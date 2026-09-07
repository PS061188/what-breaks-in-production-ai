"""Run every chapter's broken/fixed pair and print the summary lines.

    python run_all.py           # replay everything from fixtures, free
    python run_all.py --live    # re-record everything (see the cost note in README)
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CHAPTERS = [
    ("ch02-input-integrity", "Input integrity failures"),
    ("ch03-hallucination", "Hallucinations and confident fabrication"),
    ("ch04-classification-cascade", "Classification cascade errors"),
    ("ch05-extraction-normalisation", "Extraction and normalisation quality loss"),
    ("ch06-state-mismatch", "State mismatch failures"),
    ("ch07-edge-input", "Edge input failures"),
    ("ch08-routing-placement", "Routing and placement errors"),
    ("ch09-sparse-field-fabrication", "Sparse field fabrication"),
    ("ch10-silent-omissions", "Silent omissions"),
]


def run(script: Path, extra: list) -> str:
    result = subprocess.run(
        [sys.executable, str(script), *extra],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"    FAILED: {result.stderr.strip().splitlines()[-1] if result.stderr else '?'}"
    lines = [line for line in result.stdout.splitlines() if line.startswith(">>")]
    return "\n".join("    " + line for line in lines) or "    (no summary lines)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    extra = []
    if args.live:
        extra.append("--live")
    if args.model:
        extra += ["--model", args.model]
    if args.limit:
        extra += ["--limit", str(args.limit)]

    helpers = {"common.py", "normalise.py"}
    for directory, title in CHAPTERS:
        print(f"\n{'=' * 70}\n{directory}  —  {title}\n{'=' * 70}")
        if not (ROOT / directory).is_dir():
            continue  # chapter not built yet
        scripts = [p for p in sorted((ROOT / directory).glob("*.py")) if p.name not in helpers]
        # broken and fixed first — they are the comparison. The fix_*.py scripts
        # are individual engineering fixes measured on their own.
        scripts.sort(key=lambda p: {"broken.py": 0, "fixed.py": 1}.get(p.name, 2))
        for script in scripts:
            print(f"\n  {script.name}")
            print(run(script, extra))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
