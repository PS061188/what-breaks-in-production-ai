"""Corpus and scoring for Chapter 8 — routing and placement errors.

Three sections of a drug label go in; three boxes come out. Each box has
exactly one section that can legitimately fill it:

    what_it_treats        <- indications_and_usage
    who_must_not_take_it  <- contraindications
    side_effects          <- adverse_reactions

These three are close enough in subject matter to be confusable and far enough
apart in meaning that confusing them is dangerous. A condition listed under
"indications" is one the drug is *for*; the same condition under
"contraindications" is one the drug must *not* be given for. Same words,
opposite instruction.

Ground truth needs no annotation. Every section is labelled in the text the
model is given, and the model reports which section each quote came from. If a
quote for `who_must_not_take_it` is really in the indications section, the code
can see that without anyone judging it.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.llm import load_labels  # noqa: E402
from shared.scoring import quote_supported  # noqa: E402

SECTION_CHARS = 2200

# (box, the one section that can fill it)
BOXES = [
    ("what_it_treats", "indications_and_usage"),
    ("who_must_not_take_it", "contraindications"),
    ("side_effects", "adverse_reactions"),
]

SECTIONS = [section for _, section in BOXES]
BOX_LIST = ", ".join(box for box, _ in BOXES)


def build_cases(limit: int = 0) -> list:
    cases = []
    for label in load_labels():
        if not all(s in label["sections"] for s in SECTIONS):
            continue  # a label missing one of the three cannot test placement
        parts, texts = [], {}
        for section in SECTIONS:
            text = label["sections"][section][:SECTION_CHARS]
            texts[section] = text
            parts.append(f"[{section}]\n{text}")
        cases.append({"drug": label["drug"], "context": "\n\n".join(parts), "sections": texts})
        if limit and len(cases) >= limit:
            break
    return cases


def locate(quote: str, sections: dict):
    """Which labelled section this quote actually came from, if any.

    Deterministic: the quote is matched against each section's text
    independently. Nothing here asks a model where the quote belongs.
    """
    for name, text in sections.items():
        if quote_supported(quote, text):
            return name
    return None


def canonical_section(name: str) -> str:
    """Normalise a section name the model wrote back.

    The model returns the header as it appears in the document — "ADVERSE
    REACTIONS" — while the corpus keys are "adverse_reactions". Comparing those
    raw makes every answer look like a mismatch. This is a measurement bug that
    would have produced a dramatic and completely false finding, and it is the
    reason to inspect a few raw responses before trusting a rate.
    """
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def score(case: dict, result: dict) -> list:
    """One row per box: where the quote should have come from, and where it did."""
    rows = []
    for box, expected in BOXES:
        field = result[box]
        found = locate(field.get("source_quote") or "", case["sections"])
        rows.append(
            {
                "drug": case["drug"],
                "box": box,
                "expected_section": expected,
                "actual_section": found,
                "claimed_section": canonical_section(field.get("source_section")),
                "value": field.get("value") or "",
                "misplaced": found is not None and found != expected,
                "unlocatable": found is None,
            }
        )
    return rows
