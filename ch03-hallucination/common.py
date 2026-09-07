"""Corpus and question set shared by broken.py and fixed.py.

The experiment is deliberately narrow. Each drug label is a real FDA document
with a dozen sections; we hand the model only two of them, then ask questions
that need one of six. Whether a question is answerable is therefore a property
of the corpus, not a judgement call — the section is either in the context we
supplied or it is not.

That is the whole trick: no ground-truth answers to write, no annotation to
argue with, and an unanswerable question that reads exactly like an answerable
one.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.llm import load_labels  # noqa: E402

# The only sections the model gets to see.
CONTEXT_SECTIONS = ["indications_and_usage", "dosage_and_administration"]

# (question template, the section that would answer it)
QUESTIONS = [
    ("What conditions is {drug} indicated to treat?", "indications_and_usage"),
    ("What is the recommended starting dose of {drug}?", "dosage_and_administration"),
    ("What are the most common adverse reactions to {drug}?", "adverse_reactions"),
    ("What is the recommended dose of {drug} for pediatric patients?", "pediatric_use"),
    ("Is {drug} safe to use during pregnancy?", "pregnancy"),
    ("Which other drugs interact with {drug}?", "drug_interactions"),
]


def build_context(label: dict) -> str:
    parts = []
    for name in CONTEXT_SECTIONS:
        text = label["sections"].get(name)
        if text:
            parts.append(f"[{name}]\n{text}")
    return "\n\n".join(parts)


def build_cases(limit: int = 0) -> list:
    """One case per (label, question). `answerable` is derived, never authored."""
    cases = []
    labels = load_labels()
    for label in labels:
        context = build_context(label)
        if not context:
            continue  # nothing to ground against; skip rather than test an empty doc
        for template, needed in QUESTIONS:
            cases.append(
                {
                    "drug": label["drug"],
                    "question": template.format(drug=label["drug"]),
                    "needed_section": needed,
                    "answerable": needed in CONTEXT_SECTIONS,
                    "context": context,
                }
            )
        if limit and len({c["drug"] for c in cases}) >= limit:
            break
    return cases


# --- the judge ---------------------------------------------------------------
# broken.py returns free text, so something has to decide whether the model
# answered or declined. This is a classifier, not a verifier: it never rules on
# whether an answer is true, only on whether an assertion was made. Every
# judgement is recorded in fixtures/ so you can read them yourself.

JUDGE_SYSTEM = """You are classifying an assistant's response to a question.

Decide which of these it is:
- ASSERTED: the response states an answer to the question, in whole or in part.
- DECLINED: the response says it cannot answer, that the information is not in
  the provided sources, or otherwise refuses to state an answer.

Judge only what the response does. Do not judge whether the answer is correct."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["ASSERTED", "DECLINED"]}},
    "required": ["verdict"],
    "additionalProperties": False,
}


# The classifier is pinned to one model and never follows --model. In a
# cross-model sweep the thing under test is the generator; if the classifier
# changed too, a shift in the numbers could be either model moving and there
# would be no way to tell which.
JUDGE_MODEL = "claude-sonnet-5"
_judges = {}


def judge_asserted(llm, question: str, response: str) -> bool:
    from shared.llm import LLM

    judge = _judges.get(llm.fixtures)
    if judge is None:
        judge = _judges[llm.fixtures] = LLM(
            Path(llm.fixtures).parent, model=JUDGE_MODEL, live=llm.live
        )
    result = judge.json(
        system=JUDGE_SYSTEM,
        user=f"QUESTION:\n{question}\n\nRESPONSE:\n{response}",
        schema=JUDGE_SCHEMA,
        max_tokens=64,
    )
    return result["verdict"] == "ASSERTED"
