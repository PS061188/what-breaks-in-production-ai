"""Chapter 5, the fix: capture verbatim, then normalise in code.

The prompt's only job is to say what the document says and where it said it.
It is explicitly forbidden from tidying anything. The conversion to
database-ready values happens afterwards in normalise.py, which you can read,
unit-test, and — the part that matters — which records what it discarded.

Same output schema as broken.py, so the comparison is measuring the prompt and
the code, not the shape of the JSON.

    python fixed.py             # replay the recorded run, free
    python fixed.py --live      # re-run against the API
    python normalise.py         # the normaliser's own tests
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import FIELDS_ASKED, SCHEMA, build_cases, score_case, summarise  # noqa: E402
from normalise import normalise_dose, normalise_frequency  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

# Adapted from the Chapter 5 prompt template.
SYSTEM = """You are a precision data extractor. Capture what the document says.
Converting, standardising or tidying a value is a failure mode.

CAPTURE RULES — apply without exception:

DOSAGES:
  - Output number and unit exactly as written: "five hundred milligrams", "500mg",
    "5 mg to 60 mg"
  - Never collapse a range to a single number
  - Never supply a unit the text does not state

FREQUENCY AND DURATION:
  - Exactly as written: "every 6 to 8 hours", "for at least 10 days"
  - Do not convert to a count per day or a number of days

QUALIFIERS:
  - Capture any word that narrows a value: "initial", "maintenance",
    "individualized", "gradually", "not to exceed", "depending on the response"
  - Put every one you find in "qualifiers" — never drop it

For each field, output the value as written, the qualifiers attached to it, and
a source_quote copied character-for-character from the text below.

Do not output a normalised value. Normalisation runs after this step, in code.

<label_text>
{source}
</label_text>"""


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    scores = []
    discard_log = []

    for case in cases:
        result = llm.json(
            system=SYSTEM.format(source=case["source"]),
            user=f"Extract these fields: {FIELDS_ASKED}",
            schema=SCHEMA,
            max_tokens=1500,
        )
        scores.append(score_case(case, result))

        # Second half of the fix: convert in code, and record every loss.
        for field in result["fields"]:
            if "dose" in field["field"].lower():
                _, lost = normalise_dose(field["value"])
            elif "frequency" in field["field"].lower():
                _, lost = normalise_frequency(field["value"])
            else:
                continue
            for entry in lost:
                discard_log.append([case["drug"][:22], field["field"], entry[:80]])

    rule("Per document")
    table(
        ["drug", "values verbatim", "qualifiers kept", "range kept", "qualifiers dropped"],
        [
            [
                s["drug"][:22],
                f"{s['values_verbatim']}/{s['values']}",
                f"{s['qualifiers_retained']}/{s['qualifiers_present']}",
                "-" if not s["range_in_source"] else ("yes" if s["range_in_output"] else "NO"),
                ", ".join(s["qualifiers_lost"][:4]),
            ]
            for s in scores
        ],
    )

    total = summarise(scores)
    rule("Summary")
    headline(
        "Stored values still findable in the source",
        pct(total["values_verbatim"], total["values"]),
        "Compare with broken.py. Every value here can be traced back to the "
        "document without re-reading it.",
    )
    headline(
        "Qualifier retention in the stored value",
        pct(total["qualifiers_retained"], total["qualifiers_present"]),
    )
    headline("Dose ranges preserved", pct(total["docs_range_preserved"], total["docs_with_range"]))

    if discard_log:
        rule("What normalisation discarded (logged, not dropped)")
        table(["drug", "field", "discarded"], discard_log[:25])
        if len(discard_log) > 25:
            print(f"... and {len(discard_log) - 25} more")
        headline(
            "Losses recorded by the normaliser",
            str(len(discard_log)),
            "In broken.py these same losses happened inside the model call, where "
            "nothing recorded them. Here they are rows you can query.",
        )

    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
