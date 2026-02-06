#!/usr/bin/env python3
"""
compress_pdf.py  –  Drag-and-Drop PDF Compressor for Windows

Drag a PDF onto compress_pdf.bat (or run from the command line) to compress it.
Uses only pypdf + Pillow — no Ghostscript required.

Install dependencies:
    pip install pypdf Pillow
"""

import sys
import os
import io
import time
import shutil
import logging
import warnings


# ── Settings per compression level ───────────────────────────────────────────

LEVELS = {
    "light": {
        "label": "Light",
        "image_quality": 80,
        "max_dimension": None,      # don't resize
        "min_image_bytes": 4096,    # skip tiny images
        "remove_identicals": True,
        "remove_orphans": False,
    },
    "medium": {
        "label": "Medium",
        "image_quality": 50,
        "max_dimension": 2000,
        "min_image_bytes": 2048,
        "remove_identicals": True,
        "remove_orphans": False,
    },
    "high": {
        "label": "High",
        "image_quality": 28,
        "max_dimension": 1200,
        "min_image_bytes": 1024,
        "remove_identicals": True,
        "remove_orphans": False,
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt(size_bytes):
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


def progress_bar(current, total, width=30, prefix="  Progress"):
    """Print an in-place progress bar."""
    frac = current / total
    filled = int(width * frac)
    bar = "\u2588" * filled + "\u2591" * (width - filled)
    print(f"\r{prefix} [{bar}] {frac*100:5.1f}%  ({current}/{total})", end="", flush=True)


# ── Image recompression via Pillow ────────────────────────────────────────────

def _recompress_image(raw_bytes, width, height, color_space, settings):
    """
    Recompress raw image bytes with Pillow.
    Returns (new_bytes, new_filter_name) or (None, None) if not worth it.
    """
    try:
        from PIL import Image
    except ImportError:
        return None, None

    quality = settings["image_quality"]
    max_dim = settings["max_dimension"]

    try:
        # Try opening as-is (works for JPEG / PNG / TIFF streams)
        try:
            img = Image.open(io.BytesIO(raw_bytes))
            img.load()
        except Exception:
            # Raw decoded pixel data – reconstruct from width / height / mode
            mode = _pdf_cs_to_pil_mode(color_space)
            if mode is None or width == 0 or height == 0:
                return None, None
            bpp = {"L": 1, "RGB": 3, "CMYK": 4}.get(mode, 3)
            expected = width * height * bpp
            if len(raw_bytes) < expected:
                return None, None
            img = Image.frombytes(mode, (width, height), raw_bytes[:expected])

        # Convert palette / alpha to RGB (JPEG doesn't support alpha)
        if img.mode in ("RGBA", "LA", "PA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            conv = img.convert("RGBA") if img.mode == "P" else img
            if "A" in conv.mode:
                bg.paste(conv, mask=conv.split()[-1])
            else:
                bg.paste(conv)
            img = bg
        elif img.mode == "CMYK":
            img = img.convert("RGB")
        elif img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Downscale large images
        if max_dim and (img.width > max_dim or img.height > max_dim):
            ratio = min(max_dim / img.width, max_dim / img.height)
            new_w = max(1, int(img.width * ratio))
            new_h = max(1, int(img.height * ratio))
            img = img.resize((new_w, new_h), Image.LANCZOS)

        # Encode as JPEG
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()

        # Keep only if genuinely smaller (at least 5 % reduction)
        if len(compressed) < len(raw_bytes) * 0.95:
            return compressed, "/DCTDecode"

        return None, None

    except Exception:
        return None, None


def _pdf_cs_to_pil_mode(cs):
    """Map a PDF colour-space name to a PIL mode string."""
    if cs is None:
        return None
    s = str(cs)
    if "RGB" in s:
        return "RGB"
    if "Gray" in s or "CalGray" in s:
        return "L"
    if "CMYK" in s:
        return "CMYK"
    return None


# ── Core compression ─────────────────────────────────────────────────────────

def compress_pdf(input_path, output_path, level="medium"):
    """
    Compress *input_path* and write result to *output_path*.
    Returns (success: bool, images_compressed: int).
    """
    from pypdf import PdfReader, PdfWriter

    settings = LEVELS[level]

    # Check Pillow availability
    try:
        from PIL import Image  # noqa: F401
        has_pillow = True
    except ImportError:
        has_pillow = False
        print("  Note: Pillow not found — image compression disabled.")
        print("        Install with:  pip install Pillow")
        print()

    # Suppress noisy pypdf decompression warnings
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    logging.getLogger("pypdf._reader").setLevel(logging.ERROR)
    logging.getLogger("pypdf.generic").setLevel(logging.ERROR)

    reader = PdfReader(input_path, strict=False)
    writer = PdfWriter()

    # Clone all pages into writer first (required before modifying them)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        writer.append(reader)
    total = len(writer.pages)

    print(f"  Pages: {total}")
    print()

    images_compressed = 0

    for idx in range(total):
        page = writer.pages[idx]

        # 1. Compress content streams (zlib deflate) — skip on error
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                page.compress_content_streams()
        except Exception:
            pass  # some streams have bad headers; skip gracefully

        # 2. Compress images on this page
        if has_pillow:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                images_compressed += _compress_page_images(page, settings)

        # Progress bar (update every ~5 % or on the last page)
        step = max(1, total // 20)
        if (idx + 1) % step == 0 or (idx + 1) == total:
            progress_bar(idx + 1, total, prefix="  Pages  ")

    print()  # newline after progress bar

    # 3. De-duplicate identical objects & remove orphans
    print("  Optimising object tree ...", end="", flush=True)
    writer.compress_identical_objects(
        remove_identicals=settings["remove_identicals"],
        remove_orphans=settings.get("remove_orphans", False),
    )
    print(" done.")

    if images_compressed:
        print(f"  Images recompressed: {images_compressed}")

    # 5. Write output
    print("  Writing file ...", end="", flush=True)
    with open(output_path, "wb") as fh:
        writer.write(fh)
    print(" done.")

    return True, images_compressed


def _compress_page_images(page, settings):
    """Walk XObjects on *page*, recompress images in-place. Returns count."""
    from pypdf.generic import NameObject, NumberObject

    count = 0
    try:
        resources = page.get("/Resources")
        if resources is None:
            return 0
        xobjects = resources.get("/XObject")
        if xobjects is None:
            return 0
        xobjects = xobjects.get_object()
    except Exception:
        return 0

    for name in list(xobjects.keys()):
        try:
            xobj = xobjects[name].get_object()
        except Exception:
            continue

        if xobj.get("/Subtype") != "/Image":
            continue

        # Skip tiny images (icons, bullets …)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw = xobj.get_data()
        except Exception:
            continue  # skip streams that can't be decompressed
        if raw is None or len(raw) < settings["min_image_bytes"]:
            continue

        width = int(xobj.get("/Width", 0))
        height = int(xobj.get("/Height", 0))
        cs = xobj.get("/ColorSpace")

        new_data, new_filter = _recompress_image(raw, width, height, cs, settings)
        if new_data is None:
            continue

        # Patch the stream object in place
        try:
            xobj._data = new_data
            # Critical: clear any cached decoded data so the writer
            # serialises the NEW bytes, not stale pre-compression data.
            if hasattr(xobj, 'decoded_self'):
                xobj.decoded_self = None
            if hasattr(xobj, '_decoded_self'):
                xobj._decoded_self = None

            xobj[NameObject("/Filter")] = NameObject(new_filter)
            xobj[NameObject("/Length")] = NumberObject(len(new_data))

            # If image was downscaled, update stored dimensions
            max_dim = settings["max_dimension"]
            if max_dim and (width > max_dim or height > max_dim):
                from PIL import Image
                img = Image.open(io.BytesIO(new_data))
                xobj[NameObject("/Width")] = NumberObject(img.width)
                xobj[NameObject("/Height")] = NumberObject(img.height)

            # Strip stale decode parameters
            for key in ("/DecodeParms", "/DecodeParams", "/DP"):
                if key in xobj:
                    del xobj[key]

            # Set colour-space to match JPEG output
            if cs is not None:
                cs_str = str(cs)
                if "Gray" in cs_str or "CalGray" in cs_str:
                    xobj[NameObject("/ColorSpace")] = NameObject("/DeviceGray")
                else:
                    xobj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
                xobj[NameObject("/BitsPerComponent")] = NumberObject(8)

            count += 1
        except Exception:
            pass

    return count


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 60)
    print("          PDF Compressor  \u2013  Drag & Drop Tool")
    print("=" * 60)
    print()

    # ── Input file ────────────────────────────────────────────────────────
    if len(sys.argv) < 2:
        print("  Usage:  Drag a PDF onto compress_pdf.bat")
        print("          or run:  python compress_pdf.py <file.pdf>")
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    input_path = sys.argv[1].strip('"')

    if not os.path.isfile(input_path):
        print(f"  Error: file not found:\n  {input_path}")
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    if not input_path.lower().endswith(".pdf"):
        print(f"  Error: not a PDF file:\n  {input_path}")
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    # ── Show file info ────────────────────────────────────────────────────
    original_size = os.path.getsize(input_path)
    print(f"  File:   {os.path.basename(input_path)}")
    print(f"  Size:   {fmt(original_size)}")
    print(f"  Folder: {os.path.dirname(input_path)}")
    print()

    # ── Choose compression level ──────────────────────────────────────────
    print("  Compression options:")
    print("    [1] Light   \u2013  faster, larger file")
    print("    [2] Medium  \u2013  balanced (recommended)")
    print("    [3] High    \u2013  slower, smallest file")
    print()

    level_map = {"1": "light", "2": "medium", "3": "high"}
    while True:
        choice = input("  Select [1/2/3] (default 2): ").strip()
        if choice in ("", "2"):
            level = "medium"
            break
        if choice in level_map:
            level = level_map[choice]
            break
        print("  \u2192 Please enter 1, 2, or 3.")

    # ── Prepare output path ───────────────────────────────────────────────
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_compressed{ext}"

    print()
    print(f"  Level:  {LEVELS[level]['label']}")
    print(f"  Output: {os.path.basename(output_path)}")
    print()

    # ── Run compression ───────────────────────────────────────────────────
    start = time.time()

    try:
        success, _ = compress_pdf(input_path, output_path, level)
    except ImportError:
        print("\n  Error: pypdf is not installed.")
        print("  Run:   pip install pypdf Pillow")
        input("\n  Press Enter to exit ...")
        sys.exit(1)
    except Exception as exc:
        print(f"\n  Error: {exc}")
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    elapsed = time.time() - start

    # ── If "compressed" file is larger, just copy the original ────────────
    compressed_size = os.path.getsize(output_path)
    note = ""
    if compressed_size >= original_size:
        os.remove(output_path)
        shutil.copy2(input_path, output_path)
        compressed_size = original_size
        note = "  (File already well-optimised \u2014 saved a copy.)"

    # ── Results ───────────────────────────────────────────────────────────
    saved = original_size - compressed_size
    pct = (saved / original_size * 100) if original_size else 0

    print()
    print("-" * 60)
    print(f"  Original:    {fmt(original_size)}")
    print(f"  Compressed:  {fmt(compressed_size)}")
    print(f"  Saved:       {fmt(saved)}  ({pct:.1f}% reduction)")
    print(f"  Time:        {elapsed:.1f}s")
    print(f"  Output:      {output_path}")
    if note:
        print(note)
    print("-" * 60)

    input("\n  Press Enter to exit ...")


if __name__ == "__main__":
    main()
