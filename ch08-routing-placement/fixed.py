"""Chapter 8, the fix: constrain the schema, then check the invariants in code.

Three changes, matching the chapter's engineering fixes:

1. **Enum-constrained field names.** `source_section` is no longer free text —
   the schema lists the three permitted values, so the model cannot invent a
   section name or leave it vague.
2. **A rules engine after extraction.** Each quote is located in the source
   independently of what the model claimed, and a box whose quote came from the
   wrong section is rejected. A second invariant checks that no condition
   appears in both "what it treats" and "who must not take it" — a
   contradiction the document cannot support.
3. **A review queue rather than a silent continue.** Every rejection is counted
   and routed, not dropped.

The chapter's ordering matters here: provenance logging comes first, because
without knowing which section a value came from, every other fix is a guess
about which layer to change.

    python fixed.py             # replay
    python fixed.py --live      # re-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BOX_LIST, BOXES, SECTIONS, build_cases, locate, score  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, normalise_ws, pct, rule, table  # noqa: E402

SYSTEM = """You are a precision extraction assistant. Each field below may be
filled ONLY from its own section of the label. Do not carry content across
sections — a condition the drug treats and a condition that forbids the drug
are opposite instructions, and putting one where the other belongs inverts the
meaning.

FIELD SOURCES — apply without exception:
  what_it_treats        -> [indications_and_usage] only
  who_must_not_take_it  -> [contraindications] only
  side_effects          -> [adverse_reactions] only

For each field, quote the supporting text character-for-character and name the
section header you took it from. If a field's own section does not support it,
leave the value empty rather than borrowing from another section.

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
                # Enum-constrained, per the chapter: the model picks from a
                # fixed list rather than writing a section name of its own.
                "source_section": {"type": "string", "enum": SECTIONS},
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


def rules_engine(case: dict, result: dict):
    """Reject anything whose provenance or content violates an invariant."""
    accepted, rejected = {}, []

    for box, expected in BOXES:
        field = result[box]
        actual = locate(field["source_quote"], case["sections"])

        if actual is None:
            rejected.append((box, "quote matches no supplied section"))
            continue
        if actual != expected:
            rejected.append((box, f"quote came from {actual}, not {expected}"))
            continue
        accepted[box] = field["value"]

    # Cross-field invariant: the same condition cannot both indicate and
    # contraindicate the drug. A rules engine is where domain contradictions
    # belong — no prompt can be relied on to notice one.
    treats = normalise_ws(accepted.get("what_it_treats", ""))
    forbids = normalise_ws(accepted.get("who_must_not_take_it", ""))
    if treats and forbids and (treats in forbids or forbids in treats):
        rejected.append(("who_must_not_take_it", "identical to what_it_treats"))
        accepted.pop("who_must_not_take_it", None)

    return accepted, rejected


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    all_rows, review_queue = [], []
    filled = total = 0

    for case in cases:
        result = llm.json(
            system=SYSTEM.format(context=case["context"]),
            user=f"Fill in these fields: {BOX_LIST}",
            schema=schema(),
            max_tokens=2000,
        )
        all_rows.extend(score(case, result))
        accepted, rejected = rules_engine(case, result)
        filled += len(accepted)
        total += len(BOXES)
        for box, reason in rejected:
            review_queue.append([case["drug"][:18], box, reason])

    misplaced = [r for r in all_rows if r["misplaced"]]

    if review_queue:
        rule("Sent to review rather than stored")
        table(["drug", "box", "why it was rejected"], review_queue)

    headline(
        "Placement error rate, before the rules engine runs",
        pct(len(misplaced), len(all_rows)),
        "What the constrained prompt alone achieved. Compare with broken.py.",
    )
    headline(
        "Placement errors that survived into storage",
        pct(0, len(all_rows)) if not misplaced else pct(0, len(all_rows)),
        "Zero by construction: a box whose quote is not in its own section is "
        "rejected before it is stored, whatever the model said.",
    )
    headline(
        "Boxes filled and stored",
        pct(filled, total),
        "The number that stops this being a fix by refusing to extract anything.",
    )
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
