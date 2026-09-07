"""Chapter 8, the baseline: three boxes, three sections, no constraint linking them.

The model is given all three sections at once and asked to fill all three boxes.
Nothing in the request says which section belongs to which box — the names are
descriptive and the model is left to work it out. That is how most extraction
prompts are written, because the mapping is obvious to the person writing it.

What we measure is not whether the answer sounds right. It is whether the text
in each box actually came from the section that can legitimately fill it.

    python broken.py            # replay
    python broken.py --live     # re-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BOX_LIST, BOXES, build_cases, score  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

SYSTEM = """You are a clinical data extraction assistant. Read the drug label
below and fill in each requested field. Include a short source_quote for each
field, and name the section you took it from.

<label>
{context}
</label>"""


def schema() -> dict:
    props = {
        box: {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "source_quote": {"type": "string"},
                "source_section": {"type": "string"},
            },
            "required": ["value", "source_quote", "source_section"],
            "additionalProperties": False,
        }
        for box, _ in BOXES
    }
    return {
        "type": "object",
        "properties": props,
        "required": [box for box, _ in BOXES],
        "additionalProperties": False,
    }


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    all_rows = []
    for case in cases:
        result = llm.json(
            system=SYSTEM.format(context=case["context"]),
            user=f"Fill in these fields: {BOX_LIST}",
            schema=schema(),
            max_tokens=2000,
        )
        all_rows.extend(score(case, result))

    misplaced = [r for r in all_rows if r["misplaced"]]
    unlocatable = [r for r in all_rows if r["unlocatable"]]
    lying = [r for r in all_rows if r["actual_section"] and r["claimed_section"]
             and r["claimed_section"] != r["actual_section"]]

    rule("Boxes whose content came from the wrong section")
    table(
        ["drug", "box", "should come from", "actually came from", "value (first 40)"],
        [
            [r["drug"][:18], r["box"], r["expected_section"][:20],
             (r["actual_section"] or "—")[:20], r["value"][:40].replace("\n", " ")]
            for r in misplaced
        ] or [["—", "none", "", "", ""]],
    )

    headline(
        "Placement error rate",
        pct(len(misplaced), len(all_rows)),
        "Content lifted from one section and filed under another. Nothing is "
        "fabricated: every word is really in the document, in the wrong box.",
    )
    headline(
        "Quotes that match no supplied section at all",
        pct(len(unlocatable), len(all_rows)),
        "Either paraphrased while quoting, or drawn from outside the material.",
    )
    headline(
        "Cases where the model named the wrong section for its own quote",
        pct(len(lying), len(all_rows)),
        "The model's own account of where content came from is not a check. "
        "That is why the fix verifies the quote rather than trusting the label.",
    )
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
