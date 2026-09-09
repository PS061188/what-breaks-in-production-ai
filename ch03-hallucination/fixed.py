"""Chapter 3, the fix: grounded generation plus enforcement in code.

Two changes from broken.py, and they are not the same kind of change:

1. The prompt (the book's grounding template) tells the model to cite every
   claim and gives it a way to return nothing.
2. The code after the call checks that it did. A claim with no citation is
   rejected. A citation whose quote is not in the source document is rejected.
   Neither check asks the model's permission.

The second one is the durable half. Run with --model claude-opus-5 and you will
see the prompt do more of the work; run it against a weaker model and the code
is what is still standing.

    python fixed.py             # replay the recorded run, free
    python fixed.py --live      # re-run against the API
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, note, pct, quote_supported, rule, table  # noqa: E402

# Adapted from the Chapter 3 prompt template. The wording is the book's; the
# citation shape is bound to the schema below so the model cannot cite loosely.
SYSTEM = """You are a research assistant. Your answers must be GROUNDED — every
factual claim must trace to the provided source document. You are NOT allowed to
use prior knowledge to fill gaps.

GROUNDING RULES (non-negotiable):
1. Only assert facts that appear verbatim or by clear implication in <sources>.
2. For every factual claim, cite the source by quoting the exact supporting text.
3. If a question cannot be answered from the sources, set "answerable" to false
   and "answer" to null. That is a correct and expected outcome, not a failure.
4. Never extrapolate or "complete the pattern" from partial data.
5. Anything you are unsure the sources support goes in "unverified_claims"
   rather than into the answer.

SELF-CHECK BEFORE RESPONDING:
Go through each sentence of your draft answer and ask: can I point to a specific
passage in <sources> that supports this? If no, remove it.

<sources>
{context}
</sources>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "answer": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["claim", "quote"],
                "additionalProperties": False,
            },
        },
        "unverified_claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answerable", "answer", "citations", "unverified_claims"],
    "additionalProperties": False,
}


def enforce(result: dict, context: str):
    """The gate that runs whatever the model said.

    Returns (accepted_answer_or_None, reason). Nothing here is a prompt
    instruction; all of it is a check the pipeline can fail.
    """
    if not result["answerable"] or not result["answer"]:
        return None, "declined"

    if not result["citations"]:
        # The book's rule: a factual claim arriving with no citation is rejected
        # rather than logged. Silently accepting it is how the prompt becomes
        # decorative.
        return None, "REJECTED no citation"

    verified = [c for c in result["citations"] if quote_supported(c["quote"], context)]
    if not verified:
        return None, "REJECTED quote not in source"

    if len(verified) < len(result["citations"]):
        return result["answer"], f"accepted ({len(verified)}/{len(result['citations'])} quotes verified)"

    return result["answer"], "accepted"


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    rows = []
    fabricated = 0
    unanswerable = 0
    answered_ok = 0
    answerable = 0
    rejected_by_code = 0
    flagged_claims = 0
    contaminated = contaminated_answered = 0

    for case in cases:
        result = llm.json(
            system=SYSTEM.format(context=case["context"]),
            user=case["question"],
            schema=SCHEMA,
            # A grounded answer carries its citations with it, so it needs more
            # room than the baseline's bare answer. 1200 truncated mid-quote on
            # the longer labels.
            max_tokens=3000,
        )
        answer, reason = enforce(result, case["context"])
        rejected_by_code += int(reason.startswith("REJECTED"))
        flagged_claims += len(result["unverified_claims"])

        if case["answerable"]:
            answerable += 1
            answered_ok += int(answer is not None)
            available = "in context"
        elif case["contaminated"]:
            # Answerable from the supplied text after all. Recorded, not scored.
            contaminated += 1
            contaminated_answered += int(answer is not None)
            available = "COVERED anyway"
        else:
            unanswerable += 1
            fabricated += int(answer is not None)
            available = "NOT in context"

        rows.append(
            [
                case["drug"][:22],
                case["needed_section"],
                available,
                reason,
                len(result["citations"]),
            ]
        )

    rule("Per question")
    table(["drug", "section needed", "available?", "outcome", "citations"], rows)

    headline(
        "Fabrication rate on questions the sources cannot answer",
        pct(fabricated, unanswerable),
        "Compare with broken.py. The remainder, if any, is what the prompt did not "
        "catch and the citation check could not reject.",
    )
    note(
        f"{contaminated} questions are excluded from that denominator: the withheld "
        "section's topic carries its own heading inside the supplied text, so an "
        f"answer there is grounded, not fabricated. The model answered "
        f"{contaminated_answered} of {contaminated} of them."
    )
    headline("Answered correctly when the sources did cover it", pct(answered_ok, answerable),
             "Watch this one. A grounding fix that also stops answering answerable "
             "questions has not improved anything.")
    headline("Answers rejected by code, not by the model", str(rejected_by_code),
             "These are the ones the prompt alone would have let through.")
    headline("Claims the model flagged as unverified", str(flagged_claims),
             "Chapter 3: these route to human review, never to the user.")
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
