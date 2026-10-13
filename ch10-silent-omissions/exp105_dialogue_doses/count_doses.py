"""Experiment 10.4, step 1: the reference extractor.

Finds every medication-dose mention (number + mass/unit word) in the 60
ACI-Bench dialogues, in digit form ("20 mg", "81 milligrams", "50,000 units")
and word form ("twenty milligrams", "a thousand milligrams", "seven and a
half milligrams", "a twenty one milligram", "six hundred six hundred
milligrams" — a speech stutter that still means 600).

A dose needs a mass/unit word: mg / milligram(s) / mcg / microgram(s) /
g / gram(s) / unit(s). Numbers without one ("lisinopril 20", "2000s on the
other six days", "1 milliliter") are NOT extracted — counted separately as
a caveat.

Exclusions, each one printed with its reason so the call can be audited:
  - "per deciliter" within 30 chars after the unit  -> lab concentration
  - grams with amount > 10                          -> tissue/body mass
  - word-form number attached to bare "g"           -> "a g cup" (bra size)
  - >= 1000 mg with salt/sodium/intake within 80ch  -> dietary sodium target

Run:  python3 count_doses.py          # prints every mention + summary
"""
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "aci_bench_dialogues.json"

UNIT_RX = r"(?:mg|milligrams?|mcg|micrograms?|grams?|g|units?)"
UNIT_CANON = {
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "mcg": "mcg", "microgram": "mcg", "micrograms": "mcg",
    "g": "g", "gram": "g", "grams": "g",
    "unit": "units", "units": "units",
}

ONES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9}
TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
         "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
        "seventy": 70, "eighty": 80, "ninety": 90}
NUMWORDS = set(ONES) | set(TEENS) | set(TENS) | {"hundred", "thousand", "a", "and", "point", "half", "zero", "oh"}

NUMWORD_RX = "|".join(sorted(NUMWORDS, key=len, reverse=True))
WORD_RX = re.compile(
    r"\b((?:(?:" + NUMWORD_RX + r")[-\s]+)*(?:" + NUMWORD_RX + r"))[-\s]+(" + UNIT_RX + r")\b")
DIGIT_RX = re.compile(r"(?<![\d.])(\d+(?:,\d{3})*(?:\.\d+)?)\s*-?\s*(" + UNIT_RX + r")\b")
# combined strengths in NOTES: "5/500 mg", "20/25-mg"
COMBO_RX = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*-?\s*(" + UNIT_RX + r")\b")


def parse_number_words(tokens):
    """Spoken-number parser. Returns the value of the LAST well-formed number
    in the token stream (handles stutters like 'six hundred six hundred').
    Returns None if nothing parses."""
    total = 0.0
    current = 0.0
    last_small = 0.0          # most recent ones/teens/tens increment
    seen_any = False
    frac = None               # list of decimal digit chars after "point"
    half_pending = False      # "and a half"

    def flush_ok():
        return seen_any

    i = 0
    while i < len(tokens):
        w = tokens[i]
        if frac is not None:
            d = {**ONES, **TEENS, "zero": 0, "oh": 0}.get(w)
            if d is not None and d <= 9:
                frac.append(str(d))
                i += 1
                continue
            frac = frac or ["0"]
            i += 1
            continue
        if w in ONES or w in TEENS:
            v = ONES.get(w) or TEENS[w]
            if current % 100 and (current % 100) < 20 or (w in TEENS and current % 100):
                # e.g. "five six" or "six hundred twelve five": restart
                total, current, last_small = 0.0, float(v), float(v)
            else:
                current += v
                last_small = float(v)
            seen_any = True
        elif w in TENS:
            v = TENS[w]
            if current % 100:
                total, current, last_small = 0.0, float(v), float(v)   # restart ("five twenty")
            else:
                current += v
                last_small = float(v)
            seen_any = True
        elif w == "hundred":
            if not seen_any:
                current, seen_any = 100.0, True      # "hundred and twenty"
            elif current >= 100 or current == 0:
                # stutter: "six hundred six hundred" -> restart with last small
                current = (last_small or 1.0) * 100.0
                total = 0.0
            else:
                current *= 100.0
        elif w == "thousand":
            if not seen_any:
                current, seen_any = 1000.0, True
            else:
                total += (current or 1.0) * 1000.0
                current = 0.0
        elif w == "a":
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            if nxt in ("hundred", "thousand") and not seen_any:
                current, seen_any = 1.0, True
                current = 100.0 if nxt == "hundred" else 1000.0
                i += 2
                continue
            if nxt == "half":
                half_pending = True
                i += 2
                continue
            if not seen_any and nxt == "":
                return None      # bare "a <unit>" — not a number ("a g cup")
            # article inside "a twenty one milligram": skip
        elif w == "and":
            pass                 # glue: "hundred and twenty", "seven and a half"
        elif w == "point":
            frac = []
            seen_any = True
        elif w == "half":
            half_pending = True
            seen_any = seen_any or False
        i += 1

    if not flush_ok() and not half_pending:
        return None
    value = total + current
    if frac:
        value += float("0." + "".join(frac))
    if half_pending:
        value += 0.5
    return value if value > 0 else None


def canon(amount: float, unit_token: str) -> str:
    unit = UNIT_CANON[unit_token.lower()]
    return f"{amount:g} {unit}"


SALT_RX = re.compile(r"\bsalt\b|\bsodium\b|\bintake\b")
PER_DL_RX = re.compile(r"^\s*(?:per\s+deciliter|per\s+dl|/\s*dl)")


def classify_exclusion(text, start, end, amount, unit):
    """Return a reason string if this mention is NOT a medication dose."""
    after = text[end:end + 30]
    around = text[max(0, start - 80):end + 80]
    if PER_DL_RX.match(after):
        return "lab concentration (per deciliter)"
    if unit == "g" and amount > 10:
        return "body/tissue mass in grams, not a dose"
    if unit == "mg" and amount >= 1000 and SALT_RX.search(around):
        return "dietary sodium target, not a medication dose"
    return None


def extract(text, permissive=False):
    """All dose mentions in text. permissive=True (note side) skips the
    dialogue exclusions and adds combined strengths (X/Y mg -> both).
    Returns list of dicts: raw, canonical, start, end, kind, excluded."""
    text = text.lower()
    out = []
    taken = []

    def overlaps(s, e):
        return any(s < e2 and e > s2 for s2, e2 in taken)

    for m in COMBO_RX.finditer(text):
        if not permissive:
            break
        a1, a2, unit = float(m.group(1)), float(m.group(2)), m.group(3)
        for a in (a1, a2):
            out.append(dict(raw=m.group(0), canonical=canon(a, unit),
                            start=m.start(), end=m.end(), kind="combo", excluded=None))
        taken.append((m.start(), m.end()))

    for m in DIGIT_RX.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        amount = float(m.group(1).replace(",", ""))
        unit = UNIT_CANON[m.group(2)]
        reason = None if permissive else classify_exclusion(text, m.start(), m.end(), amount, unit)
        out.append(dict(raw=m.group(0), canonical=canon(amount, m.group(2)),
                        start=m.start(), end=m.end(), kind="digit", excluded=reason))
        taken.append((m.start(), m.end()))

    for m in WORD_RX.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        unit_tok = m.group(2)
        if UNIT_CANON[unit_tok] == "g" and unit_tok == "g":
            if not permissive:
                out.append(dict(raw=m.group(0), canonical=None, start=m.start(), end=m.end(),
                                kind="word", excluded="bare letter 'g' after word-number (cup size etc.)"))
            continue
        tokens = re.split(r"[-\s]+", m.group(1).strip())
        amount = parse_number_words(tokens)
        if amount is None:
            continue
        reason = None if permissive else classify_exclusion(text, m.start(), m.end(), amount, UNIT_CANON[unit_tok])
        out.append(dict(raw=m.group(0), canonical=canon(amount, unit_tok),
                        start=m.start(), end=m.end(), kind="word", excluded=reason))
        taken.append((m.start(), m.end()))

    out.sort(key=lambda d: d["start"])
    return out


def dialogue_doses():
    """{(split, encounter_id): {"mentions": [...], "doses": {canonical: [contexts]}}}"""
    dialogues = json.loads(DATA.read_text())["dialogues"]
    result = {}
    for d in dialogues:
        txt = d["dialogue"].lower()
        mentions = extract(txt, permissive=False)
        doses = {}
        for m in mentions:
            if m["excluded"] or m["canonical"] is None:
                continue
            a, b = max(0, m["start"] - 110), min(len(txt), m["end"] + 110)
            doses.setdefault(m["canonical"], []).append(txt[a:b].replace("\n", " | "))
        result[(d["split"], d["encounter_id"])] = {"mentions": mentions, "doses": doses, "text": txt}
    return result


def main():
    data = dialogue_doses()
    n_digit = n_word = n_excl = 0
    dialogs_with = 0
    total_unique = 0
    for (split, enc), rec in data.items():
        kept = [m for m in rec["mentions"] if not m["excluded"] and m["canonical"]]
        excl = [m for m in rec["mentions"] if m["excluded"]]
        if not kept and not excl:
            continue
        print(f"\n=== {split} {enc}  ({len(rec['doses'])} unique doses)")
        for m in rec["mentions"]:
            txt = rec["text"]
            a, b = max(0, m["start"] - 70), min(len(txt), m["end"] + 70)
            ctx = txt[a:b].replace("\n", " | ")
            if m["excluded"]:
                n_excl += 1
                print(f"  [EXCLUDED: {m['excluded']}] «{m['raw']}»\n      …{ctx}…")
            else:
                if m["kind"] == "digit":
                    n_digit += 1
                else:
                    n_word += 1
                print(f"  [{m['kind'].upper()} -> {m['canonical']}] «{m['raw']}»\n      …{ctx}…")
        if kept:
            dialogs_with += 1
            total_unique += len(rec["doses"])
    print(f"\n==== kept mentions: {n_digit} digit-form, {n_word} word-form, "
          f"{n_excl} excluded, across {dialogs_with} of 60 dialogues; "
          f"{total_unique} unique (dialogue, dose) pairs")


if __name__ == "__main__":
    main()
