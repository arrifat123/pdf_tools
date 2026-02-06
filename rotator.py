"""
PDF Page Rotator — Auto-detect horizontal pages or manually rotate by angle.
Uses pypdf only. Designed for drag-and-drop via rotator.bat.
"""

import sys
import os
import time
from pypdf import PdfReader, PdfWriter


# ── helpers ────────────────────────────────────────────────────────────────

def parse_page_ranges(text: str, total_pages: int) -> list[int]:
    """Parse user input like '1-10,45,67-72' into a sorted list of 0-based page indices."""
    pages: set[int] = set()
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            tokens = part.split("-", 1)
            try:
                start, end = int(tokens[0]), int(tokens[1])
            except ValueError:
                print(f"  [!] Skipping invalid range: '{part}'")
                continue
            if start < 1 or end < 1:
                print(f"  [!] Page numbers must be >= 1. Skipping '{part}'")
                continue
            if start > end:
                start, end = end, start
            if start > total_pages:
                print(f"  [!] Range {part} is beyond total pages ({total_pages}). Skipping.")
                continue
            end = min(end, total_pages)
            pages.update(range(start - 1, end))  # 0-based
        else:
            try:
                num = int(part)
            except ValueError:
                print(f"  [!] Skipping invalid entry: '{part}'")
                continue
            if num < 1 or num > total_pages:
                print(f"  [!] Page {num} is out of range (1-{total_pages}). Skipping.")
                continue
            pages.add(num - 1)
    return sorted(pages)


def collapse_ranges(indices_0based: list[int]) -> str:
    """Turn [14,15,16,17,18,19,44,66,67,68,69,70,71] into '15-20, 45, 67-72' (1-based)."""
    if not indices_0based:
        return "(none)"
    nums = [i + 1 for i in indices_0based]  # 1-based
    parts: list[str] = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
        else:
            parts.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = n
    parts.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(parts)


def is_landscape(page) -> bool:
    """Return True if the page's effective (post-rotation) width > height."""
    box = page.mediabox
    w = float(box.width)
    h = float(box.height)
    rotation = page.get("/Rotate", 0) or 0
    rotation = int(rotation) % 360
    if rotation in (90, 270):
        w, h = h, w
    return w > h


def show_progress(current: int, total: int, label: str = "Processing"):
    """Simple inline progress bar for large files."""
    pct = current / total * 100
    bar_len = 30
    filled = int(bar_len * current // total)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\r  {label}: |{bar}| {pct:5.1f}%  ({current}/{total})", end="", flush=True)


# ── core logic ─────────────────────────────────────────────────────────────

def auto_detect_and_rotate(reader: PdfReader, writer: PdfWriter) -> int:
    total = len(reader.pages)
    show_prog = total > 50
    landscape_indices: list[int] = []

    # Pass 1 — detect
    print("\n  Scanning pages for horizontal orientation...")
    for i in range(total):
        if show_prog and (i % 5 == 0 or i == total - 1):
            show_progress(i + 1, total, "Scanning")
        if is_landscape(reader.pages[i]):
            landscape_indices.append(i)
    if show_prog:
        show_progress(total, total, "Scanning")
        print()

    if not landscape_indices:
        print("\n  No horizontal pages detected — nothing to rotate.")
        return 0

    print(f"\n  Detected {len(landscape_indices)} horizontal page(s): {collapse_ranges(landscape_indices)}")

    # Pass 2 — build output
    print("  Rotating detected pages 90° clockwise to portrait...")
    rotated_set = set(landscape_indices)
    for i in range(total):
        if show_prog and (i % 5 == 0 or i == total - 1):
            show_progress(i + 1, total, "Writing ")
        page = reader.pages[i]
        if i in rotated_set:
            page = page.rotate(90)
        writer.add_page(page)
    if show_prog:
        show_progress(total, total, "Writing ")
        print()

    return len(landscape_indices)


def manual_rotate(reader: PdfReader, writer: PdfWriter) -> int:
    total = len(reader.pages)
    show_prog = total > 50

    # Get page numbers
    raw = input("\n  Enter page numbers to rotate (e.g., 15-20,45,67-72 or 'all' for all pages): ").strip()
    if raw.lower() == "all":
        target_indices = list(range(total))
    else:
        target_indices = parse_page_ranges(raw, total)

    if not target_indices:
        print("  No valid pages selected — nothing to rotate.")
        return 0

    # Get angle
    angle_input = input("  Rotation angle? (90 / 180 / 270 or -90 for counter-clockwise): ").strip()
    try:
        angle = int(angle_input)
    except ValueError:
        print("  [!] Invalid angle. Must be an integer.")
        return 0

    # Normalise angle
    if angle == -90:
        angle = 270
    elif angle == -180:
        angle = 180
    elif angle == -270:
        angle = 90

    if angle % 90 != 0 or angle == 0:
        print("  [!] Angle must be a non-zero multiple of 90.")
        return 0

    angle = angle % 360  # keep in 90/180/270

    print(f"\n  Rotating {len(target_indices)} page(s) by {angle}°...")
    print(f"  Pages: {collapse_ranges(target_indices)}")

    target_set = set(target_indices)
    for i in range(total):
        if show_prog and (i % 5 == 0 or i == total - 1):
            show_progress(i + 1, total, "Writing ")
        page = reader.pages[i]
        if i in target_set:
            page = page.rotate(angle)
        writer.add_page(page)
    if show_prog:
        show_progress(total, total, "Writing ")
        print()

    return len(target_indices)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║        PDF  PAGE  ROTATOR            ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    # --- get input file ---
    if len(sys.argv) < 2:
        print("  [!] No PDF file provided.")
        print("  Usage: Drag a PDF onto rotator.bat, or run:")
        print("         python rotator.py <file.pdf>")
        return

    pdf_path = sys.argv[1].strip('"')
    if not os.path.isfile(pdf_path):
        print(f"  [!] File not found: {pdf_path}")
        return
    if not pdf_path.lower().endswith(".pdf"):
        print(f"  [!] Not a PDF file: {pdf_path}")
        return

    print(f"  File : {os.path.basename(pdf_path)}")
    print(f"  Path : {os.path.dirname(os.path.abspath(pdf_path))}")

    # --- read PDF ---
    try:
        reader = PdfReader(pdf_path)
    except Exception as exc:
        print(f"\n  [!] Failed to read PDF: {exc}")
        return

    total = len(reader.pages)
    print(f"  Pages: {total}")
    print()

    # --- choose mode ---
    choice = input("  Auto-detect horizontal pages? (Y/N): ").strip().upper()
    writer = PdfWriter()

    t0 = time.perf_counter()

    if choice == "Y":
        count = auto_detect_and_rotate(reader, writer)
    elif choice == "N":
        count = manual_rotate(reader, writer)
    else:
        print("  [!] Invalid choice. Please enter Y or N.")
        return

    if count == 0:
        print("\n  Done — no pages were rotated. Output file not created.")
        return

    # --- save ---
    base, ext = os.path.splitext(pdf_path)
    out_path = f"{base}_rotated{ext}"

    print("\n  Saving...")
    try:
        with open(out_path, "wb") as f:
            writer.write(f)
    except Exception as exc:
        print(f"  [!] Failed to save: {exc}")
        return

    elapsed = time.perf_counter() - t0
    size_mb = os.path.getsize(out_path) / (1024 * 1024)

    print()
    print("  ── SUCCESS ──────────────────────────────")
    print(f"  Rotated : {count} page(s)")
    print(f"  Output  : {os.path.basename(out_path)}")
    print(f"  Location: {os.path.dirname(os.path.abspath(out_path))}")
    print(f"  Size    : {size_mb:.1f} MB")
    print(f"  Time    : {elapsed:.1f}s")
    print("  ─────────────────────────────────────────")


if __name__ == "__main__":
    main()
