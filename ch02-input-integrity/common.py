"""Corpus and corruption for Chapter 2 — input integrity failures.

Every other chapter feeds the model clean text. This one damages it first, in
the specific ways real pipelines damage text, and asks what the system does
when the input was never fit to process.

The damage is **deterministic**. Given the same document and the same seed, the
same characters are mangled every time — so the experiment is reproducible and,
more importantly, we know exactly what was broken and can therefore say exactly
what the pipeline should have caught.

Four corruption modes, each drawn from something that really happens:

  ocr          Character confusions a scanner makes: rn->m, 0<->O, l<->1, cl->d.
               The output is still readable English, which is why it survives.
  unicode      Cyrillic and Greek lookalikes substituted for Latin letters, plus
               non-breaking spaces and smart quotes. Looks identical on screen;
               breaks every exact-match rule you have.
  truncated    The document cut off mid-sentence, as happens when an upstream
               field has a length cap nobody documented.
  mojibake     UTF-8 read as Latin-1 — the classic "â€™" for an apostrophe.

`clean` is the control.
"""

import hashlib
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.llm import load_labels  # noqa: E402

EXCERPT = 1800

MODES = ["clean", "ocr", "unicode", "truncated", "mojibake"]

# Cyrillic/Greek homoglyphs. These render identically to their Latin twins in
# almost every font, which is the entire problem.
CONFUSABLES = {"a": "а", "e": "е", "o": "о", "p": "р",
               "c": "с", "y": "у", "x": "х", "i": "і"}

OCR_SWAPS = [("rn", "m"), ("m", "rn"), ("0", "O"), ("O", "0"),
             ("l", "1"), ("1", "l"), ("cl", "d"), ("5", "S")]


def _rng(seed: str):
    """A tiny deterministic generator — no random module, no seeding worries."""
    state = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % (2 ** 64)
        yield state / (2 ** 64)


def corrupt(text: str, mode: str, seed: str) -> str:
    if mode == "clean":
        return text
    if mode == "truncated":
        return text[: int(len(text) * 0.45)]
    if mode == "mojibake":
        return text.encode("utf-8").decode("latin-1", errors="replace")

    rng = _rng(seed + mode)
    out = []
    if mode == "unicode":
        for ch in text:
            if ch.lower() in CONFUSABLES and next(rng) < 0.08:
                out.append(CONFUSABLES[ch.lower()])
            elif ch == " " and next(rng) < 0.05:
                out.append(" ")  # non-breaking space
            else:
                out.append(ch)
        return "".join(out)

    # ocr
    i = 0
    while i < len(text):
        replaced = False
        if next(rng) < 0.06:
            for src, dst in OCR_SWAPS:
                if text.startswith(src, i):
                    out.append(dst)
                    i += len(src)
                    replaced = True
                    break
        if not replaced:
            out.append(text[i])
            i += 1
    return "".join(out)


def build_cases(limit: int = 0) -> list:
    """One case per (drug, corruption mode). Ground truth is the mode itself."""
    cases = []
    labels = load_labels()
    for label in labels:
        text = label["sections"].get("dosage_and_administration", "")[:EXCERPT]
        # Cut at a sentence boundary. Without this every excerpt ends
        # mid-sentence by construction, the truncation check fires on the clean
        # control too, and the experiment measures nothing.
        cut = text.rfind(". ")
        if cut > 600:
            text = text[: cut + 1]
        if len(text) < 500:
            continue
        for mode in MODES:
            damaged_text = corrupt(text, mode, label["drug"])
            # A corruption that changed nothing is not a corruption. Mojibake is
            # a no-op on a pure-ASCII document, and counting those as "damage the
            # gate failed to catch" would understate the gate for a reason that
            # has nothing to do with the gate.
            if mode != "clean" and damaged_text == text:
                continue
            cases.append(
                {
                    "drug": label["drug"],
                    "mode": mode,
                    "damaged": mode != "clean",
                    "text": damaged_text,
                }
            )
        if limit and len({c["drug"] for c in cases}) >= limit:
            break
    return cases


# --- the pre-flight gate ------------------------------------------------------
# This is Chapter 2's fix, and none of it is a model call. Each check answers a
# single question about the bytes, and each returns a reason a human can act on.

NON_ASCII_LETTER = re.compile(r"[^\x00-\x7f]")
GARBLE = re.compile(r"[ÃÂ¢€™â][^\s]{0,3}")


def validate(text: str):
    """Return a list of reasons this input should not be processed."""
    reasons = []

    if len(text) < 900:
        reasons.append("suspiciously short — possible truncation upstream")
    if text and not text.rstrip().endswith((".", ")", ":", ";")):
        reasons.append("ends mid-sentence")

    # Unicode normalisation as a hard gate, per the chapter. NFKC folds
    # compatibility forms; anything non-ASCII that survives in what should be an
    # English clinical document is a confusable or an encoding artefact.
    normalised = unicodedata.normalize("NFKC", text)
    foreign = NON_ASCII_LETTER.findall(normalised)
    if len(foreign) > len(text) * 0.004:
        reasons.append(f"{len(foreign)} non-ASCII characters in an English document")

    if GARBLE.search(text):
        reasons.append("mojibake signature — UTF-8 read as Latin-1")

    # OCR confusion leaves words that are not words. A dictionary check is
    # overkill; digits welded into alphabetic tokens are a cheap, specific tell.
    mixed = re.findall(r"\b(?=[a-zA-Z]*\d)(?=\d*[a-zA-Z])[a-zA-Z\d]{4,}\b", text)
    mixed = [w for w in mixed if not re.fullmatch(r"\d+\s*(mg|mcg|ml|g)", w, re.I)]
    if len(mixed) > 3:
        reasons.append(f"{len(mixed)} alphanumeric-mixed tokens — OCR damage likely")

    return reasons
