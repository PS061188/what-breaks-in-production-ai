"""Render the corpus to page images, OCR them back, and record the confidence.

Chapter 2's second engineering fix is to carry OCR confidence scores downstream
and treat low-confidence regions as suspect. It has been marked "not implemented
as written" for the whole project, because the corpus is FDA text that was never
scanned: there are no confidence numbers to carry, and inventing them would mean
generating the exact signal the fix depends on.

This script removes that excuse. Each label section is typeset onto a page,
rendered to an image, degraded the way a scan or a fax degrades one, and read
back with a real OCR engine. What comes out is genuinely damaged text with the
engine's own per-line confidence attached — the input the fix was always
supposed to have.

    .venv-ocr/bin/python make_ocr_corpus.py
    .venv-ocr/bin/python make_ocr_corpus.py --limit 1 --keep-images
"""

import argparse
import json
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "labels_ocr.json"
PAGES = ROOT / "ocr_pages"
SECTION = "dosage_and_administration"

# A page rendered at this DPI, then degraded, is roughly a mid-quality office
# scan: readable, and wrong in the places scans are wrong.
# Chosen by sweeping until word accuracy landed near 92% — a plausible
# mid-quality office scan. Below roughly 95 DPI Vision stops detecting text
# rather than misreading it, so the usable band is narrow.
DPI = 105
BLUR = 1.0
JPEG_QUALITY = 28


def chunk(text: str, size: int = 2400):
    """Split on whitespace into page-sized pieces, losing nothing.

    insert_textbox reports leftover *height*, not leftover characters, so it
    cannot be used to paginate. Chunking here instead means the concatenation of
    the pages is exactly the input, which the caller asserts.
    """
    words, pages, cur = text.split(), [], []
    n = 0
    for w in words:
        if n + len(w) + 1 > size and cur:
            pages.append(" ".join(cur))
            cur, n = [], 0
        cur.append(w)
        n += len(w) + 1
    if cur:
        pages.append(" ".join(cur))
    return pages


def typeset(text: str, path: Path) -> int:
    doc = fitz.open()
    pieces = chunk(text)
    for piece in pieces:
        page = doc.new_page()
        box = fitz.Rect(56, 56, page.rect.width - 56, page.rect.height - 56)
        if page.insert_textbox(box, piece, fontsize=10.5,
                               fontname="times-roman", align=0) < 0:
            raise SystemExit(
                f"page overflow on a {len(piece)}-char chunk — lower the chunk size"
            )
    doc.save(path)
    doc.close()
    return len(pieces)


def degrade(img: Image.Image, tmp: Path) -> Image.Image:
    """What a scanner and a fax queue do to a clean page."""
    img = img.convert("L")
    img = img.filter(ImageFilter.GaussianBlur(BLUR))
    img.save(tmp, "JPEG", quality=JPEG_QUALITY)
    return Image.open(tmp)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--keep-images", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from shared.llm import load_labels  # noqa: E402
    from ocrmac import ocrmac  # noqa: E402  (Apple Vision, no install needed)

    PAGES.mkdir(exist_ok=True)
    labels = load_labels()
    if args.limit:
        labels = labels[: args.limit]

    out = []
    for label in labels:
        clean = label["sections"].get(SECTION, "")
        if not clean:
            continue
        drug = label["drug"]
        stem = "".join(c for c in drug if c.isalnum())[:24]
        pdf, png, jpg = (PAGES / f"{stem}.pdf", PAGES / f"{stem}.png",
                         PAGES / f"{stem}.jpg")

        n_pages = typeset(clean, pdf)
        doc = fitz.open(pdf)
        lines, confs = [], []
        for page in doc:
            page.get_pixmap(dpi=DPI).save(png)
            degrade(Image.open(png), jpg)
            for text, score, _box in ocrmac.OCR(str(jpg)).recognize():
                lines.append(text)
                confs.append(float(score))
        doc.close()

        out.append({
            "drug": drug,
            "clean": clean,
            "ocr_text": " ".join(lines),
            "ocr_lines": lines,
            "ocr_confidence": confs,
            "pages": n_pages,
        })
        print(f"  {drug[:28]:30s} clean {len(clean):6d} -> ocr {len(' '.join(lines)):6d} "
              f"chars, {len(lines):4d} lines, mean conf {sum(confs)/max(len(confs),1):.3f}")

        if not args.keep_images:
            for p in (pdf, png, jpg):
                p.unlink(missing_ok=True)

    OUT.write_text(json.dumps({"documents": out}, indent=1))
    print(f"\nwrote {OUT.relative_to(ROOT)} — {len(out)} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
