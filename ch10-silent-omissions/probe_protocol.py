"""Chapter 10's completeness protocol, three recorded runs on the CLI (Experiment 10.3, second half).

book_prompt.py ran the protocol three times through repeat.py, which keeps only the
last run's answers, so two of the three runs behind the book's figures cannot be
reopened. This probe reruns it three times and keeps every run, through the same
`claude -p` setup as probe_count.py, so the protocol can be compared with the
one-line instruction's three runs recorded there (condition "as-printed").

What it reports, per run:
  - dose figures returned, against the code's count of distinct figures
  - Step 1's inventory count against the number of items the model then listed
  - Step 3's self-check: which short documents it flagged, and which complete ones

    python3 probe_protocol.py           # replay
    python3 probe_protocol.py --live    # record any run that is missing
"""

import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from book_prompt import SYSTEM  # noqa: E402
from common import build_cases, dose_figures  # noqa: E402
from probe_count import MODEL, RUNS, call_cli, parse  # noqa: E402

from shared.cli_defaults import SUFFIX, api_defaults  # noqa: E402
FIXTURES = HERE / ("fixtures_count" + SUFFIX) / "protocol"
USER = ("Run the protocol and return the result.\n\n"
        "Return only a JSON object with exactly these keys and no other text: "
        "\"inventory_count\" (integer), \"doses\" (array of strings), \"completeness_check\" "
        "(object with \"all_counts_match\" (boolean) and \"warnings\" (array of strings)).")


def get(case: dict, run: int, live: bool) -> dict:
    path = FIXTURES / f"{case['drug'].split()[0].lower()}__s{run}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recorded answer: {path.relative_to(HERE)} (run with --live)")
    started = time.time()
    out = call_cli(SYSTEM.replace("{text}", case["text"]), USER)
    record = {"condition": "protocol", "drug": case["drug"], "run": run, "model_requested": MODEL,
              "models_used": sorted((out.get("modelUsage") or {}).keys()), "reply": out.get("result", ""),
              "seconds": round(time.time() - started, 1), "notional_cost_usd": out.get("total_cost_usd")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="record missing runs through the claude CLI")
    args = ap.parse_args()
    cases = build_cases()
    jobs = [(case, r) for r in RUNS for case in cases]
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(lambda j: get(*j, live=args.live), jobs))

    per_run = {}
    print(f"{'run':>3}  {'drug':13} {'code':>4} {'inventory':>9} {'items':>5} {'returned':>8}  missing / self-check")
    for (case, run), rec in zip(jobs, records):
        ans = parse(rec["reply"])
        got = dose_figures(" ".join(map(str, ans["doses"])), expand_ranges=True)
        missing = sorted(case["expected"] - got)
        check = ans["completeness_check"]
        flagged = (not check["all_counts_match"]) or bool(check["warnings"])
        print(f"{run:>3}  {case['drug'][:13]:13} {len(case['expected']):>4} {ans['inventory_count']:>9} "
              f"{len(ans['doses']):>5} {len(case['expected'] & got):>5}/{len(case['expected'])}  "
              f"{missing or '-'} / {'FLAGGED' if flagged else 'silent'}")
        s = per_run.setdefault(run, {"ret": 0, "exp": 0, "inv_eq_items": 0, "short": [], "complete": []})
        s["ret"] += len(case["expected"] & got)
        s["exp"] += len(case["expected"])
        s["inv_eq_items"] += int(ans["inventory_count"]) == len(ans["doses"])
        (s["short"] if missing else s["complete"]).append((case["drug"].split()[0], flagged))

    print()
    for run, s in per_run.items():
        short_flagged = sum(f for _, f in s["short"])
        complete_flagged = sum(f for _, f in s["complete"])
        print(f"run {run}: returned {s['ret']}/{s['exp']} ({100 * s['ret'] / s['exp']:.0f}%); "
              f"inventory = items listed on {s['inv_eq_items']}/6; "
              f"self-check flagged {short_flagged}/{len(s['short'])} short documents "
              f"and {complete_flagged}/{len(s['complete'])} complete ones")
    used = sorted({m for r in records for m in r.get("models_used", [])})
    print(f"\nmodels used: {used}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
