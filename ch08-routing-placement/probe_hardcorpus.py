"""Chapter 8, probe: does the chapter's prompt prevent misplacement when
misplacement is actually possible?

On the labels as supplied — three sections, each under its own heading — neither
the plain prompt nor Prompt 8-1 misplaced anything (FINDINGS §3). That corpus is
too easy to show what a prompt adds: the heading tells the model where every
sentence belongs.

This probe removes the headings. Each label's three sections are split into
sentences and shuffled together (fixed seed per drug, so both prompts see the
same text), and the model must decide from content alone whether a sentence is
an indication, a contraindication or an adverse reaction. That is the decision
a real note demands, and the ground truth is still exact: every sentence's
section of origin is known.

Two prompts, as printed in the book:
  plain     broken.py's prompt — fill the fields, quote your source
  chapter   fixed.py's prompt — FIELD SOURCES rule, quote character-for-character
Three separate live draws each (the helper's `sample` index keeps the draws
apart in the cache). Scored with the same locate() as fixed.py; the primary
number uses the whole quote, because the quotes here are sentence-length and
the 80-character window's boilerplate artefact (FINDINGS §3) does not apply.
Both windows are printed.

Usage:
  python probe_hardcorpus.py           # replay
  python probe_hardcorpus.py --live    # record three draws per prompt (~$0.40)
"""

import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import common  # noqa: E402
from common import BOXES, BOX_LIST, SECTIONS, build_cases  # noqa: E402
import broken  # noqa: E402
import fixed  # noqa: E402
from shared import scoring  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402

PROMPTS = {"plain": (broken.SYSTEM, broken.schema), "chapter": (fixed.SYSTEM, fixed.schema)}
RUNS = (1, 2, 3)


def sentences(text: str):
    parts = re.split(r"(?<=[.;:])\s+(?=[A-Z(])", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def hard_cases():
    out = []
    for case in build_cases():
        pool = []
        for section in SECTIONS:
            pool += [(s, section) for s in sentences(case["sections"][section])]
        random.Random(case["drug"]).shuffle(pool)
        out.append({**case, "hard_context": "\n".join(s for s, _ in pool), "n_sentences": len(pool)})
    return out


def locate_at(window: int):
    common.quote_supported = lambda q, t, threshold=85.0, w=window: scoring.quote_supported(q, t, threshold, w)


def score(case, result, window):
    locate_at(window)
    mis = unl = 0
    for box, expected in BOXES:
        found = common.locate(result[box].get("source_quote") or "", case["sections"])
        if found is None:
            unl += 1
        elif found != expected:
            mis += 1
    return mis, unl


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(HERE, model=args.model, live=args.live)
    cases = hard_cases()
    n_boxes = len(cases) * len(BOXES)
    print(f"{len(cases)} labels, headings removed, sentences shuffled "
          f"({sum(c['n_sentences'] for c in cases)} sentences in all); {n_boxes} boxes per run\n")
    results = {}
    for name, (system, schema_fn) in PROMPTS.items():
        for run in RUNS:
            for case in cases:
                results[(name, run, case["drug"])] = llm.json(
                    system=system.format(context=case["hard_context"]),
                    user=f"Fill in these fields: {BOX_LIST}",
                    schema=schema_fn(),
                    max_tokens=2000,
                    sample=run,
                )
    for window, label in ((0, "whole quote"), (80, "80 characters")):
        print(f"=== locator: {label} ===")
        print(f"{'prompt':10} {'run':>4} {'misplaced':>10} {'no match':>9}   (of {n_boxes} boxes)")
        for name in PROMPTS:
            for run in RUNS:
                mis = unl = 0
                for case in cases:
                    m, u = score(case, results[(name, run, case["drug"])], window)
                    mis += m; unl += u
                print(f"{name:10} {run:>4} {mis:>10} {unl:>9}")
        print()
    print("misplaced = the quote is found in a different section from the box's own.")
    print("no match  = the quote is not found in any section (paraphrased, or invented).")
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
