"""Run every chapter against one or more models and collect the results.

    python sweep.py                                   # replay what is recorded
    python sweep.py --live --models claude-opus-5 gpt-5-mini

Writes report/sweep_results.json so the cross-model tables in the report and in
FIX_STATUS.md are generated from measurements rather than transcribed by hand.

Two things this fixes about running sweeps as shell loops:

**Paths are absolute.** A shell loop launched from the wrong directory fails on
every script with "no such file", and if the loop greps for success lines it
prints nothing and looks like slow progress rather than total failure. That
happened, cost an hour, and is exactly the shape of the silent-failure problem
the chapters are about.

**Failures are reported as failures.** Every script's exit status is recorded
and printed. A sweep that quietly drops half its runs is worse than one that
stops.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CHAPTERS = [
    ("ch02-input-integrity", "Input integrity failures"),
    ("ch03-hallucination", "Hallucinations and confident fabrication"),
    ("ch04-classification-cascade", "Classification cascade errors"),
    ("ch05-extraction-normalisation", "Extraction and normalisation quality loss"),
    ("ch06-state-mismatch", "State mismatch failures"),
    ("ch07-edge-input", "Edge input failures"),
    ("ch08-routing-placement", "Routing and placement errors"),
    ("ch09-sparse-field-fabrication", "Sparse field fabrication"),
    ("ch10-silent-omissions", "Silent omissions"),
]

HELPERS = {"common.py", "normalise.py"}
HEADLINE = re.compile(r"^>> (.+?): (.+)$")
USAGE = re.compile(r"\[(?:live|replay)\] (\d+) model call\(s\).*?\$([\d.]+)", re.S)


def run_one(script: Path, model: str, live: bool, limit: int):
    cmd = [sys.executable, str(script), "--model", model]
    if live:
        cmd.append("--live")
    if limit:
        cmd += ["--limit", str(limit)]

    started = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    elapsed = time.monotonic() - started

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        return {
            "ok": False,
            "error": tail[-1][:300] if tail else "unknown failure",
            "seconds": elapsed,
        }

    metrics = {}
    for line in proc.stdout.splitlines():
        m = HEADLINE.match(line.strip())
        if m:
            metrics[m.group(1).strip()] = m.group(2).strip()

    cost = 0.0
    usage = USAGE.search(proc.stderr)
    if usage:
        cost = float(usage.group(2))

    return {"ok": True, "metrics": metrics, "cost": cost, "seconds": elapsed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["claude-haiku-4-5"])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", nargs="*", help="chapter directory names to restrict to")
    args = parser.parse_args()

    results, failures, total_cost = {}, [], 0.0

    for model in args.models:
        results[model] = {}
        print(f"\n{'=' * 72}\n{model}\n{'=' * 72}", flush=True)
        for directory, title in CHAPTERS:
            if args.only and directory not in args.only:
                continue
            if not (ROOT / directory).is_dir():
                continue  # chapter not built yet
            scripts = [
                p for p in sorted((ROOT / directory).glob("*.py")) if p.name not in HELPERS
            ]
            scripts.sort(key=lambda p: {"broken.py": 0, "fixed.py": 1}.get(p.name, 2))
            for script in scripts:
                key = f"{directory}/{script.name}"
                outcome = run_one(script, model, args.live, args.limit)
                results[model][key] = outcome
                if outcome["ok"]:
                    total_cost += outcome["cost"]
                    print(f"  ok    {key:<48} {outcome['seconds']:6.1f}s  "
                          f"${outcome['cost']:.4f}", flush=True)
                    for name, value in outcome["metrics"].items():
                        print(f"          {name}: {value}", flush=True)
                else:
                    failures.append((model, key, outcome["error"]))
                    print(f"  FAIL  {key:<48} {outcome['error'][:80]}", flush=True)

    out = ROOT / "report" / "sweep_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"models": args.models, "results": results}, indent=2))

    print(f"\n{'=' * 72}")
    print(f"total ${total_cost:.2f}  ·  {len(failures)} failure(s)  ·  wrote {out.name}")
    for model, key, error in failures:
        print(f"  FAIL {model} {key}: {error[:120]}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
