"""Chapter 9, the baseline: every field is required, so every field gets filled.

The schema says each of the six fields is a string. The prompt offers "N/A" as
an escape hatch, which sounds like a licensed empty state and is not one — the
model still has to produce a string, and a plausible string is a better answer
than "N/A" by every instinct the model has.

Four of the six fields have no source content. Watch what arrives in them, and
watch the source_quote that arrives with it.

    python broken.py            # replay the recorded run, free
    python broken.py --live     # re-run against the API
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import FIELD_LIST, FIELDS, build_cases, is_absent_answer  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, quote_supported, rule, table  # noqa: E402

SYSTEM = """You are a clinical data extraction assistant. Extract the requested
fields from the drug label below into the schema. Include a short source_quote
for each field. If a field is not stated in the label, use "N/A".

<source_document>
{context}
</source_document>"""


def schema() -> dict:
    props = {}
    for name, _ in FIELDS:
        props[name] = {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "source_quote": {"type": "string"},
            },
            "required": ["value", "source_quote"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": props,
        "required": [name for name, _ in FIELDS],
        "additionalProperties": False,
    }


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    rows = []
    fabricated = absent_total = 0
    recalled = present_total = 0
    invented_quotes = 0

    for case in cases:
        result = llm.json(
            system=SYSTEM.format(context=case["context"]),
            user=f"Extract these fields: {FIELD_LIST}",
            schema=schema(),
            max_tokens=2000,
        )
        for name, _ in FIELDS:
            field = result[name]
            declined = is_absent_answer(field["value"])
            quote_ok = quote_supported(field["source_quote"], case["context"])

            if case["present"][name]:
                present_total += 1
                recalled += int(not declined)
                outcome = "extracted" if not declined else "MISSED"
            else:
                absent_total += 1
                if not declined:
                    fabricated += 1
                    invented_quotes += int(not quote_ok)
                    outcome = "FABRICATED"
                else:
                    outcome = "declined"

            if not case["present"][name]:
                rows.append(
                    [
                        case["drug"][:20],
                        name,
                        outcome,
                        "yes" if quote_ok else "NO",
                        str(field["value"])[:52].replace("\n", " "),
                    ]
                )

    rule("Fields with no source content (the correct answer is nothing)")
    table(["drug", "field", "outcome", "quote in doc?", "value (first 52 chars)"], rows)

    headline(
        "Fabrication rate on fields the document does not cover",
        pct(fabricated, absent_total),
        "Every one of these is a value a downstream system will store and a "
        "reviewer will read as extracted fact.",
    )
    headline(
        "Fabrications whose source_quote IS in the document",
        pct(fabricated - invented_quotes, fabricated) if fabricated else "n/a",
        "The uncomfortable number. These are not invented quotes — the text is "
        "really there, in a section that does not support the field it was "
        "attached to. Asking for a quote does not stop this, and neither does "
        "checking that the quote exists.",
    )
    headline("Recall on fields the document does cover", pct(recalled, present_total))
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
