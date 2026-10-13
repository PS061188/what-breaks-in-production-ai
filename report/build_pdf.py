"""Assemble report/parts/*.html into one document and render it to PDF.

The report is split into parts so a chapter can be revised without touching the
rest, and so parts can be added as more chapters are run. Files are concatenated
in filename order — the numeric prefixes are the running order.

Uses headless Chrome, the same renderer convert_to_pdf.py uses for the book, so
there is one PDF toolchain in this project rather than two.

    python report/build_pdf.py
"""

import subprocess
import sys
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HERE = Path(__file__).resolve().parent
PARTS = HERE / "parts"
HTML = HERE / "experiments.html"
PDF = HERE / "What-Breaks-in-Production-AI-The-Experiments.pdf"


def assemble() -> str:
    parts = sorted(PARTS.glob("*.html"))
    if not parts:
        raise SystemExit(f"no parts found in {PARTS}")
    head = parts[0].read_text()
    body = "\n".join(p.read_text() for p in parts[1:])
    print(f"assembling {len(parts)} parts: {', '.join(p.name for p in parts)}")
    return f"{head}\n<body>\n{body}\n</body>\n</html>\n"


def main() -> int:
    if not Path(CHROME).exists():
        print(f"Chrome not found at {CHROME}", file=sys.stderr)
        return 1

    HTML.write_text(assemble())

    result = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--run-all-compositor-stages-before-draw",
         f"--print-to-pdf={PDF}", "--print-to-pdf-no-header", "--no-pdf-header-footer",
         f"file://{HTML}"],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        print(result.stderr[:800], file=sys.stderr)
        return 1

    print(f"wrote {PDF.name}  ({PDF.stat().st_size / 1e6:.1f} MB)")
    try:
        import fitz
        doc = fitz.open(PDF)
        page = doc[min(5, len(doc) - 1)]
        sizes = [s["size"] for b in page.get_text("dict")["blocks"]
                 for l in b.get("lines", []) for s in l["spans"]]
        body = max(sizes) if sizes else 0
        doc.close()
        # Chrome shrinks the whole document to fit its widest element, silently.
        # One nowrap cell full of prose cost 31 pages before anyone noticed
        # (4 Oct 2026). Body text on a mid page is ~9-14pt when healthy.
        if body < 8.0:
            print(f"SCALE WARNING: largest text on a mid page is {body:.1f}pt — "
                  "an element is wider than the page and Chrome shrank everything.")
            return 1
    except ImportError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
