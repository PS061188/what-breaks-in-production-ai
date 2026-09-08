"""Chapter 8's prompt template, transposed onto this corpus and measured.

The chapter's prompt is written for a shipping intake form — origin, destination
and billing addresses — which this corpus does not contain. What transposes is
the machinery it wraps around the fields, and that machinery had never been run:

  FIELD DEFINITIONS      each field defined before extraction begins
  DISAMBIGUATION         quote the text, name the keywords, state confidence
  placement_confidence   HIGH | MEDIUM | LOW, per field
  requires_review        set true when any field is LOW
  PLACEMENT SELF-CHECK   verify the fields are not duplicates of each other

The chapter's own argument is that a model's account of where content came from
cannot be trusted, which is why its engineering fix verifies the quote instead.
This measures whether the confidence machinery in its *prompt* fares any better.

    python3 book_prompt.py --live
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BOXES, build_cases, locate  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

SYSTEM = """You are an intake processor. Extract and route data to the correct
fields. Field confusion causes downstream errors - precision is required.

FIELD DEFINITIONS (apply these before extracting):
  - "what_it_treats": the conditions the drug is INDICATED for. Keywords:
    "indicated for", "treatment of", "management of"
  - "who_must_not_take_it": the conditions that FORBID the drug. Keywords:
    "contraindicated", "should not be used", "do not administer"
  - "side_effects": the reactions the drug CAUSES. Keywords: "adverse
    reactions", "commonly reported", "observed in trials"

DISAMBIGUATION PROTOCOL:
If the role of any passage is unclear:
  1. Quote the exact text where it appears
  2. State which contextual keywords indicate its role
  3. State your confidence: HIGH / MEDIUM / LOW
  4. If LOW confidence for any field: set "requires_review": true

PLACEMENT SELF-CHECK:
After populating all fields, verify:
  - Are what_it_treats and who_must_not_take_it different? If identical, flag it.
  - Does side_effects describe reactions rather than indications?

<label>
{context}
</label>"""

FIELD = {
    "type": "object",
    "properties": {
        "value": {"type": ["string", "null"]},
        "source_quote": {"type": ["string", "null"]},
        "source_section": {"type": ["string", "null"]},
        "placement_confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
    },
    "required": ["value", "source_quote", "source_section", "placement_confidence"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {**{b: FIELD for b, _ in BOXES},
                   "requires_review": {"type": "boolean"},
                   "review_reason": {"type": ["string", "null"]}},
    "required": [b for b, _ in BOXES] + ["requires_review", "review_reason"],
    "additionalProperties": False,
}


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    results = map_parallel(
        lambda c: llm.json(system=SYSTEM.format(context=c["context"]),
                           user="Extract the three fields.",
                           schema=SCHEMA, max_tokens=2500),
        cases,
    )

    rows, misplaced, total = [], 0, 0
    conf = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    flagged_when_wrong = wrong = 0
    for case, r in zip(cases, results):
        for box, expected in BOXES:
            f = r[box]
            found = locate(f.get("source_quote") or "", case["sections"])
            bad = found is not None and found != expected
            total += 1
            misplaced += bad
            conf[f["placement_confidence"]] += 1
            wrong += bad
            flagged_when_wrong += bool(bad and (f["placement_confidence"] != "HIGH"
                                                or r["requires_review"]))
            if bad:
                rows.append([case["drug"][:18], box, expected, str(found),
                             f["placement_confidence"],
                             "yes" if r["requires_review"] else "no"])

    if rows:
        rule("Fields whose quote came from the wrong section")
        table(["drug", "box", "should be", "actually from", "confidence",
               "requires_review"], rows)

    headline("Placement error rate", pct(misplaced, total),
             "The plain prompt measured elsewhere in this chapter gives 0-3%.")
    headline("Fields graded HIGH placement confidence",
             pct(conf["HIGH"], total),
             f"MEDIUM {conf['MEDIUM']}, LOW {conf['LOW']}, of {total} fields.")
    headline("Times requires_review was set",
             pct(sum(1 for r in results if r["requires_review"]), len(results)),
             "The flag the whole disambiguation protocol exists to raise.")
    headline("Misplaced fields the machinery flagged",
             pct(flagged_when_wrong, wrong) if wrong else "nothing was misplaced",
             "Either a non-HIGH confidence or requires_review would count.")
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
