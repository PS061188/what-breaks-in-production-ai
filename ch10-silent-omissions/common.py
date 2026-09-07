"""Corpus and ground truth for Chapter 10 — silent omissions.

Every other chapter asks whether what came out is right. This one asks whether
all of it came out, which needs a different instrument: an independent count of
what was in the document, made without asking the model.

The countable thing here is dose figures. A dosing section states a fixed set of
them — "20 mg", "2.5 mg", "80 mg" — and a regular expression finds every one
exactly. No annotation, no judgement, no second model. If the source contains
eleven distinct dose figures and the extraction returns six, five were dropped,
and nothing in the extraction says so.

The book's version of this check uses a named-entity model to produce the
independent count. A regular expression stands in for it here because dose
figures have a rigid shape and the substitution keeps the repo free of a
500 MB download. The principle is identical and it is the principle that
matters: **the second count must not come from the thing being checked.**
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.llm import load_labels  # noqa: E402

# Long enough to be a realistic document rather than a snippet. The first run
# used 2,600 characters and returned every figure from every document — which
# says more about the size of the excerpt than about the model. Omission is a
# load failure; testing it on short text tests nothing.
EXCERPT = 12000

# A number followed by a dose unit. Deliberately strict: it is better for the
# reference count to miss an unusual form than to invent one, because a
# reference count that is too high reports omissions that did not happen.
DOSE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|units?)\b", re.I)


# Identifiers that look like doses. "VKORC1-1639G > A" is a gene variant; the
# regex above reads it as 1639 grams. A reference count that is too high invents
# omissions that never happened — which is worse than one that is too low,
# because it produces a finding rather than a gap. This exclusion exists because
# that is precisely what happened on the first run.
IDENTIFIER_BEFORE = re.compile(r"[A-Z]{2,}[0-9]*[\u2212\-]?$")
FOLLOWED_BY_COMPARISON = re.compile(r"^\s*[><=]")


def dose_figures(text: str) -> set:
    """Every distinct dose figure in the text, normalised for comparison."""
    found = set()
    for match in DOSE.finditer(text):
        amount, unit = match.group(1), match.group(2)
        if IDENTIFIER_BEFORE.search(text[max(0, match.start() - 12) : match.start()]):
            continue
        if FOLLOWED_BY_COMPARISON.match(text[match.end() : match.end() + 4]):
            continue
        amount = amount.rstrip("0").rstrip(".") if "." in amount else amount
        found.add(f"{amount} {unit.lower().rstrip('s')}")
    return found


def build_cases(limit: int = 0) -> list:
    cases = []
    for label in load_labels():
        text = label["sections"].get("dosage_and_administration", "")[:EXCERPT]
        cut = text.rfind(". ")
        if cut > 800:
            text = text[: cut + 1]
        expected = dose_figures(text)
        # A document with almost nothing to count cannot demonstrate omission.
        if len(expected) < 6:
            continue
        cases.append({"drug": label["drug"], "text": text, "expected": expected})
        if limit and len(cases) >= limit:
            break
    return cases


def score(case: dict, returned: list) -> dict:
    """Compare what was returned against the independent count."""
    got = set()
    for item in returned:
        got |= dose_figures(str(item))
    expected = case["expected"]
    missed = expected - got
    return {
        "drug": case["drug"],
        "expected": len(expected),
        "returned": len(got & expected),
        "missed": sorted(missed),
        "invented": sorted(got - expected),
    }
