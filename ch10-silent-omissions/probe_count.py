"""Chapter 10 — the model's own count of the source, asked without ambiguity (Experiment 10.3).

fixed.py asks the model to "count the dose amounts in the source" and compares the
answer with the number of DISTINCT dose figures the code finds. "The dose amounts"
also reads as every mention, and each of the six recorded answers sat between the
distinct count and the mention count (FINDINGS §16). So the 0-of-6 result measured
the wording of the question as much as the model.

This probe asks the same question two ways, on the same six documents:

  as-printed   fixed.py's prompt, word for word
  distinct     the same prompt with the count defined: each different amount once,
               however many times it appears

and compares every answer with three numbers the code computes without the model:
distinct figures in the source, mentions in the source, and distinct figures in the
model's own list. Three runs of each, Claude Haiku 4.5, called through the `claude -p`
CLI on the claude.ai plan (never the paid API) with its default system prompt
replaced, no tools, no MCP servers, no settings files and an empty working
directory. The CLI has no schema enforcement, so the prompt asks for the JSON
object fixed.py's schema defines and the reply is parsed.

    python3 probe_count.py           # replay recorded answers
    python3 probe_count.py --live    # record any run that is missing
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from common import DOSE, FOLLOWED_BY_COMPARISON, IDENTIFIER_BEFORE, LAB_UNIT_AFTER, build_cases, dose_figures  # noqa: E402
from fixed import SYSTEM as AS_PRINTED  # noqa: E402

FIXTURES = HERE / "fixtures_count"
CLI = str(Path.home() / ".local" / "bin" / "claude")
MODEL = "claude-haiku-4-5"
RUNS = (1, 2, 3)

ASKED = "count\nthe dose amounts in the source and check your list against that count."
assert ASKED in AS_PRINTED
DISTINCT = AS_PRINTED.replace(
    ASKED,
    "count\nthe distinct dose amounts in the source (each different amount once, however\n"
    "many times it appears: \"20 mg\" mentioned three times counts as one) and check\n"
    "your list against that count.")

PROMPTS = {"as-printed": AS_PRINTED, "distinct": DISTINCT}

USER = ("List every dose amount mentioned in the text.\n\n"
        "Return only a JSON object with exactly these keys and no other text: "
        "\"doses\" (array of strings), \"not_extracted\" (array of strings), "
        "\"source_count_claimed\" (integer).")


def mentions(text: str) -> int:
    """Every dose figure in the text, repeats included, with common.py's exclusions."""
    n = 0
    for m in DOSE.finditer(text):
        if IDENTIFIER_BEFORE.search(text[max(0, m.start() - 12): m.start()]):
            continue
        if FOLLOWED_BY_COMPARISON.match(text[m.end(): m.end() + 4]):
            continue
        if LAB_UNIT_AFTER.match(text[m.end(): m.end() + 6]):
            continue
        n += 1
    return n


def call_cli(system: str, prompt: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    cmd = [CLI, "-p", "--model", MODEL, "--output-format", "json", "--system-prompt", system,
           "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]
    with tempfile.TemporaryDirectory() as cwd:
        for attempt in range(3):
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env, cwd=cwd, timeout=600)
            if proc.returncode == 0:
                out = json.loads(proc.stdout)
                if not out.get("is_error"):
                    return out
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"claude CLI failed: {proc.stderr[-400:] or proc.stdout[-400:]}")


def parse(reply: str) -> dict:
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
    return json.loads(body[body.find("{"): body.rfind("}") + 1])


def get(condition: str, case: dict, run: int, live: bool) -> dict:
    path = FIXTURES / condition / f"{case['drug'].split()[0].lower()}__s{run}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recorded answer: {path.relative_to(HERE)} (run with --live)")
    started = time.time()
    out = call_cli(PROMPTS[condition].format(text=case["text"]), USER)
    record = {"condition": condition, "drug": case["drug"], "run": run, "model_requested": MODEL,
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
    jobs = [(c, case, r) for c in PROMPTS for case in cases for r in RUNS]
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(lambda j: get(*j, live=args.live), jobs))

    print(f"{'condition':11} {'run':>3}  {'drug':13} {'distinct':>8} {'mentions':>8} {'claimed':>7} "
          f"{'own list':>8} {'returned':>8}")
    summary = {}
    for (condition, case, run), rec in zip(jobs, records):
        ans = parse(rec["reply"])
        claimed = int(ans["source_count_claimed"])
        own = dose_figures(" ".join(map(str, ans["doses"])), expand_ranges=True)
        distinct, total = len(case["expected"]), mentions(case["text"])
        returned = len(case["expected"] & own)
        print(f"{condition:11} {run:>3}  {case['drug'][:13]:13} {distinct:>8} {total:>8} {claimed:>7} "
              f"{len(own):>8} {returned:>5}/{distinct}")
        s = summary.setdefault((condition, run), {"exact": 0, "own": 0, "items": 0, "closer_to_mentions": 0, "err": [], "ret": 0, "exp": 0})
        s["exact"] += claimed == distinct
        s["own"] += claimed == len(own)
        s["items"] += claimed == len(ans["doses"])
        s["closer_to_mentions"] += abs(claimed - total) < abs(claimed - distinct)
        s["err"].append(claimed - distinct)
        s["ret"] += returned
        s["exp"] += distinct

    print()
    for (condition, run), s in summary.items():
        print(f"{condition:11} run {run}: count = items it listed on {s['items']}/6, = distinct figures on {s['exact']}/6, "
              f"= distinct figures in its list on {s['own']}/6, "
              f"nearer the mention count on {s['closer_to_mentions']}/6; count minus distinct {s['err']}; "
              f"figures returned {s['ret']}/{s['exp']}")
    used = sorted({m for r in records for m in r.get("models_used", [])})
    print(f"\nmodels used: {used}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
