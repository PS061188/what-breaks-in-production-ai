"""Run an experiment N times live and report a spread instead of a point.

Every headline a script prints (the `>>` lines) is collected across runs, so a
result that moves between runs is visible rather than averaged away.

Nothing in the repo was measured twice until August 2026. When it was, four
published numbers turned out to be wrong -- including a null that was a real
effect and a false-alarm rate that did not reproduce. This is the cheapest
insurance in the project.

    python3 repeat.py ch02-input-integrity/broken.py --runs 3
    python3 repeat.py ch07-edge-input/*.py --runs 3
"""

import argparse
import collections
import pathlib
import re
import subprocess
import sys

HEADLINE = re.compile(r"^>> (.+?): (.+)$", re.M)
COST = re.compile(r"\$([0-9]+\.[0-9]+) on")


def run_once(script: pathlib.Path) -> tuple:
    proc = subprocess.run(
        ["python3", script.name, "--live"],
        cwd=script.parent, capture_output=True, text=True, timeout=1800,
    )
    text = proc.stdout + proc.stderr
    found = dict(HEADLINE.findall(text))
    return found, sum(float(x) for x in COST.findall(text)), proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scripts", nargs="+")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-cost", type=float, default=None,
                        help="hard ceiling in dollars; stop before a run that "
                             "would exceed it")
    args = parser.parse_args()

    spent = 0.0
    worst = 0.0
    for name in args.scripts:
        script = pathlib.Path(name).resolve()
        results = collections.defaultdict(list)
        if args.max_cost is not None and spent + worst > args.max_cost:
            print(f"\nBUDGET REACHED (${spent:.2f}) -- skipping {script.name} "
                  "and everything after it")
            break
        print(f"\n{'=' * 78}\n{script.parent.name}/{script.name}  x{args.runs}\n{'=' * 78}")
        for i in range(args.runs):
            # Stop BEFORE a run that would breach the ceiling, using the most
            # expensive run seen so far as the estimate. Never overshoot.
            if args.max_cost is not None and i and spent + worst > args.max_cost:
                print(f"  stopping: next run (~${worst:.2f}) would exceed "
                      f"the ${args.max_cost:.2f} ceiling (spent ${spent:.2f})")
                break
            found, cost, code = run_once(script)
            worst = max(worst, cost)
            spent += cost
            if code != 0:
                print(f"  run {i + 1}: FAILED (exit {code}) -- skipping this script")
                break
            print(f"  run {i + 1}: ${cost:.2f}  ({len(found)} headline(s))")
            # A parse that finds nothing must not look like a run that agreed.
            # The first version of this script matched zero headlines and
            # reported "nothing moved" for 42 live runs. $3.40, silently.
            if not found:
                print("      NO HEADLINES PARSED -- aborting rather than "
                      "reporting a false agreement")
                return 1
            for k, v in found.items():
                results[k].append(v)
        for measure, values in results.items():
            uniq = sorted(set(values))
            flag = "  <-- MOVED" if len(uniq) > 1 else ""
            print(f"    {measure}")
            print(f"      {' | '.join(values)}{flag}")

    print(f"\n{'=' * 78}\nlive cost this session: ${spent:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
