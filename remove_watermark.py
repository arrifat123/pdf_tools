#!/usr/bin/env python3
"""
PDF Watermark Remover — Text Mode
===================================
Removes watermark TEXT from PDFs by keyword matching.

Uses PyMuPDF to reliably locate watermark text on every page
(handles any font encoding, rotation, and transparency)
and surgically removes it while preserving all other content.

Drag a PDF onto remover.bat or pass as argument.
Output: "filename_no_watermark.pdf" in the same folder.
"""

import subprocess
import sys
import os
import time

# ── Auto-install PyMuPDF if missing ──────────────────────────────────────
try:
    import fitz
except ImportError:
    print("  Installing PyMuPDF...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyMuPDF"])
    import fitz


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def progress_bar(current: int, total: int, width: int = 40):
    pct = current / total
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    print(f"\r  [{bar}] {current}/{total} pages ({pct:.0%})", end="", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  TEXT-BASED WATERMARK REMOVAL  (PyMuPDF search + redaction)
# ═══════════════════════════════════════════════════════════════════════════════

def remove_watermark_text(pdf_path: str, keywords: list[str], out_path: str) -> int:
    """
    Locate all instances of keyword text on every page using PyMuPDF's
    text search engine (handles font encoding, rotation, etc.), then
    redact (remove) them.

    - Images are fully preserved (never touched).
    - Only the matched watermark text is removed.
    - Works with rotated, semi-transparent, and multi-line watermarks.

    Returns total number of watermark instances removed.
    """
    doc = fitz.open(pdf_path)
    total = len(doc)
    total_removed = 0

    print(f"  Pages: {total}")
    print(f"  Keywords: {', '.join(keywords)}\n")

    for i, page in enumerate(doc):
        page_hits = 0

        for keyword in keywords:
            # search_for returns Quad objects that follow text rotation
            hits = page.search_for(keyword, quads=True)

            for quad in hits:
                # Add a redaction annotation over the matched text.
                # After apply_redactions(), only the content inside
                # these quads is removed — everything else stays.
                page.add_redact_annot(quad=quad)
                page_hits += 1

        if page_hits > 0:
            # Apply redactions:
            #   images=0  →  PDF_REDACT_IMAGE_NONE  →  images are NOT touched
            #   graphics=0  →  vector drawings are NOT touched  (PyMuPDF ≥ 1.23)
            # This removes ONLY the matched text glyphs.
            try:
                page.apply_redactions(images=0, graphics=0)
            except TypeError:
                # Older PyMuPDF without 'graphics' parameter
                page.apply_redactions(images=0)

            total_removed += page_hits

        progress_bar(i + 1, total)

    print()

    # Save with garbage collection + compression
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()

    return total_removed


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  PDF Watermark Remover — Text Mode")
    print("=" * 60)

    # ── Get PDF path ─────────────────────────────────────────────────────
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1].strip().strip('"')
        print(f"\n  File: {pdf_path}")
    else:
        print("\n  No file was dragged onto the script.")
        pdf_path = input("  Enter the full path to a PDF: ").strip().strip('"')

    if not pdf_path or not os.path.isfile(pdf_path):
        print("  Error: File not found or not provided.")
        input("\n  Press Enter to close...")
        sys.exit(1)

    if not pdf_path.lower().endswith(".pdf"):
        print("  Error: Not a PDF file.")
        input("\n  Press Enter to close...")
        sys.exit(1)

    # ── Build output path ────────────────────────────────────────────────
    folder = os.path.dirname(pdf_path) or "."
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    out_path = os.path.join(folder, f"{base}_no_watermark.pdf")

    # ── Get keywords ─────────────────────────────────────────────────────
    print()
    raw = input("  Enter watermark text to remove (comma-separated): ").strip()
    keywords = [k.strip() for k in raw.split(",") if k.strip()]
    if not keywords:
        print("  No keywords provided. Exiting.")
        input("\n  Press Enter to close...")
        sys.exit(1)

    # ── Run removal ──────────────────────────────────────────────────────
    start = time.time()
    print(f"\n  Scanning and removing watermark text...\n")

    found = remove_watermark_text(pdf_path, keywords, out_path)

    elapsed = time.time() - start
    print(f"\n  Watermark instances found & removed: {found}")
    print(f"  Time: {elapsed:.1f}s")

    # ── Report ───────────────────────────────────────────────────────────
    if os.path.isfile(out_path):
        orig_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"\n  Original: {orig_mb:.2f} MB")
        print(f"  Cleaned:  {size_mb:.2f} MB")
        print(f"\n  Saved to: {out_path}")

        if found == 0:
            print("\n  No matches found. Tips:")
            print("    - Check the exact spelling of the watermark text")
            print("    - Try shorter keywords (part of the watermark)")
            print("    - The watermark might be an image, not text")
    else:
        print("\n  Error — no output file was created.")

    input("\n  Press Enter to close...")


if __name__ == "__main__":
    main()
