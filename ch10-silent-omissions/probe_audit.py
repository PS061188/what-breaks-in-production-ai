"""Chapter 10's completeness audit, run against extractions with known gaps (Experiment 10.6).

The chapter's third engineering fix is a second model call — the
evaluator-optimizer pattern: show a model the source document and the extracted
output and ask, verbatim, "What information present in the source is missing
from the extraction?". fixed.py ran that audit once, against an extraction run
that had almost nothing missing. Nobody has measured whether the audit catches
omissions that are KNOWN to have happened, or how often it alarms on
extractions that are complete.

This probe has ground truth on both sides. The recorded extractions of
Experiment 10.3 (fixtures_count/{as-printed,distinct,protocol}/, 54 runs) and
the kept API protocol run (fixtures/, book_prompt.py's last run, 6 documents)
are compared against the pattern's reference count with the corrected matcher
(lab-unit exclusion on the source side, expand_ranges=True on the list side
only). That comparison names which extractions are short and by which figures.
One audit call per recorded extraction — Claude Haiku 4.5, no tools, at most
2 attempts per case and at most 60 calls in all. No schema is enforced, so the
prompt adds a JSON format instruction after the book's question, and the reply
is parsed.

Scoring is proposed, not concluded: every non-empty missing[] list is printed
in full, every known-missing figure no entry contained is printed, and entries
that may name real content the dose pattern cannot see (mL volumes, dosing-table
cells whose unit sits in the column heading, range endpoints) are tagged
pattern-blind candidates for hand reading rather than counted as false alarms.

    python3 probe_audit.py           # replay recorded audits and rescore
    python3 probe_audit.py --live    # record any audit that is missing
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from common import build_cases, dose_figures  # noqa: E402
from probe_count import MODEL, parse  # noqa: E402

AUDITOR = MODEL   # overridden by --auditor for Experiment 10.12

from shared.cli_defaults import SUFFIX, api_defaults  # noqa: E402
FIXTURES = HERE / ("fixtures_audit" + SUFFIX)
SOURCE_CLI = HERE / ("fixtures_count" + SUFFIX)
SOURCE_API = HERE / "fixtures"
CLI = str(Path.home() / ".local" / "bin" / "claude")
CONDITIONS = ("as-printed", "distinct", "protocol", "api-protocol")
BUDGET = 60
MAX_ATTEMPTS = 2

SYSTEM = ("You are auditing an extraction for completeness. An extraction system "
          "was asked to list every distinct dose amount mentioned in the document. "
          "You will be shown the source document and the list it extracted.")

# The book's question, verbatim, after the source and the extraction. The JSON
# instruction is an addition for scorability — no schema is enforced.
USER = ("SOURCE:\n{text}\n\n"
        "EXTRACTED:\n{doses}\n\n"
        "What information present in the source is missing from the extraction?\n\n"
        "Answer with JSON only: {{\"missing\": [\"...\"]}} — one entry per missing "
        "item, or [] if nothing is missing.")

_lock = threading.Lock()
_attempts = 0
_pre_recorded = 0  # fixtures on disk before this live run; set once in main()


def call_cli(system: str, prompt: str, budget_used: int) -> dict:
    """probe_count.py's call, with a hard call budget and TimeoutExpired retried.

    Every subprocess attempt counts against BUDGET, recorded fixtures included
    (each one took at least one call). Max 2 attempts per case.
    """
    global _attempts
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    cmd = [CLI, "-p", "--model", AUDITOR, "--output-format", "json", "--system-prompt", system,
           "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]
    env, cmd = api_defaults(AUDITOR, env, cmd)
    proc = None
    with tempfile.TemporaryDirectory() as cwd:
        for attempt in range(MAX_ATTEMPTS):
            with _lock:
                if budget_used + _attempts >= BUDGET:
                    raise RuntimeError(f"call budget of {BUDGET} exhausted")
                _attempts += 1
            try:
                proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env, cwd=cwd, timeout=600)
            except subprocess.TimeoutExpired:
                print(f"  attempt {attempt + 1} timed out after 600s", file=sys.stderr)
                continue
            if proc.returncode == 0:
                out = json.loads(proc.stdout)
                if not out.get("is_error"):
                    return out
            time.sleep(20 * (attempt + 1))
    tail = (proc.stderr[-400:] or proc.stdout[-400:]) if proc is not None else "timed out on every attempt"
    raise RuntimeError(f"claude CLI failed: {tail}")


def load_extractions() -> list:
    """Every recorded extraction, with its doses list and its case.

    The three conditions of Experiment 10.3 come from fixtures_count/. The kept API protocol
    run (book_prompt.py's last run) comes from fixtures/ — a different envelope
    (model/system/user/response, no condition or drug fields), but the reply
    JSON inside has the same "doses" list, so it qualifies. Its drug is
    recovered by matching the case text embedded in the recorded system prompt.
    """
    cases = {c["drug"].split()[0].lower(): c for c in build_cases()}
    out = []
    for cond in ("as-printed", "distinct", "protocol"):
        for path in sorted((SOURCE_CLI / cond).glob("*.json")):
            rec = json.loads(path.read_text(encoding="utf-8"))
            drug = rec["drug"].split()[0].lower()
            doses = [str(d) for d in parse(rec["reply"])["doses"]]
            out.append({"condition": cond, "drug": drug, "run": rec["run"],
                        "doses": doses, "case": cases[drug]})
    for path in sorted(SOURCE_API.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        if not rec.get("system", "").startswith("You are an extraction engine"):
            continue
        drug = next(k for k, c in cases.items() if c["text"] in rec["system"])
        doses = [str(d) for d in json.loads(rec["response"])["doses"]]
        out.append({"condition": "api-protocol", "drug": drug, "run": 1,
                    "doses": doses, "case": cases[drug]})
    order = {c: i for i, c in enumerate(CONDITIONS)}
    out.sort(key=lambda e: (order[e["condition"]], e["drug"], e["run"]))
    return out


def comparison(ext: dict) -> dict:
    """The corrected Experiment 10.3 comparison: reference over the source,
    expand_ranges=True over the joined doses list only."""
    reference = ext["case"]["expected"]
    own = dose_figures(" ".join(ext["doses"]), expand_ranges=True)
    return {"reference": reference, "own": own,
            "known_missing": sorted(reference - own)}


def contains_figure(entry: str, figure: str) -> bool:
    """Does the entry contain the figure — number + unit, whitespace-insensitive?

    Range forms count too ("10 to 15 mg" contains 10 mg), the same corrected
    rule Experiment 10.3 applies to a model's list.
    """
    num, unit = figure.split()
    if re.search(rf"(?<![\d.]){re.escape(num)}\s*{re.escape(unit)}s?\b", entry, re.I):
        return True
    return figure in dose_figures(entry, expand_ranges=True)


def number_in_source(num: str, source: str) -> bool:
    return re.search(rf"(?<![\d.]){re.escape(num)}(?![\d.])", source) is not None


def propose_tags(entry: str, comp: dict, source: str) -> list:
    """Mechanical proposals only — the hand-read decides."""
    tags = []
    caught = [f for f in comp["known_missing"] if contains_figure(entry, f)]
    if caught:
        tags.append("CAUGHT " + ", ".join(caught))
    figs = dose_figures(entry, expand_ranges=True)
    if figs and figs <= comp["own"]:
        tags.append("already-in-extraction (false-alarm candidate)")
    expanded_src = dose_figures(source, expand_ranges=True)
    endpoints = figs & (expanded_src - comp["reference"] - comp["own"])
    if endpoints:
        tags.append("pattern-blind candidate: range endpoint in source (" + ", ".join(sorted(endpoints)) + ")")
    volumes = [v for v in re.findall(r"(\d+(?:\.\d+)?)\s*mL\b", entry, re.I) if number_in_source(v, source)]
    if volumes:
        tags.append("pattern-blind candidate: mL volume in source (" + ", ".join(volumes) + " mL)")
    nums = re.findall(r"\d+(?:\.\d+)?", entry)
    in_src = [n for n in nums if number_in_source(n, source)]
    if nums and not in_src:
        tags.append("no number of this entry found in source (invented candidate)")
    elif in_src and not caught and not figs:
        tags.append("pattern-blind candidate: bare number in source, no adjacent unit (" + ", ".join(in_src[:6]) + ")")
    if not tags:
        tags.append("hand-read")
    return tags


def get(ext: dict, live: bool) -> dict:
    sub = "" if AUDITOR == MODEL else AUDITOR + "/"
    path = FIXTURES / (sub + ext["condition"]) / f"{ext['drug']}__s{ext['run']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recorded audit: {path.relative_to(HERE)} (run with --live)")
    started = time.time()
    doses = json.dumps(ext["doses"], ensure_ascii=False, indent=1)
    out = call_cli(SYSTEM, USER.format(text=ext["case"]["text"], doses=doses), budget_used=_pre_recorded)
    record = {"condition": ext["condition"], "drug": ext["case"]["drug"], "run": ext["run"],
              "model_requested": AUDITOR, "models_used": sorted((out.get("modelUsage") or {}).keys()),
              "reply": out.get("result", ""), "seconds": round(time.time() - started, 1),
              "notional_cost_usd": out.get("total_cost_usd")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  recorded {path.relative_to(HERE)} ({record['seconds']}s)", file=sys.stderr)
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="record missing audits live")
    ap.add_argument("--auditor", default=MODEL, help="auditor model (Experiment 10.12: a different model than the extractor)")
    args = ap.parse_args()
    global AUDITOR
    AUDITOR = args.auditor

    extractions = load_extractions()
    comps = [comparison(e) for e in extractions]

    print("=" * 78)
    print("Experiment 10.6 — the completeness audit, against extractions with known gaps")
    print("=" * 78)
    print("\nPRE-CHECK — the corrected pattern comparison over every recorded extraction")
    print("(reference = dose_figures on the source, lab-unit fix in; extraction =")
    print("dose_figures over the joined doses list, expand_ranges=True on the list side)\n")
    print(f"{'condition':13} {'drug':14} {'run':>3} {'n_reference':>11} {'n_found':>7}  known_missing")
    short = 0
    for ext, comp in zip(extractions, comps):
        km = comp["known_missing"]
        short += bool(km)
        print(f"{ext['condition']:13} {ext['drug']:14} {ext['run']:>3} {len(comp['reference']):>11} "
              f"{len(comp['reference'] & comp['own']):>7}  {', '.join(km) if km else '-'}")
    n_figures = sum(len(c["known_missing"]) for c in comps)
    print(f"\n{len(extractions)} recorded extractions (54 from Experiment 10.3 + {len(extractions) - 54} from the protocol prompt); "
          f"{short} short, {len(extractions) - short} complete; "
          f"{n_figures} known-missing figures in all")
    print("fixtures/ note: the API protocol files have a different envelope (model/system/"
          "user/response,\nno condition or drug fields) but the reply JSON inside has the "
          "same \"doses\" list, so the\nsix extractions are included, as condition api-protocol.")

    if short < 3:
        print(f"\nSTOP: only {short} short extraction(s) — below the floor of 3. No audit calls made.")
        return 1

    if args.live:
        global _pre_recorded
        root = FIXTURES if AUDITOR == MODEL else FIXTURES / AUDITOR
        _pre_recorded = len(list(root.glob("*/*.json")))
        with cf.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda e: get(e, live=True), extractions))

    # Scoring recomputes everything from the recorded files on disk.
    records = [get(e, live=False) for e in extractions]

    print("\n" + "=" * 78)
    print("PER-CASE AUDIT RESULTS — every counted case, every non-empty missing[] in full")
    print("=" * 78)
    caught_total, caught_by_cond = 0, {}
    figures_by_cond = {}
    alarms, complete_by_cond, alarms_by_cond = 0, {}, {}
    short_with_output = short_fully_caught = 0
    unparseable = []
    pattern_blind = []
    uncaught_lines = []

    for ext, comp, rec in zip(extractions, comps, records):
        cond, km = ext["condition"], comp["known_missing"]
        label = f"{cond} / {ext['drug']} / run {ext['run']}"
        figures_by_cond[cond] = figures_by_cond.get(cond, 0) + len(km)
        try:
            missing = [str(m) for m in parse(rec["reply"])["missing"]]
        except Exception as err:
            unparseable.append(label)
            print(f"\n--- {label} — UNPARSEABLE REPLY ({err}) ---")
            print(f"known_missing: {km or '(none — extraction complete)'}")
            print("raw reply, in full:")
            print(rec["reply"])
            continue

        if km:
            if missing:
                short_with_output += 1
            caught_here = [f for f in km if any(contains_figure(m, f) for m in missing)]
            caught_total += len(caught_here)
            caught_by_cond[cond] = caught_by_cond.get(cond, 0) + len(caught_here)
            if len(caught_here) == len(km):
                short_fully_caught += 1
            print(f"\n--- {label} — SHORT extraction ---")
            print(f"known_missing ({len(km)}): {km}")
            print(f"audit missing[] ({len(missing)} entr{'y' if len(missing) == 1 else 'ies'}):")
            for m in missing:
                tags = propose_tags(m, comp, ext["case"]["text"])
                print(f"  - {json.dumps(m, ensure_ascii=False)}")
                print(f"      proposed: {'; '.join(tags)}")
                for t in tags:
                    if t.startswith("pattern-blind"):
                        pattern_blind.append((label, m, t))
            for f in km:
                if f not in caught_here:
                    uncaught_lines.append(f"  NOT CAUGHT: {f}  ({label})")
            print(f"figures caught here: {len(caught_here)}/{len(km)} "
                  f"({', '.join(caught_here) if caught_here else 'none'})")
        else:
            complete_by_cond[cond] = complete_by_cond.get(cond, 0) + 1
            if missing:
                alarms += 1
                alarms_by_cond[cond] = alarms_by_cond.get(cond, 0) + 1
                print(f"\n--- {label} — COMPLETE extraction, audit raised entries (alarm) ---")
                print(f"audit missing[] ({len(missing)} entr{'y' if len(missing) == 1 else 'ies'}):")
                for m in missing:
                    tags = propose_tags(m, comp, ext["case"]["text"])
                    print(f"  - {json.dumps(m, ensure_ascii=False)}")
                    print(f"      proposed: {'; '.join(tags)}")
                    for t in tags:
                        if t.startswith("pattern-blind"):
                            pattern_blind.append((label, m, t))
            else:
                print(f"\n--- {label} — COMPLETE extraction, audit returned [] (silent, correct)")

    print("\n" + "=" * 78)
    print("KNOWN-MISSING FIGURES NO missing[] ENTRY CONTAINED")
    print("=" * 78)
    print("\n".join(uncaught_lines) if uncaught_lines else "(none — every known-missing figure was named)")

    print("\n" + "=" * 78)
    print("SUMMARY (proposed scores — the per-case prints above are the record)")
    print("=" * 78)
    n_complete = len(extractions) - short
    print(f"\nKnown-missing figures caught: {caught_total} of {n_figures}, across {short} short extractions")
    for cond in CONDITIONS:
        if figures_by_cond.get(cond):
            print(f"  {cond:13} {caught_by_cond.get(cond, 0)}/{figures_by_cond[cond]} figures")
    print(f"Short extractions where the audit raised anything: {short_with_output} of {short}")
    print(f"Short extractions with every known-missing figure caught: {short_fully_caught} of {short}")
    print(f"\nAlarms on complete extractions (missing[] non-empty): {alarms} of {n_complete}")
    for cond in CONDITIONS:
        if complete_by_cond.get(cond):
            print(f"  {cond:13} {alarms_by_cond.get(cond, 0)}/{complete_by_cond[cond]} complete extractions")
    print(f"\nPattern-blind candidates (entries that may name real source content the dose")
    print(f"pattern cannot see — NOT counted as false alarms, for hand reading): {len(pattern_blind)}")
    for label, m, t in pattern_blind:
        print(f"  {label}: {json.dumps(m, ensure_ascii=False)}  [{t}]")
    if unparseable:
        print(f"\nUnparseable replies: {len(unparseable)} — {unparseable}")

    cost = sum(r.get("notional_cost_usd") or 0 for r in records)
    seconds = sum(r.get("seconds") or 0 for r in records)
    used = sorted({m for r in records for m in r.get("models_used", [])})
    print(f"\nRecorded audit calls: {len(records)} (one per extraction; retries would appear "
          f"in the live run's attempt count)")
    print(f"Live attempts this run: {_attempts} (budget {BUDGET}, recorded fixtures count against it)")
    print(f"Total cost at API prices: ${cost:.4f}")
    print(f"Total recorded seconds: {seconds:.0f}")
    print(f"Models used: {used}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
