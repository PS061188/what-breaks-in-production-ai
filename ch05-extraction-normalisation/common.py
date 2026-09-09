"""Corpus, shared schema, and the specificity checks for Chapter 5.

The source is the DOSAGE AND ADMINISTRATION section of a real FDA label. That
text is written to be precise: ranges rather than points, conditions on when to
adjust, words like "initial", "maintenance", "individualized", "gradually". The
question the chapter asks is whether that precision survives extraction.

Every check in this file is ordinary string matching against the source. No
model is asked whether the output looks right.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.llm import load_labels  # noqa: E402
from shared.scoring import normalise_ws, quote_supported  # noqa: E402

# Some labels carry tens of thousands of characters of dosing text. Truncate to
# a consistent excerpt so the experiment is the same size for every drug — and
# so every check runs against exactly what the model was shown.
EXCERPT_CHARS = 3500

# Words that narrow a dosing instruction. The list is not exhaustive and is not
# meant to be; it was built by grepping the corpus for the hedges and range
# markers that are actually present. Only terms found in a given source count
# towards that source's score.
QUALIFIER_STEMS = [
    "may vary",
    "initial",
    "maintenance",
    "individualiz",
    "gradual",
    "depending on",
    "not to exceed",
    "approximately",
    "as needed",
    "divided doses",
    "titrat",
    "taper",
    "decrement",
    "if necessary",
    "up to",
    "at least",
    "in response",
]

# A dose range: two figures with a dose unit attached to at least one of them.
# The unit is required. Without it the pattern also matched INR target ranges
# ("range, 2 to 3"), dosing intervals ("every 4 to 6 hours"), ages ("ages 6-12")
# and time-to-effect ("1 to 4 days") — on three of the twelve labels every match
# was one of those, so the document was recorded as containing a dose range it
# does not contain, and an extraction that correctly carried no range was scored
# as having lost one.
RANGE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?)\s*(?:to|-|–|—)\s*\d+"
    r"|\d+(?:\.\d+)?\s*(?:to|-|–|—)\s*\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?)\b",
    re.I,
)

# Both scripts return this shape. Holding the schema constant means the measured
# difference is attributable to the prompt and to what runs after the call —
# not to one script having somewhere to put a qualifier and the other not.
SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {"type": "string"},
                    "qualifiers": {"type": "array", "items": {"type": "string"}},
                    "source_quote": {"type": "string"},
                },
                "required": ["field", "value", "qualifiers", "source_quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["fields"],
    "additionalProperties": False,
}

FIELDS_ASKED = "starting_dose, maximum_dose, frequency, dose_adjustment"


def build_cases(limit: int = 0) -> list:
    cases = []
    for label in load_labels():
        text = label["sections"].get("dosage_and_administration")
        if not text:
            continue
        cases.append({"drug": label["drug"], "source": text[:EXCERPT_CHARS]})
        if limit and len(cases) >= limit:
            break
    return cases


def captured_blob(result: dict) -> str:
    """The values themselves — what a downstream table would actually store.

    Deliberately excludes source_quote. Both scripts are required to return a
    quote, so a source_quote long enough to contain the whole instruction would
    let an output score well on specificity it did not actually capture. The
    stored value is the thing under test.
    """
    parts = []
    for field in result["fields"]:
        parts.append(field.get("value", ""))
        parts.extend(field.get("qualifiers", []))
    return " | ".join(parts)


def qualifiers_in(text: str) -> set:
    lowered = normalise_ws(text)
    return {stem for stem in QUALIFIER_STEMS if stem in lowered}


def score_case(case: dict, result: dict) -> dict:
    """Deterministic measures of whether specificity survived into the value."""
    source = case["source"]
    blob = captured_blob(result)

    present = qualifiers_in(source)
    retained = present & qualifiers_in(blob)

    source_ranges = bool(RANGE_RE.search(source))
    output_ranges = bool(RANGE_RE.search(blob))

    values = [f["value"] for f in result["fields"]]
    # A value that can be found in the source is one you can still audit. A
    # value the model rewrote on the way out is one you cannot check without
    # re-reading the document by hand.
    verbatim = [v for v in values if quote_supported(v, source)]

    quotes = [f["source_quote"] for f in result["fields"]]
    verified_quotes = [q for q in quotes if quote_supported(q, source)]

    return {
        "drug": case["drug"],
        "qualifiers_present": len(present),
        "qualifiers_retained": len(retained),
        "qualifiers_lost": sorted(present - retained),
        "range_in_source": source_ranges,
        "range_in_output": output_ranges,
        "values": len(values),
        "values_verbatim": len(verbatim),
        "quotes": len(quotes),
        "quotes_verified": len(verified_quotes),
    }


def summarise(scores: list) -> dict:
    with_range = [s for s in scores if s["range_in_source"]]
    return {
        "qualifiers_present": sum(s["qualifiers_present"] for s in scores),
        "qualifiers_retained": sum(s["qualifiers_retained"] for s in scores),
        "docs_with_range": len(with_range),
        "docs_range_preserved": len([s for s in with_range if s["range_in_output"]]),
        "values": sum(s["values"] for s in scores),
        "values_verbatim": sum(s["values_verbatim"] for s in scores),
        "quotes": sum(s["quotes"] for s in scores),
        "quotes_verified": sum(s["quotes_verified"] for s in scores),
    }
