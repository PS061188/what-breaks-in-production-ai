"""Chapter 10, the baseline: ask for a list, get a list, store the list.

The request is simple — list every dose figure the text mentions — and the
answer always looks complete. It is a list. Lists look finished.

Nothing in the output says how many there should have been, so nothing can say
how many are missing. That is what makes omission the quietest of the nine
failures: there is no wrong value to find, no fabricated claim to trace. There
is a shorter list than there should be, and it looks exactly like a correct one.

    python broken.py            # replay
    python broken.py --live     # re-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases, score  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

SYSTEM = """You are a clinical data extraction assistant. Read the dosing text
below and list the dose amounts it mentions.

<text>
{text}
</text>"""

SCHEMA = {
    "type": "object",
    "properties": {"doses": {"type": "array", "items": {"type": "string"}}},
    "required": ["doses"],
    "additionalProperties": False,
}


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    def one(case):
        return llm.json(
            system=SYSTEM.format(text=case["text"]),
            user="List every dose amount mentioned in the text.",
            schema=SCHEMA,
            max_tokens=1500,
        )

    scores = [score(c, r["doses"]) for c, r in zip(cases, map_parallel(one, cases))]

    rule("Per document")
    table(
        ["drug", "in the source", "returned", "missed", "examples of what was dropped"],
        [
            [s["drug"][:20], s["expected"], s["returned"], len(s["missed"]),
             ", ".join(s["missed"][:5])]
            for s in scores
        ],
    )

    expected = sum(s["expected"] for s in scores)
    returned = sum(s["returned"] for s in scores)
    incomplete = sum(1 for s in scores if s["missed"])

    headline(
        "Dose figures actually returned",
        pct(returned, expected),
        "Counted against a regular expression over the same text — an independent "
        "count the model had no part in.",
    )
    headline(
        "Documents where something was silently dropped",
        pct(incomplete, len(scores)),
        "Not one of these outputs said anything was missing. Every list looked "
        "complete, because a list always does.",
    )
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
