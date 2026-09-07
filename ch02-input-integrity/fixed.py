"""Chapter 2, the fix: validate the bytes before you pay for a model call.

The gate is in common.py and contains no model call at all. It answers four
questions about the text — is it too short, does it stop mid-sentence, does it
carry characters an English clinical document should not contain, does it look
like a scan that went wrong — and returns a reason for each failure.

Anything that fails goes to a dead-letter queue with its reason attached, and
never reaches the model. That is the chapter's point: an input that was never
fit to process should be rejected at the door, not diagnosed afterwards from a
strange answer.

    python fixed.py             # replay
    python fixed.py --live      # re-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broken import SCHEMA, SYSTEM  # noqa: E402
from common import build_cases, validate  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, normalise_ws, pct, rule, table  # noqa: E402


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    dead_letter, processed = [], {}
    calls_avoided = 0

    for case in cases:
        reasons = validate(case["text"])
        if reasons:
            dead_letter.append([case["drug"][:18], case["mode"], "; ".join(reasons)[:62]])
            calls_avoided += 1
            continue
        processed[(case["drug"], case["mode"])] = llm.json(
            system=SYSTEM.format(text=case["text"]),
            user="What is the starting dose?",
            schema=SCHEMA,
            max_tokens=500,
        )

    damaged = [c for c in cases if c["damaged"]]
    clean = [c for c in cases if not c["damaged"]]
    caught = sum(1 for c in damaged if validate(c["text"]))
    false_alarms = sum(1 for c in clean if validate(c["text"]))

    silent = 0
    survivors = []
    for case in damaged:
        result = processed.get((case["drug"], case["mode"]))
        reference = processed.get((case["drug"], "clean"))
        if result is None or reference is None:
            continue
        if normalise_ws(result["starting_dose"]) != normalise_ws(reference["starting_dose"]):
            silent += 1
            survivors.append([case["drug"][:18], case["mode"],
                              result["starting_dose"][:40].replace("\n", " ")])

    rule("Dead-letter queue — rejected before any model call")
    table(["drug", "damage", "why it was rejected"], dead_letter[:20])
    if len(dead_letter) > 20:
        print(f"... and {len(dead_letter) - 20} more")

    if survivors:
        rule("Damage that got through the gate and still changed the answer")
        table(["drug", "damage", "answer stored"], survivors)

    headline("Damaged inputs stopped at the gate", pct(caught, len(damaged)))
    headline(
        "Clean inputs wrongly rejected",
        pct(false_alarms, len(clean)),
        "The price of the gate. Every one is a good document a human now has to "
        "look at.",
    )
    headline(
        "Silent corruptions that survived",
        pct(silent, len(damaged)),
        "Compare with broken.py. What remains is the damage the cheap checks "
        "cannot see.",
    )
    headline(
        "Model calls avoided",
        str(calls_avoided),
        "The gate is not only a quality control. It is the cheapest part of the "
        "pipeline refusing to pay the most expensive part.",
    )
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
