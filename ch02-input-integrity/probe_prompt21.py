"""Experiment 2.7 — Prompt 2-1 exactly as printed: report the damage, never abort.

book_prompt.py runs the chapter's earlier protocol, which tells the model to
abort on a bad grade. The prompt the book prints today is the report-only
version: list every corruption signal, quote the worst passage, grade the input,
and always extract, leaving the decision to the caller. Its "What this prompt
does" figures had been carried over from the earlier protocol. This runs the
printed text (prompt_2_1.txt) on the same 53 documents, three times.

Runs Claude Haiku 4.5, no tools. Each reply is recorded in
fixtures_prompt21/ and replays for free.

    python3 probe_prompt21.py           # replay
    python3 probe_prompt21.py --live    # record any run that is missing
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

from common import build_cases  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

from shared.cli_defaults import SUFFIX, api_defaults  # noqa: E402
FIXTURES = HERE / ("fixtures_prompt21" + SUFFIX)
PROMPT = (HERE / "prompt_2_1.txt").read_text(encoding="utf-8")
CLI = str(Path.home() / ".local" / "bin" / "claude")
MODEL = "claude-haiku-4-5"
RUNS = (1, 2, 3)
USER = "Report the input quality, then extract the starting dose."

# Three of the twelve clean controls carry a real defect in the label text as
# supplied, so flagging them is correct. Every reply that flagged one quoted it.
KNOWN_DEFECTS = {
    "Amoxicillin": "zero-width spaces before the suspension strengths",
    "Gabapentin": "'ADMlNlSTRATION', lower-case l for capital I, in the label text",
    "Metformin": "'1.73 m 2' four times, the superscript lost",
}


def call_cli(system: str, prompt: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    cmd = [CLI, "-p", "--model", MODEL, "--output-format", "json", "--system-prompt", system,
           "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]
    env, cmd = api_defaults(MODEL, env, cmd)
    with tempfile.TemporaryDirectory() as cwd:
        for attempt in range(3):
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env, cwd=cwd, timeout=600)
            if proc.returncode == 0:
                out = json.loads(proc.stdout)
                if not out.get("is_error"):
                    return out
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"claude CLI failed: {proc.stderr[-400:] or proc.stdout[-400:]}")


def grade(reply: str):
    """The input_quality the reply gave, or None if it gave none.

    No schema is enforced, so some replies grade in prose ("Classification:
    DEGRADED") before or instead of the JSON. The JSON field wins when present.
    """
    m = re.search(r'"input_quality"\s*:\s*"([A-Z_]+)"', reply)
    if not m:
        m = re.search(r"(?:input[_ ]quality|classification|grade|status|assessment)\W{0,12}"
                      r"(CLEAN|DEGRADED|SEVERELY_CORRUPTED)", reply, re.I)
    return m.group(1).upper() if m else None


def get(case: dict, run: int, live: bool) -> dict:
    path = FIXTURES / f"{case['mode']}__{case['drug'].split()[0].lower()}__s{run}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recorded answer: {path.relative_to(HERE)} (run with --live)")
    started = time.time()
    out = call_cli(PROMPT + "\n\n<text>\n" + case["text"] + "\n</text>", USER)
    record = {"mode": case["mode"], "drug": case["drug"], "run": run, "model_requested": MODEL,
              "models_used": sorted((out.get("modelUsage") or {}).keys()), "reply": out.get("result", ""),
              "seconds": round(time.time() - started, 1), "notional_cost_usd": out.get("total_cost_usd")}
    FIXTURES.mkdir(exist_ok=True)
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="record missing runs live")
    args = ap.parse_args()

    cases = build_cases()
    jobs = [(c, r) for r in RUNS for c in cases]
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(lambda job: get(job[0], job[1], args.live), jobs))
    grades = {(rec["mode"], rec["drug"], rec["run"]): grade(rec["reply"]) for rec in records}

    modes = sorted({c["mode"] for c in cases if c["mode"] != "clean"})
    rule("Prompt 2-1 as printed: documents graded not CLEAN, by damage type and run")
    rows = []
    for mode in ["clean"] + modes:
        group = [c for c in cases if c["mode"] == mode]
        rows.append([mode] + [pct(sum(grades[mode, c["drug"], r] != "CLEAN" for c in group), len(group)) for r in RUNS])
    table(["damage"] + [f"run {r}" for r in RUNS], rows)

    rule("Grades given, all 53 documents, per run")
    names = ["CLEAN", "DEGRADED", "SEVERELY_CORRUPTED", None]
    table(["run"] + [str(n) for n in names],
          [[r] + [sum(grades[c["mode"], c["drug"], r] == n for c in cases) for n in names] for r in RUNS])

    damaged = [c for c in cases if c["mode"] != "clean"]
    clean = [c for c in cases if c["mode"] == "clean"]
    for r in RUNS:
        headline(f"Run {r}: damaged documents graded not CLEAN",
                 pct(sum(grades[c["mode"], c["drug"], r] != "CLEAN" for c in damaged), len(damaged)))
        flagged = [c["drug"].split()[0] for c in clean if grades["clean", c["drug"], r] != "CLEAN"]
        false_alarms = [d for d in flagged if d not in KNOWN_DEFECTS]
        headline(f"Run {r}: clean controls graded not CLEAN", pct(len(flagged), len(clean)),
                 f"real defects {len(flagged) - len(false_alarms)}, false alarms {len(false_alarms)}"
                 + (f" ({', '.join(false_alarms)})" if false_alarms else ""))
    cost = sum(rec.get("notional_cost_usd") or 0 for rec in records)
    print(f"\n  {len(records)} replies · cost at API prices ${cost:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
