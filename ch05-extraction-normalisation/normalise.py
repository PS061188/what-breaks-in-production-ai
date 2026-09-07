"""Normalisation as ordinary, testable code — the second half of the Chapter 5 fix.

The model captured what the document said. This converts it. Two rules the
chapter insists on, both visible below:

1. The raw value is kept alongside the normalised one. If the mapping turns out
   to be wrong, every affected record is re-derivable without going back to the
   source document.
2. When the target shape cannot hold something, the mapping records that it
   discarded it. Silently returning the nearest value is how a lossy row stays
   invisible for two years.

Run it directly to see the unit tests pass:  python normalise.py
"""

import re
from typing import Dict, List, Optional, Tuple

TO_MG = {"mg": 1.0, "milligram": 1.0, "milligrams": 1.0, "mcg": 0.001, "g": 1000.0, "gram": 1000.0}

RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|milligrams?|grams?)?\s*(?:to|-|–|—)\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g|milligrams?|grams?)?",
    re.I,
)
SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|milligrams?|grams?)", re.I)

# Order matters: "twice daily" also contains "daily", so the more specific
# patterns have to be tried first. The unit test at the bottom of this file
# exists because the obvious ordering-free version of this list silently
# reported every twice-daily dose as once daily.
_TIMES = r"\s+(?:a\s+|per\s+)?(?:day|daily)"
PER_DAY = [
    (r"\bq\.?i\.?d\.?\b|four times" + _TIMES, 4),
    (r"\bt\.?i\.?d\.?\b|three times" + _TIMES, 3),
    (r"\bb\.?i\.?d\.?\b|twice" + _TIMES + r"|two times" + _TIMES, 2),
    (r"\bq\.?d\.?\b|once" + _TIMES + r"|\bdaily\b", 1),
]
EVERY_N_HOURS_RE = re.compile(r"every\s+(\d+)\s*(?:to\s*\d+\s*)?hours?", re.I)


def normalise_dose(raw: str) -> Tuple[Optional[Dict], List[str]]:
    """Return (normalised, discarded).

    `discarded` names every part of the input the normalised form cannot hold.
    An empty list means the conversion was lossless.
    """
    discarded: List[str] = []
    text = (raw or "").strip()
    if not text:
        return None, ["empty value"]

    match = RANGE_RE.search(text)
    if match:
        low, low_unit, high, high_unit = match.groups()
        unit = (high_unit or low_unit or "mg").lower()
        factor = TO_MG.get(unit, TO_MG.get(unit.rstrip("s"), 1.0))
        normalised = {"min_mg": float(low) * factor, "max_mg": float(high) * factor}
    else:
        match = SINGLE_RE.search(text)
        if not match:
            # No number and unit at all. Do not guess — say so and keep the raw text.
            return None, [f"no parsable dose in {text!r}"]
        amount, unit = match.groups()
        factor = TO_MG.get(unit.lower(), TO_MG.get(unit.lower().rstrip("s"), 1.0))
        value = float(amount) * factor
        normalised = {"min_mg": value, "max_mg": value}

    # Anything in the raw text outside the numbers we parsed is meaning the two
    # float fields cannot carry. Record it rather than dropping it.
    remainder = RANGE_RE.sub(" ", text) if RANGE_RE.search(text) else SINGLE_RE.sub(" ", text)
    remainder = re.sub(r"[^A-Za-z ]", " ", remainder)
    remainder = " ".join(w for w in remainder.split() if len(w) > 2)
    if remainder:
        discarded.append(f"qualifying text not representable in min_mg/max_mg: {remainder!r}")

    normalised["raw_text"] = text  # rule 1: never store the derived value alone
    return normalised, discarded


def normalise_frequency(raw: str) -> Tuple[Optional[Dict], List[str]]:
    discarded: List[str] = []
    text = (raw or "").strip()
    if not text:
        return None, ["empty value"]

    hours = EVERY_N_HOURS_RE.search(text)
    if hours:
        per_day = round(24 / int(hours.group(1)))
        if "to" in text.lower():
            discarded.append(f"interval was a range; kept the shorter end from {text!r}")
        return {"per_day": per_day, "raw_text": text}, discarded

    for pattern, per_day in PER_DAY:
        if re.search(pattern, text, re.I):
            conditional = re.search(r"\b(if|when|unless|as needed|prn)\b", text, re.I)
            if conditional:
                discarded.append(f"conditional dropped from frequency: {text!r}")
            return {"per_day": per_day, "raw_text": text}, discarded

    return None, [f"unrecognised frequency {text!r} — left unnormalised rather than guessed"]


def _test() -> None:
    dose, lost = normalise_dose("5 mg to 60 mg per day")
    assert dose["min_mg"] == 5 and dose["max_mg"] == 60, dose
    assert dose["raw_text"] == "5 mg to 60 mg per day"
    assert lost, "a range with trailing words should report what it dropped"

    dose, lost = normalise_dose("500mg")
    assert dose["min_mg"] == dose["max_mg"] == 500
    assert lost == []

    dose, lost = normalise_dose("2 g")
    assert dose["min_mg"] == 2000

    dose, lost = normalise_dose("individualized based on response")
    assert dose is None and lost, "unparsable input must not become a number"

    freq, lost = normalise_frequency("twice daily")
    assert freq["per_day"] == 2 and lost == []

    freq, lost = normalise_frequency("every 6 hours")
    assert freq["per_day"] == 4

    freq, lost = normalise_frequency("twice daily if morning readings stay high")
    assert freq["per_day"] == 2 and lost, "the condition is the instruction; log its loss"

    freq, lost = normalise_frequency("as directed by physician")
    assert freq is None and lost

    print("normalise.py: all checks passed")


if __name__ == "__main__":
    _test()
