"""Wall-clock and footprint measurement for the local-compute fixes.

Some fixes in the book cost money (an API call per claim). Others cost machine
time and disk (a cross-encoder, a vector index). A reader deciding whether a
fix is affordable needs both numbers, and they do not trade off the same way:
API cost scales with volume forever, local compute is a fixed setup cost plus a
much cheaper marginal one.

Every timing printed by this repo is from one laptop — an Apple M-series CPU,
no GPU. Treat them as orders of magnitude, not benchmarks.
"""

import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict

_TIMINGS: Dict[str, float] = {}


@contextmanager
def stage(name: str):
    """Time a named stage. Nested calls are fine; each name accumulates."""
    started = time.monotonic()
    try:
        yield
    finally:
        _TIMINGS[name] = _TIMINGS.get(name, 0.0) + (time.monotonic() - started)


def timings() -> Dict[str, float]:
    return dict(_TIMINGS)


def dir_size_mb(path) -> float:
    path = Path(path)
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def report(extra: str = "") -> None:
    if not _TIMINGS:
        return
    parts = [f"{name} {seconds:.1f}s" for name, seconds in _TIMINGS.items()]
    line = "  [local compute]  " + "  ·  ".join(parts)
    if extra:
        line += "  ·  " + extra
    print(line, file=sys.stderr)
