"""Chapter 10's COMPLETENESS PROTOCOL, run verbatim against the same documents.

The chapter's prompt is a four-step protocol: inventory the document by counting
categories BEFORE extracting, extract, then self-check extracted counts against
the inventory and re-read for any category that comes up short.

It had never been run. `fixed.py` tests a lighter instruction of my own — count
your source, list what you did not extract — so the protocol itself had no
number. The interesting question is whether the self-check does anything, given
that this chapter already measured the model's own count of the source as wrong
on 6 of 6 documents.

    python3 book_prompt.py --live
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases, dose_figures  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

SYSTEM = """You are an extraction engine. Completeness is your primary quality
metric. Missing data is worse than null data - at least null is honest.

COMPLETENESS PROTOCOL:

Step 1 - INVENTORY (do this before extracting anything):
Read the entire document and count the total number of dose amounts it contains.
Record that count as "inventory_count".

Step 2 - EXTRACT all dose amounts.

Step 3 - COMPLETENESS SELF-CHECK:
Verify: extracted_count == inventory_count
If the counts mismatch:
  - State by how many you are short
  - Re-read the document specifically for dose amounts
  - Add the missing items
  - If still short, flag it in "warnings"

Step 4 - OUTPUT including completeness_check.

<text>
{text}
</text>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "inventory_count": {"type": "integer"},
        "doses": {"type": "array", "items": {"type": "string"}},
        "completeness_check": {
            "type": "object",
            "properties": {
                "all_counts_match": {"type": "boolean"},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["all_counts_match", "warnings"],
            "additionalProperties": False,
        },
    },
    "required": ["inventory_count", "doses", "completeness_check"],
    "additionalProperties": False,
}


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    results = map_parallel(
        lambda c: llm.json(system=SYSTEM.replace("{text}", c["text"]),
                           user="Run the protocol and return the result.",
                           schema=SCHEMA, max_tokens=2500),
        cases,
    )

    rows, returned, expected, dropped = [], 0, 0, 0
    warned_when_short = short = 0
    for case, r in zip(cases, results):
        got = dose_figures(" ".join(r["doses"]))
        missing = case["expected"] - got
        truth = len(case["expected"])
        returned += len(case["expected"] & got)
        expected += truth
        dropped += bool(missing)
        is_short = bool(missing)
        short += is_short
        flagged = (not r["completeness_check"]["all_counts_match"]
                   or r["completeness_check"]["warnings"])
        warned_when_short += bool(is_short and flagged)
        rows.append([case["drug"][:20], truth, r["inventory_count"], len(got),
                     "yes" if r["completeness_check"]["all_counts_match"] else "NO",
                     ", ".join(sorted(missing))[:26] or "-"])

    rule("Chapter 10's protocol, per document")
    table(["drug", "really present", "model's inventory", "extracted",
           "self-check says match", "actually missing"], rows)

    headline("Dose figures returned", pct(returned, expected),
             "fixed.py's lighter instruction returned 96% on the same documents.")
    headline("Documents where something was silently dropped", pct(dropped, len(cases)),
             "Silently means the self-check did not flag it.")
    headline("Model's inventory count that matched the real count",
             pct(sum(1 for c, r in zip(cases, results)
                     if r["inventory_count"] == len(c["expected"])), len(cases)),
             "Step 1 is the foundation the whole protocol rests on.")
    headline("Documents short where the self-check raised a flag",
             pct(warned_when_short, short) if short else "no document was short",
             "This is the only thing Step 3 is for.")
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
