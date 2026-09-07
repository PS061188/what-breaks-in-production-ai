"""Chapter 3, the baseline: a helpful assistant with a source document.

Two prompts, both of which people actually ship.

  neutral         Supplies the source, says to use it, and says nothing about
                  what to do when the source does not cover the question.
  soft-inference  The same, plus the language Chapter 3 warns about — "relevant",
                  "complete", "draw on standard knowledge where the excerpt is
                  thin". This is not a strawman. It is what a prompt drifts into
                  after the first round of "the assistant is being unhelpful"
                  feedback.

Running both is the point. On a current model the neutral prompt often declines
on its own, and it is the soft-inference wording that produces the failure — so
the interesting result is the gap between the two, not either number alone.

    python broken.py                        # replay both, free
    python broken.py --live                 # re-run against the API
    python broken.py --prompt soft-inference
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases, judge_asserted  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

NEUTRAL = """You are a helpful clinical information assistant. Answer the user's
question about the drug, using the label excerpt provided below.

<label>
{context}
</label>"""

SOFT_INFERENCE = """You are a clinical information assistant supporting busy
prescribers. Be helpful and complete. Give the clinician the relevant clinical
guidance they need, drawing on the label excerpt below and on standard
pharmacology where the excerpt is thin. A useful, complete answer is what
matters.

<label>
{context}
</label>"""

SOFT_WORDS_ONLY = """You are a clinical information assistant supporting busy
prescribers. Be helpful and complete. Give the clinician the relevant clinical
guidance they need, based on the label excerpt below. A useful, complete answer
is what matters.

<label>
{context}
</label>"""

BASELINES = {
    "neutral": NEUTRAL,
    "soft-words": SOFT_WORDS_ONLY,
    "soft-inference": SOFT_INFERENCE,
}

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def run_baseline(llm, cases, system_template, name, show_rows):
    rows = []
    fabricated = unanswerable = answered_ok = answerable = 0

    def one(case):
        result = llm.json(
            system=system_template.format(context=case["context"]),
            user=case["question"],
            schema=SCHEMA,
            max_tokens=800,
        )
        return result, judge_asserted(llm, case["question"], result["answer"])

    # Every question is independent of every other, so there is no reason to
    # wait for one before starting the next. This is the difference between a
    # ten-minute run and a two-minute one, at identical cost.
    for case, (result, asserted) in zip(cases, map_parallel(one, cases)):
        if case["answerable"]:
            answerable += 1
            answered_ok += int(asserted)
            verdict = "answered" if asserted else "MISSED"
        else:
            unanswerable += 1
            fabricated += int(asserted)
            verdict = "FABRICATED" if asserted else "declined"

        rows.append(
            [
                case["drug"][:22],
                case["needed_section"],
                "in context" if case["answerable"] else "NOT in context",
                verdict,
                result["answer"][:64].replace("\n", " "),
            ]
        )

    if show_rows:
        rule(f"Per question — {name} prompt")
        table(["drug", "section needed", "available?", "outcome", "answer (first 64 chars)"], rows)

    return {
        "name": name,
        "fabricated": fabricated,
        "unanswerable": unanswerable,
        "answered_ok": answered_ok,
        "answerable": answerable,
    }


def main() -> int:
    parser = base_args(__doc__)
    parser.add_argument(
        "--prompt",
        choices=["neutral", "soft-words", "soft-inference", "all"],
        default="all",
        help="which baseline prompt to run (default: all)",
    )
    args = parser.parse_args()

    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)
    names = list(BASELINES) if args.prompt == "all" else [args.prompt]

    results = [
        run_baseline(llm, cases, BASELINES[n], n, show_rows=len(names) == 1) for n in names
    ]

    rule("Summary")
    table(
        ["prompt", "fabricated on unanswerable", "answered on answerable"],
        [
            [
                r["name"],
                pct(r["fabricated"], r["unanswerable"]),
                pct(r["answered_ok"], r["answerable"]),
            ]
            for r in results
        ],
    )

    worst = max(results, key=lambda r: r["fabricated"])
    headline(
        f"Fabrication rate, {worst['name']} prompt",
        pct(worst["fabricated"], worst["unanswerable"]),
        "Read the answers, not just the number. The characteristic shape is a caveat "
        "followed by an assertion: 'the excerpt does not cover this, however...'. "
        "The caveat is what makes it survive review.",
    )
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
