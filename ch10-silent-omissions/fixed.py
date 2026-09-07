"""Chapter 10, the fix — applied to a failure that did not occur.

The baseline returned every dose figure from every document, including one of
nearly twelve thousand characters. There is no omission here to fix.

So this script does something more useful than demonstrating an improvement it
cannot demonstrate. It runs the chapter's fixes anyway and reports what they
cost and what they catch when the model is already doing the job:

1. **An independent count**, made without the model, compared against what came
   back. On this corpus it agreed every time — and on an earlier run it caught a
   discrepancy that turned out to be a bug in the counting, not in the model.
2. **An explicit "what I did not extract" field**, which forces the model to
   state its own omissions rather than leaving a short list looking complete.
3. **A completeness audit**: a second call showing the source and the extraction
   and asking what is missing from it.

The last one is the expensive one, and measuring how much it finds when there is
nothing to find is exactly the number a team needs before switching it on for
every request.

    python fixed.py             # replay
    python fixed.py --live      # re-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases, dose_figures, score  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

SYSTEM = """You are a clinical data extraction assistant. List every dose amount
mentioned in the text below.

Completeness is the quality measure here, not brevity. Before you finish, count
the dose amounts in the source and check your list against that count.

If there is anything you did not extract — because it was ambiguous, because it
was not clearly a dose, or because you were unsure — put it in
`not_extracted` with a short reason. An empty list there is a claim that your
extraction is complete. Do not make that claim lightly.

<text>
{text}
</text>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "doses": {"type": "array", "items": {"type": "string"}},
        "not_extracted": {"type": "array", "items": {"type": "string"}},
        "source_count_claimed": {"type": "integer"},
    },
    "required": ["doses", "not_extracted", "source_count_claimed"],
    "additionalProperties": False,
}

AUDIT_SYSTEM = """You are auditing an extraction for completeness.

You will be shown a source text and a list of dose amounts extracted from it.
Name every dose amount that appears in the source but is missing from the list.
If none are missing, return an empty list. Do not list amounts that are already
in the extraction."""

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {"missing": {"type": "array", "items": {"type": "string"}}},
    "required": ["missing"],
    "additionalProperties": False,
}


def main() -> int:
    parser = base_args(__doc__)
    parser.add_argument("--audit-model", default="claude-sonnet-5",
                        help="model for the completeness audit (a different one, per the book)")
    args = parser.parse_args()

    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    auditor = LLM(Path(__file__).parent, model=args.audit_model, live=args.live)
    cases = build_cases(limit=args.limit)

    def extract(case):
        return llm.json(
            system=SYSTEM.format(text=case["text"]),
            user="List every dose amount mentioned in the text.",
            schema=SCHEMA,
            max_tokens=2000,
        )

    results = map_parallel(extract, cases)
    scores = [score(c, r["doses"]) for c, r in zip(cases, results)]

    def audit(pair):
        case, result = pair
        return auditor.json(
            system=AUDIT_SYSTEM,
            user=f"SOURCE:\n{case['text']}\n\nEXTRACTED:\n{', '.join(result['doses'])}",
            schema=AUDIT_SCHEMA,
            # Sonnet 5 reasons before answering, and that reasoning shares the
            # output budget. 1200 was not enough for a long source.
            max_tokens=4000,
        )

    audits = map_parallel(audit, list(zip(cases, results)))

    rows = []
    count_mismatch = audit_flags = false_flags = 0
    for case, result, s, a in zip(cases, results, scores, audits):
        independent = len(case["expected"])
        claimed = result["source_count_claimed"]
        mismatch = claimed != independent
        count_mismatch += int(mismatch)

        real_missing = [m for m in a["missing"] if dose_figures(m) & case["expected"]
                        and not (dose_figures(m) & dose_figures(" ".join(result["doses"])))]
        audit_flags += len(a["missing"])
        false_flags += len(a["missing"]) - len(real_missing)

        rows.append([
            case["drug"][:20], independent, claimed, "MISMATCH" if mismatch else "agrees",
            len(result["not_extracted"]), len(a["missing"]), len(real_missing),
        ])

    rule("Per document")
    table(
        ["drug", "independent count", "model's own count", "agree?",
         "self-declared gaps", "audit flagged", "genuinely missing"],
        rows,
    )

    expected = sum(s["expected"] for s in scores)
    returned = sum(s["returned"] for s in scores)

    headline("Dose figures returned", pct(returned, expected),
             "Unchanged from the baseline. There was no omission to fix.")
    headline(
        "Model's own count of the source vs the independent count",
        pct(len(scores) - count_mismatch, len(scores)),
        "The model counting the source itself is not an independent check — it is "
        "the same reader, counting twice. Where these disagree, only the outside "
        "count means anything.",
    )
    headline(
        "Items the expensive completeness audit flagged",
        str(audit_flags),
        f"of which genuinely missing: {audit_flags - false_flags}. Every false flag "
        "is a human sent to check something that was already correct.",
    )

    print()
    llm.report("extraction")
    auditor.report("completeness audit")
    total = llm.cost() + auditor.cost()
    print(f"  [audit overhead] ${auditor.cost():.4f} of ${total:.4f} total "
          f"({100 * auditor.cost() / total:.0f}% of the bill) to find "
          f"{audit_flags - false_flags} real omission(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
