"""Corpus, field list, and the absence predicate for Chapter 9.

A real FDA label has a dozen or so sections, and which sections a given product
carries varies. Prednisone's label has no pediatric-use section. Sertraline's
has no pregnancy section. That is real sparseness in a real document, not a gap
somebody manufactured for a demo.

Each run hands the model two sections and asks for six fields. Four of the six
have no source content. The correct answer for those four is nothing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.contamination import covered_topics  # noqa: E402
from shared.llm import load_labels  # noqa: E402
from shared.scoring import normalise_ws  # noqa: E402

CONTEXT_SECTIONS = ["indications_and_usage", "dosage_and_administration"]

# (field name, the label section that would supply it)
FIELDS = [
    ("indications", "indications_and_usage"),
    ("adult_dosage", "dosage_and_administration"),
    ("pediatric_dosage", "pediatric_use"),
    ("pregnancy_guidance", "pregnancy"),
    ("overdose_management", "overdosage"),
    ("drug_interactions", "drug_interactions"),
]

FIELD_LIST = ", ".join(name for name, _ in FIELDS)

# A value counts as "the model declined" if it is boilerplate filler or an
# explicit statement of absence. The list is deliberately generous — anything
# ambiguous is scored in the model's favour, so the fabrication rate reported is
# a floor, not a ceiling. Every value is printed in the per-field table so you
# can check the calls yourself.
FILLER = [
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "not applicable",
    "not specified",
    "not stated",
    "not provided",
    "not mentioned",
    "not included",
    "not available",
    "not addressed",
    "not found",
    "not discussed",
    "not described",
    "not documented",
    "no information",
    "to be determined",
    "tbd",
    "-",
    "",
]

ABSENCE_MARKERS = [
    "not specified",
    "not stated",
    "not provided",
    "not mentioned",
    "not included",
    "not available",
    "not addressed",
    "not found",
    "not discussed",
    "not described",
    "not contain",
    "does not",
    "no information",
    "no pediatric",
    "no specific",
    "not in the",
    "cannot be determined",
]


def is_absent_answer(value) -> bool:
    """True when the model returned nothing, filler, or an explicit 'not here'."""
    if value is None:
        return True
    text = normalise_ws(str(value)).rstrip(".")
    if text in FILLER:
        return True
    return any(marker in text for marker in ABSENCE_MARKERS)


def build_context(label: dict) -> str:
    parts = []
    for name in CONTEXT_SECTIONS:
        text = label["sections"].get(name)
        if text:
            parts.append(f"[{name}]\n{text[:3000]}")
    return "\n\n".join(parts)


def section_texts(label: dict) -> dict:
    """The same sections, kept separately so a quote can be located in one.

    Chapter 8 measured how often the model names the wrong section for its own
    quote: about one time in five, even when the content itself was placed
    correctly. A check that trusts that name is trusting an unreliable witness.
    Keeping the sections apart lets the code find the quote itself.
    """
    return {
        name: label["sections"][name][:3000]
        for name in CONTEXT_SECTIONS
        if label["sections"].get(name)
    }


def build_cases(limit: int = 0) -> list:
    cases = []
    for label in load_labels():
        context = build_context(label)
        if not context:
            continue
        cases.append(
            {
                "drug": label["drug"],
                "context": context,
                "section_texts": section_texts(label),
                # Derived from the label itself. Nothing here was hand-labelled.
                "present": {name: (section in CONTEXT_SECTIONS) for name, section in FIELDS},
                # Fields whose section was withheld but whose topic carries its
                # own heading inside the supplied text. Filling those is reading,
                # not fabricating, so they are recorded and not scored. See
                # shared/contamination.py.
                "covered_anyway": {
                    name: (
                        section not in CONTEXT_SECTIONS
                        and section in covered_topics(label["sections"], CONTEXT_SECTIONS)
                    )
                    for name, section in FIELDS
                },
            }
        )
        if limit and len(cases) >= limit:
            break
    return cases
