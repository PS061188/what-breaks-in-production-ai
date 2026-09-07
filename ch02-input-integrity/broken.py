"""Chapter 2, the baseline: process whatever arrives.

No validation, no gate. Every document goes to the model, damaged or not, and
the model is asked for the starting dose. It answers every time.

The clean version of each document gives us the reference answer. A damaged
version that produces a different answer, with no complaint from anywhere in the
pipeline, is a silent corruption: a wrong value stored as a right one.

    python broken.py            # replay
    python broken.py --live     # re-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases, validate  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, normalise_ws, pct, rule, table  # noqa: E402

SYSTEM = """You are a clinical data extraction assistant. Read the dosing text
below and report the starting dose.

<text>
{text}
</text>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "starting_dose": {"type": "string"},
        "confident": {"type": "boolean"},
    },
    "required": ["starting_dose", "confident"],
    "additionalProperties": False,
}


def run(llm, cases):
    answers = {}
    for case in cases:
        result = llm.json(
            system=SYSTEM.format(text=case["text"]),
            user="What is the starting dose?",
            schema=SCHEMA,
            max_tokens=500,
        )
        answers[(case["drug"], case["mode"])] = result
    return answers


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)
    answers = run(llm, cases)

    rows = []
    silent = damaged = confident_on_damage = 0

    for case in cases:
        if not case["damaged"]:
            continue
        damaged += 1
        result = answers[(case["drug"], case["mode"])]
        reference = answers.get((case["drug"], "clean"))
        if reference is None:
            continue
        changed = normalise_ws(result["starting_dose"]) != normalise_ws(
            reference["starting_dose"]
        )
        confident_on_damage += int(result["confident"])
        if changed and result["confident"]:
            silent += 1
            rows.append(
                [
                    case["drug"][:18],
                    case["mode"],
                    "yes" if validate(case["text"]) else "no",
                    reference["starting_dose"][:26].replace("\n", " "),
                    result["starting_dose"][:26].replace("\n", " "),
                ]
            )

    rule("Damaged inputs that changed the answer, with no complaint from the pipeline")
    table(
        ["drug", "damage", "detectable?", "answer from clean text", "answer from damaged"],
        rows or [["—", "none", "", "", ""]],
    )

    headline(
        "Silent corruption rate",
        pct(silent, damaged),
        "A different value, stored with no error raised anywhere. Nothing in the "
        "output says the input was broken.",
    )
    headline(
        "Damaged inputs the model said it was confident about",
        pct(confident_on_damage, damaged),
        "Confidence is a property of the model, not of the input. Asking for it "
        "does not make it an input-quality signal.",
    )
    headline(
        "Model calls made on documents that should never have been processed",
        str(damaged),
        "Every one was paid for.",
    )
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
