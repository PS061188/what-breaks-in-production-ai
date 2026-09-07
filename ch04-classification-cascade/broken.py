"""Chapter 4, the baseline: the pipeline needs a label, so it gets one.

Two classifiers run over the same 96 passages:

  naive        "Classify this passage." No reasoning, no confidence.
  book prompt  Chapter 4's template verbatim — chain of thought, a confidence
               grade, a runner-up, and a requires_human_review flag.

The book-prompt labels are then handed to a downstream extraction stage, and
*nothing acts on requires_human_review*. That is the baseline, and it is not a
straw man: a pipeline with no human-review lane has nowhere to put a deferred
classification, so the flag is logged and the record proceeds. That is the state
the chapter describes.

Watch three things:

  1. how often the label is wrong,
  2. what confidence the model attached to the wrong ones,
  3. whether the downstream stage notices it is running on the wrong category.

    python broken.py                  # replay the recorded run, free
    python broken.py --live           # re-run against the API
    python broken.py --chunk middle   # passages from the body of each section
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import (  # noqa: E402
    build_cases,
    classify_book,
    classify_naive,
    report_audit_trail,
    report_cascade,
    report_classification,
    report_confidence,
    report_f1_gate,
    run_downstream,
)
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import rule  # noqa: E402


def add_chunk_args(parser):
    """Shared by broken.py and fixed.py so the two always run on the same input."""
    parser.add_argument(
        "--chunk",
        default="both",
        choices=["both", "first", "middle", "last"],
        help="which passage of each section to classify (default: both first and middle)",
    )
    return parser


def positions(choice: str) -> list:
    return ["first", "middle"] if choice == "both" else [choice]


def banner(position: str) -> None:
    where = {
        "first": "the OPENING of each section",
        "middle": "the BODY of each section",
        "last": "the END of each section",
    }[position]
    print(f"\n\n{'=' * 72}")
    print(f">> PASSAGES TAKEN FROM {where}  (chunk={position})")
    print("=" * 72)


def run_position(args, llm, position: str) -> None:
    cases = build_cases(limit=args.limit, position=position)
    banner(position)

    rule(f"Baseline 1 — naive classifier ({len(cases)} passages, chunk={position})")
    naive_rows = map_parallel(lambda c: classify_naive(llm, c), cases)
    report_classification(naive_rows, cases)

    rule("Baseline 2 — Chapter 4's prompt template, nothing gating on its output")
    book_rows = map_parallel(lambda c: classify_book(llm, c), cases)
    report_classification(book_rows, cases)

    rule("Is the confidence grade worth anything?")
    report_confidence(book_rows)
    report_audit_trail(book_rows)

    rule("Per-category F1 — Chapter 4 fix 3, on the book-prompt labels")
    report_f1_gate(book_rows)

    if not args.skip_downstream:
        rule("The cascade — the assigned category selects the downstream stage")
        by_id = {c["case_id"]: c for c in cases}
        book_rows = map_parallel(
            lambda r: run_downstream(llm, by_id[r["case_id"]], r), book_rows
        )
        report_cascade(book_rows)


def main() -> int:
    parser = add_chunk_args(base_args(__doc__))
    parser.add_argument(
        "--skip-downstream",
        action="store_true",
        help="classification only; the downstream stage is the expensive half",
    )
    args = parser.parse_args()

    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    for position in positions(args.chunk):
        run_position(args, llm, position)

    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
