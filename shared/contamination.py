"""Which withheld topics the supplied context already covers.

Chapters 3 and 9 both derive their ground truth the same way: hand the model two
sections of a label, ask about six, and treat the four withheld sections as
unanswerable. That holds only if the two supplied sections say nothing about the
withheld topics — and on real FDA labels they sometimes do. Levothyroxine's
`dosage_and_administration` section carries a full paediatric dosing table under
its own heading. A model that answers the paediatric question from that table is
reading the document correctly, and scoring it as fabrication is wrong.

The test below is structural, not interpretive: it looks for an explicit
subsection heading naming the withheld topic inside the supplied text. It does
not read for meaning, and it does not ask a model. That keeps the chapter's
ground truth a property of the corpus rather than a judgement call.

Deliberately narrow. A passage that discusses children without a heading that
says so is not caught here, so the contaminated set is a floor. The effect of
that is to leave some contamination in place, which understates the correction —
the safe direction.
"""

import re

# One pattern per withheld topic. Each matches a heading, not prose: either a
# canonical FDA subsection title, or the topic word in a position only a heading
# occupies.
TOPIC_HEADINGS = {
    "pediatric_use": r"\b(?:Pediatric|Paediatric)\s+(?:Patients|Use|Population)\b",
    "pregnancy": r"\bPregnan(?:cy|t)\s+(?:Patients|Women|Use)\b|\bPregnancy\b(?=\s*[:—-])",
    "drug_interactions": r"\bDrug\s+Interactions?\b|\bConcomitant\s+(?:Use|Medications?|Therapy)\b",
    "adverse_reactions": r"\bAdverse\s+Reactions?\b|\bSide\s+Effects?\b",
    "overdosage": r"\bOverdosage\b|\bOverdose\b(?=\s*[:—-])",
}


def covered_topics(sections: dict, context_sections: list) -> set:
    """Withheld topics that the supplied sections carry an explicit heading for."""
    supplied = "\n".join(sections.get(name) or "" for name in context_sections)
    if not supplied.strip():
        return set()
    return {
        topic
        for topic, pattern in TOPIC_HEADINGS.items()
        if topic not in context_sections and re.search(pattern, supplied)
    }
