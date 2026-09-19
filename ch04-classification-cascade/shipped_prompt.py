"""Chapter 4, the prompt as it ships in the book, measured as its own arm.

The book's template was measured with its confidence grade and
requires_human_review flag still in it, and lost to a one-line prompt: 97% vs
99% on opening passages, 91% vs 97% on body passages. The shipped template
drops those two fields and keeps the reasoning steps, runner_up and
ruled_out_because. Removing fields the model ignored should not move accuracy
— but that is an expectation, and a reader copies the shipped prompt, so it
gets its own measurement.

    python shipped_prompt.py                 # replay
    python shipped_prompt.py --live          # three runs, both positions, ~$2
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import (  # noqa: E402
    CATEGORIES, CATEGORY_BLOCK, blank_row, build_cases, classify_book,
    classify_naive, correct,
)
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import pct, rule, table  # noqa: E402

SHIPPED_SYSTEM = f"""You are a document classifier. Classification errors propagate to
extraction, routing and downstream processing, so accuracy and an honest
account of your reasoning are both required.

CATEGORIES:
{CATEGORY_BLOCK}

BEFORE STATING YOUR CLASSIFICATION:
1. List the 3 most prominent features of this document that inform
   classification.
2. Name the 2 categories that are most plausible, and why each is.
3. State which one wins, and what specifically ruled the other out.

OUTPUT FORMAT (strict JSON):
{{
  "reasoning": "<your step-by-step analysis>",
  "classification": "<CATEGORY>",
  "runner_up": "<the second most likely category>",
  "ruled_out_because": "<what decided it against the runner-up>"
}}

If the evidence genuinely does not separate the top two, say so in
"ruled_out_because" and put the weaker one in "runner_up" anyway. Do not
manufacture a distinction that is not in the document."""


def shipped_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string"},
            "classification": {"type": "string", "enum": CATEGORIES},
            "runner_up": {"type": "string", "enum": CATEGORIES},
            "ruled_out_because": {"type": "string"},
        },
        "required": ["reasoning", "classification", "runner_up", "ruled_out_because"],
        "additionalProperties": False,
    }


def classify_shipped(llm: LLM, case: dict, sample: int) -> dict:
    result = llm.json(
        system=SHIPPED_SYSTEM,
        user=f"<passage>\n{case['passage']}\n</passage>",
        schema=shipped_schema(),
        max_tokens=1200,
        sample=sample,
    )
    row = blank_row(case)
    row["classification"] = result["classification"]
    row["alternative_considered"] = result["runner_up"]
    return row


def summarise(rows):
    n = len(rows)
    right = sum(correct(r) for r in rows)
    errors = [r for r in rows if not correct(r)]
    recov = sum(r["alternative_considered"] == r["true_category"] for r in errors)
    return right, n, recov, len(errors)


def main() -> int:
    parser = base_args(__doc__)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)

    for position, label in (("first", "opening passages"), ("middle", "body passages")):
        cases = build_cases(limit=args.limit, position=position)
        rule(f"{label}: {len(cases)} passages")
        rows_out = []
        naive = map_parallel(lambda c: classify_naive(llm, c), cases)
        r, n, _, _ = summarise(naive)
        rows_out.append(["one-line prompt (replayed)", pct(r, n), "—"])
        book = map_parallel(lambda c: classify_book(llm, c), cases)
        r, n, rec, e = summarise(book)
        rows_out.append(["full template, with confidence fields (replayed)", pct(r, n), f"{rec}/{e}"])
        for k in range(1, args.runs + 1):
            rows = map_parallel(lambda c: classify_shipped(llm, c, k), cases)
            r, n, rec, e = summarise(rows)
            rows_out.append([f"shipped template, run {k}", pct(r, n), f"{rec}/{e}"])
        table(["prompt", "accuracy", "errors where runner_up was the true category"], rows_out)
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
