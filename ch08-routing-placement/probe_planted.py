"""Chapter 8, probe: does the rules engine catch misplacement when it happens?

On these labels the model never misplaced anything (FINDINGS §3: the one
reported misplacement is a scoring artefact), so fixed.py's rules engine had
nothing to catch and its only action was a false rejection. That measures what
the check costs on clean traffic. It says nothing about what it catches.

This probe builds the failure on purpose, the way Chapter 6's context-integrity
test did. It replays the recorded, correct outputs and, by code, swaps the
quote and value between two boxes — a contraindication filed as an indication,
and so on — producing misplacements whose location is known. Then it runs the
same rules_engine() over them and counts:

  caught     planted misplacements the engine rejected
  missed     planted misplacements it accepted
  false      untouched boxes it rejected anyway

For each case, every pair of the three boxes is swapped once: 3 variants per
case, each with two planted misplacements and one untouched box.

The quote locator compares the first VERIFY_WINDOW characters (80 as shipped),
and those characters are drug-name boilerplate shared by every section, so the
probe repeats the count at 200 characters and on the whole quote. That is the
same window sweep FINDINGS §3 used, now pointed at recall instead of precision.

Usage:
  python probe_planted.py        # replay; no model calls at all
"""

import io
import sys
from contextlib import redirect_stdout
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import common  # noqa: E402
from common import BOXES, BOX_LIST, build_cases  # noqa: E402
from fixed import SYSTEM, rules_engine, schema  # noqa: E402
from shared import scoring  # noqa: E402
from shared.llm import LLM  # noqa: E402

WINDOWS = ((80, "80 characters (as shipped)"), (200, "200 characters"), (0, "whole quote"))


def replay_results(cases):
    llm = LLM(HERE, live=False)
    out = []
    for case in cases:
        with redirect_stdout(io.StringIO()):
            result = llm.json(
                system=SYSTEM.format(context=case["context"]),
                user=f"Fill in these fields: {BOX_LIST}",
                schema=schema(),
                max_tokens=2000,
            )
        out.append(result)
    return out


def plant(result: dict, a: str, b: str) -> dict:
    """Swap quote and value between boxes a and b. Both are now misplaced."""
    planted = {box: dict(field) for box, field in result.items()}
    for key in ("source_quote", "value"):
        planted[a][key], planted[b][key] = result[b].get(key), result[a].get(key)
    return planted


def run(cases, results, window: int):
    common.quote_supported = lambda q, t, threshold=85.0, w=window: scoring.quote_supported(q, t, threshold, w)
    boxes = [box for box, _ in BOXES]
    caught = missed = false = variants = 0
    reasons = {}
    for case, result in zip(cases, results):
        for a, b in combinations(boxes, 2):
            variants += 1
            planted = plant(result, a, b)
            _, rejected = rules_engine(case, planted)
            rejected_boxes = {box for box, _ in rejected}
            for box, reason in rejected:
                reasons[reason.split(",")[0]] = reasons.get(reason.split(",")[0], 0) + 1
            for box in (a, b):
                if box in rejected_boxes:
                    caught += 1
                else:
                    missed += 1
            (untouched,) = set(boxes) - {a, b}
            if untouched in rejected_boxes:
                false += 1
    return variants, caught, missed, false, reasons


def main() -> int:
    cases = build_cases()
    results = replay_results(cases)
    print(f"{len(cases)} cases replayed, {len(BOXES)} boxes each, "
          f"{len(cases) * 3} planted variants, {len(cases) * 6} planted misplacements\n")
    print(f"{'locator window':28} {'planted':>8} {'caught':>7} {'missed':>7} {'untouched':>10} {'false rej.':>10}")
    for window, label in WINDOWS:
        variants, caught, missed, false, reasons = run(cases, results, window)
        planted = variants * 2
        print(f"{label:28} {planted:>8} {caught:>7} {missed:>7} {variants:>10} {false:>10}")
    print()
    variants, caught, missed, false, reasons = run(cases, results, 80)
    print(">> At the shipped window, every rejection the engine gave, by reason:")
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"   {n:>4}  {reason}")
    print("\n   'quote came from X' is the placement check doing its job.")
    print("   'quote matches no supplied section' is the locator failing to find a real quote at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
