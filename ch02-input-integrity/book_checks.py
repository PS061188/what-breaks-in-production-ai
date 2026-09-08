"""The four pre-flight checks Chapter 2 actually prescribes, measured.

The chapter tells the reader to run four checks before any model call:
language sanity via langdetect, character-level entropy, token count bounds, and
required field presence via a Pydantic validator. The gate measured elsewhere in
this repository is a *different* five checks, so the 85% catch rate published for
this section belongs to something the section does not describe.

This script closes that gap. Each prescribed check is implemented on its own and
run over the same 53 cases, so the chapter's own advice gets a number.

    python3 book_checks.py            # no model calls, no API key, deterministic
"""

import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases, validate  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

EXPECTED_LANGUAGE = "en"
MIN_TOKENS = 250          # the corpus excerpts run 400-600 tokens
MAX_TOKENS = 8000


def check_language(text: str):
    """Chapter 2, check 1: 'use langdetect to verify the input is in the
    language your system expects'."""
    from shared.deps import require

    require("langdetect", "langdetect", "Chapter 2's language-sanity check")
    from langdetect import detect, DetectorFactory, LangDetectException

    DetectorFactory.seed = 0  # langdetect is stochastic without this
    try:
        found = detect(text)
    except LangDetectException:
        return "langdetect could not identify a language"
    return None if found == EXPECTED_LANGUAGE else f"language detected as {found!r}"


def char_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def check_entropy(text: str, low: float, high: float):
    """Chapter 2, check 2: 'an entropy check flags inputs where the character
    distribution looks wrong'."""
    h = char_entropy(text)
    if h < low:
        return f"character entropy {h:.2f} below {low}"
    if h > high:
        return f"character entropy {h:.2f} above {high}"
    return None


def check_tokens(text: str):
    """Chapter 2, check 3: 'token count bounds'."""
    from shared.deps import require

    require("tiktoken", "tiktoken", "Chapter 2's token-count check")
    import tiktoken

    n = len(tiktoken.get_encoding("cl100k_base").encode(text))
    if n < MIN_TOKENS:
        return f"{n} tokens, below the {MIN_TOKENS} expected"
    if n > MAX_TOKENS:
        return f"{n} tokens, above the {MAX_TOKENS} limit"
    return None


def main() -> int:
    cases = build_cases()
    clean = [c for c in cases if c["mode"] == "clean"]
    damaged = [c for c in cases if c["mode"] != "clean"]

    # Calibrate the entropy band on the CLEAN documents only. Choosing it after
    # seeing the damaged ones would be fitting the check to the answer.
    clean_h = [char_entropy(c["text"]) for c in clean]
    lo, hi = min(clean_h) - 0.15, max(clean_h) + 0.15
    rule(f"Entropy band calibrated on clean documents only: {lo:.2f} – {hi:.2f}")

    checks = {
        "1 · language sanity (langdetect)": check_language,
        "2 · character entropy": lambda t: check_entropy(t, lo, hi),
        "3 · token count bounds": check_tokens,
    }

    rows = []
    for name, fn in checks.items():
        caught = sum(1 for c in damaged if fn(c["text"]))
        false_alarm = sum(1 for c in clean if fn(c["text"]))
        rows.append([name, pct(caught, len(damaged)), pct(false_alarm, len(clean))])

    # The union of the three testable prescribed checks.
    def prescribed(t):
        return [r for r in (fn(t) for fn in checks.values()) if r]

    rows.append([
        "ALL THREE TOGETHER",
        pct(sum(1 for c in damaged if prescribed(c["text"])), len(damaged)),
        pct(sum(1 for c in clean if prescribed(c["text"])), len(clean)),
    ])
    rows.append([
        "the gate this repo actually built",
        pct(sum(1 for c in damaged if validate(c["text"])), len(damaged)),
        pct(sum(1 for c in clean if validate(c["text"])), len(clean)),
    ])
    rule("Each prescribed check, on its own, over the same 53 cases")
    table(["check", "damaged caught", "clean wrongly rejected"], rows)

    rule("Which damage each prescribed check can see")
    modes = sorted({c["mode"] for c in damaged})
    by_mode = [
        [name] + [pct(sum(1 for c in damaged if c["mode"] == m and fn(c["text"])),
                      sum(1 for c in damaged if c["mode"] == m)) for m in modes]
        for name, fn in checks.items()
    ]
    by_mode.append(["the gate this repo built"] + [
        pct(sum(1 for c in damaged if c["mode"] == m and validate(c["text"])),
            sum(1 for c in damaged if c["mode"] == m)) for m in modes])
    table(["check"] + modes, by_mode)

    headline(
        "Check 4 — required field presence",
        "not applicable to this corpus",
        "Pydantic field validation guards a structured payload. The input here is "
        "raw document text with no fields to be absent, so there is nothing for "
        "the check to inspect. It is sound advice for API-shaped inputs and it "
        "cannot be scored on this one.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
