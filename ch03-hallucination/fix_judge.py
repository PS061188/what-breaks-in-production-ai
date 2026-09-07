"""Chapter 3, engineering fix: LLM-as-judge hallucination detector.

The book: *"Run a secondary, cheaper model call with the source documents and
the generated answer: 'Does this answer introduce any facts not present in the
sources? List them.'"*

Run as a **pre-delivery gate**, not a post-hoc audit — which is what makes its
cost and latency matter. Every answer pays for it, not a sampled 10%.

Two departures from the book's wording, both deliberate:

- **The judge is a different, stronger model.** The chapter's own rule is that a
  model cannot verify its own output. Generator is Haiku 4.5; judge defaults to
  Sonnet 5. "Cheaper" is the wrong axis when the judge's job is to catch what
  the generator could not see.
- **It sees the sources.** A judge shown only the answer agrees with it — a
  fabricated line reads perfectly well on its own.

Scored against ground truth, so this reports precision as well as recall. A
detector that flags everything is not a detector.

    python fix_judge.py                       # replay
    python fix_judge.py --live                # re-run (costs money, see the footer)
    python fix_judge.py --live --judge-model claude-opus-5
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broken import SCHEMA, SOFT_INFERENCE  # noqa: E402
from common import build_cases  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

JUDGE_SYSTEM = """You are auditing an assistant's answer for grounding.

You will be shown the SOURCES the assistant was given and the ANSWER it
produced. Decide whether the answer asserts any factual claim that is not
supported by the sources.

Judge grounding, not correctness. A claim can be true in the world and still be
unsupported here — that is exactly what you are looking for. Hedging does not
excuse a claim: "the sources do not cover this, however X is typically Y"
asserts X.

List every unsupported claim you find. If there are none, return an empty list."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string", "enum": ["GROUNDED", "UNGROUNDED"]},
    },
    "required": ["unsupported_claims", "verdict"],
    "additionalProperties": False,
}


def main() -> int:
    parser = base_args(__doc__)
    parser.add_argument(
        "--judge-model",
        default="claude-sonnet-5",
        help="model that audits the answer (default: claude-sonnet-5, not the generator)",
    )
    args = parser.parse_args()

    # The generator always replays. This gate audits the exact answers broken.py
    # measured — regenerating them would move the baseline underneath the
    # detector and make the two runs incomparable.
    generator = LLM(Path(__file__).parent, model=args.model, live=False)
    judge = LLM(Path(__file__).parent, model=args.judge_model, live=args.live)
    cases = build_cases(limit=args.limit)

    rows = []
    caught = missed = false_alarm = correct_pass = 0

    for case in cases:
        answer = generator.json(
            system=SOFT_INFERENCE.format(context=case["context"]),
            user=case["question"],
            schema=SCHEMA,
            max_tokens=800,
        )["answer"]

        audit = judge.json(
            system=JUDGE_SYSTEM,
            user=f"SOURCES:\n{case['context']}\n\nQUESTION:\n{case['question']}\n\nANSWER:\n{answer}",
            schema=JUDGE_SCHEMA,
            max_tokens=1000,
        )
        flagged = audit["verdict"] == "UNGROUNDED"

        if case["answerable"]:
            # Ground truth: the sources cover this. Flagging it is a false alarm.
            false_alarm += int(flagged)
            correct_pass += int(not flagged)
            outcome = "FALSE ALARM" if flagged else "passed"
        else:
            caught += int(flagged)
            missed += int(not flagged)
            outcome = "caught" if flagged else "MISSED"

        rows.append(
            [
                case["drug"][:20],
                case["needed_section"][:20],
                "in context" if case["answerable"] else "NOT in context",
                outcome,
                len(audit["unsupported_claims"]),
            ]
        )

    rule("Per question")
    table(["drug", "section needed", "available?", "judge", "claims flagged"], rows)

    headline(
        "Recall — ungrounded answers the judge caught",
        pct(caught, caught + missed),
        "Ground truth is the corpus: these questions need a section that was "
        "never supplied, so any assertion is ungrounded by construction.",
    )
    headline(
        "Precision cost — grounded answers wrongly flagged",
        pct(false_alarm, false_alarm + correct_pass),
        "Every one of these is a good answer sent to human review. A gate with a "
        "high false-alarm rate does not get left switched on.",
    )

    print()
    generator.report("generator")
    judge.report("judge")
    total_cost = generator.cost() + judge.cost()
    total_time = (generator.api_seconds + judge.api_seconds) if args.live else (
        generator.recorded_seconds + judge.recorded_seconds
    )
    n = len(cases)
    print(
        f"  [gate cost] ${total_cost:.4f} for {n} answers"
        f"  ·  ${total_cost / n:.5f} per answer audited"
        f"  ·  {total_time / n:.2f}s added latency per answer",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
