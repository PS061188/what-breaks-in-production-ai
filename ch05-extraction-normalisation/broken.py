"""Chapter 5, the baseline: extract and normalise in one prompt.

The prompt asks for exactly what a downstream table wants — a number in
milligrams, a frequency per day, a tidy canonical value. It is a reasonable
request and the model complies. What it cannot do is comply without deciding
which parts of the source do not fit, and it makes those decisions silently.

Nothing here is fabricated, so a hallucination check passes. Nothing is
missing, so a coverage check passes. The output is simply less specific than
the source, and specificity was carrying the clinical instruction.

    python broken.py            # replay the recorded run, free
    python broken.py --live     # re-run against the API
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import FIELDS_ASKED, SCHEMA, build_cases, score_case, summarise  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

SYSTEM = """You are a clinical data extraction assistant. Extract the dosing
information from the label text below into clean, standardised, database-ready
values.

Standardise as you go:
- Doses as a number in milligrams.
- Frequency as the number of doses per day.
- Durations in days.
- One canonical value per field. Keep it tidy and consistent.

<label_text>
{source}
</label_text>"""

# The honest baseline. It asks for extraction and says nothing about how to
# render a value - no "standardise as you go", no "one canonical value", no
# "keep it tidy". Added after the Chapter 3 audit found that a baseline which
# instructs the failure measures compliance, not failure.
PLAIN = """You are a clinical data extraction assistant. Extract the dosing
information from the label text below.

<label_text>
{source}
</label_text>"""

PROMPTS = {"plain": PLAIN, "standardise": SYSTEM}


def main() -> int:
    parser = base_args(__doc__)
    parser.add_argument("--prompt", choices=["plain", "standardise", "both"],
                        default="both",
                        help="which baseline to run (default: both, so the "
                             "comparison is visible without extra flags)")
    args = parser.parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    names = ["plain", "standardise"] if args.prompt == "both" else [args.prompt]
    for name in names:
        run_arm(llm, cases, name)
    llm.report()
    return 0


def run_arm(llm, cases, name) -> None:
    scores = []
    for case in cases:
        result = llm.json(
            system=PROMPTS[name].format(source=case["source"]),
            user=f"Extract these fields: {FIELDS_ASKED}",
            schema=SCHEMA,
            max_tokens=1500,
        )
        scores.append(score_case(case, result))

    rule(f"Per document — {name} prompt")
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
        "A value the model rewrote on the way out cannot be audited without "
        "re-reading the document by hand. This is the property normalisation "
        "inside the prompt spends first.",
    )
    headline(
        "Qualifier retention in the stored value",
        pct(total["qualifiers_retained"], total["qualifiers_present"]),
        "Words in the source that narrow a dose — 'initial', 'maintenance', "
        "'individualized', 'not to exceed' — that survive into the value.",
    )
    headline(
        "Dose ranges preserved",
        pct(total["docs_range_preserved"], total["docs_with_range"]),
        "A source that says 5 mg to 60 mg and an output that says 40 is not a "
        "transcription error. It is a range collapsed to a point, and nothing "
        "in the pipeline recorded that it happened.",
    )
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
