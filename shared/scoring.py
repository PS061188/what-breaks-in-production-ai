"""Deterministic checks and the result table.

Nothing here calls a model. Every function is ordinary code you can unit-test,
which is the point Chapter 5 makes about normalisation and Chapter 9 makes
about quote verification: the check that matters is the one you can run.
"""

import re
import sys
from difflib import SequenceMatcher
from typing import Iterable, Optional

try:
    from rapidfuzz import fuzz

    _HAVE_RAPIDFUZZ = True
except ImportError:  # pragma: no cover - fallback path
    _HAVE_RAPIDFUZZ = False


def normalise_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _partial_ratio_fallback(needle: str, haystack: str) -> float:
    """Stand-in for rapidfuzz.fuzz.partial_ratio when rapidfuzz isn't installed.

    Exact substring scores 100; otherwise score by the longest contiguous run
    of the quote that appears in the document. Close enough to separate "this
    quote is in the document" from "the model wrote this quote itself", which
    is the only decision it is used for.
    """
    if not needle:
        return 0.0
    if needle in haystack:
        return 100.0
    matcher = SequenceMatcher(None, needle, haystack, autojunk=False)
    match = matcher.find_longest_match(0, len(needle), 0, len(haystack))
    return 100.0 * match.size / len(needle)


# Verify a bounded prefix of the quote rather than the whole thing. See the
# note under quote_supported() — this is not a detail, it is the difference
# between the check working and the check eating your recall.
VERIFY_WINDOW = 80


def quote_score(quote: Optional[str], document: str, window: int = VERIFY_WINDOW) -> float:
    """0-100: how well `quote` matches some span of `document`.

    `window` caps how much of the quote is compared. Pass 0 to compare all of it.
    """
    if not quote:
        return 0.0
    needle, haystack = normalise_ws(quote), normalise_ws(document)
    if window:
        needle = needle[:window]
    if _HAVE_RAPIDFUZZ:
        return float(fuzz.partial_ratio(needle, haystack))
    return _partial_ratio_fallback(needle, haystack)


def quote_supported(
    quote: Optional[str],
    document: str,
    threshold: float = 85.0,
    window: int = VERIFY_WINDOW,
) -> bool:
    """Does this quote actually exist in the source?

    Chapter 9 gives this check as `rapidfuzz.fuzz.partial_ratio > 85`. Run
    literally, on the whole quote, that rule does not work — and the failure is
    not obvious from reading it.

    partial_ratio scores the needle against the best-matching window of the
    haystack *of the needle's own length*, so its tolerance for small
    differences shrinks as the quote grows. A 600-character quote that dropped
    three words scores in the 60s and gets rejected. Measured on this corpus,
    verifying whole quotes at threshold 85 nulled 42 points of legitimate recall
    (96% -> 54%) to buy 8 points of fabrication.

    Verifying the first `VERIFY_WINDOW` characters instead keeps recall at 95%
    and still rejects invented quotes, which cannot match on their opening
    either. Sweep in ch09-sparse-field-fabrication/README.md.
    """
    return quote_score(quote, document, window=window) >= threshold


def contains_phrase(haystack: str, phrase: str) -> bool:
    """Whitespace- and case-insensitive substring test."""
    return normalise_ws(phrase) in normalise_ws(haystack)


# --- reporting ---------------------------------------------------------------


def rule(title: str = "") -> None:
    if title:
        print(f"\n{title}\n{'-' * len(title)}")
    else:
        print("-" * 60)


def table(headers: Iterable[str], rows: Iterable[Iterable[object]]) -> None:
    headers = list(headers)
    rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for row in rows:
        print(fmt.format(*row))


def headline(metric: str, value: str, note: str = "") -> None:
    line = f"\n>> {metric}: {value}"
    if note:
        line += f"\n   {note}"
    print(line)


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{100.0 * numerator / denominator:.0f}% ({numerator}/{denominator})"


def warn(message: str) -> None:
    print(f"[note] {message}", file=sys.stderr)
