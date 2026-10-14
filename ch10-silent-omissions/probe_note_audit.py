"""Experiment 10.9, part 1 — the completeness audit (fix 3) on prose output.

Every fix in Chapter 10 was measured on an extraction task: the output is a
list, and a count can say whether the list is short. Prachi's question (13 Oct
2026): what do the fixes do on a task whose output has no countable items? The
task here is the chapter's own second corpus, 60 ACI-Bench role-played
doctor-patient conversations turned into clinic notes (Experiment 9.4's
recorded template-prompt notes, run s1). A note is prose. Nothing in it can be
counted the way doses in a list can.

Fix 3 is the one fix that runs unchanged on prose: show a second model the
conversation and the note, ask what is missing. One call per conversation,
Claude Haiku 4.5 through the subscription CLI.

Scoring is the hard part, and it is stated rather than hidden: there is no
enumerable ground truth, which is the point of the experiment. Three things
can still be checked:

  dose claims      Experiment 10.5 read every stated dose against every note:
                   all 64 reached all their notes. So an audit claim that a
                   DOSE is missing is a false alarm by a settled record.
  quote check      for each claim, whether the content it names appears in the
                   note (a conservative keyword test, printed per claim so it
                   can be audited), and whether it appears in the dialogue.
  hand reading     every claim is printed in full under its encounter id.
                   The classes are the scorer's suggestion; the printed
                   claims are the record.

    python3 probe_note_audit.py                 # replay
    python3 probe_note_audit.py --live          # record run 1
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
CH9 = HERE.parent / "ch09-sparse-field-fabrication" / "fixtures_conversation" / "template"
DATA = HERE.parent / "data" / "aci_bench_dialogues.json"
FIXTURES = HERE / "fixtures_note_audit"
CLI = str(Path.home() / ".local" / "bin" / "claude")
MODEL = "claude-haiku-4-5"

SYSTEM = """You are auditing a clinical visit note for completeness.

You will be shown the conversation the note was written from, and the note.
List every piece of clinically relevant content that the conversation contains
and the note leaves out. For each item give a short quote from the conversation.
If nothing relevant is missing, return an empty list.

Return JSON: { "missing": [ { "content": "<what is missing>", "quote": "<from the conversation>" } ] }"""

USER = "CONVERSATION:\n{dialogue}\n\nNOTE:\n{note}\n\nReturn only the JSON object."

DOSE_RX = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:mg|mcg|milligrams?|micrograms?|units?)\b", re.I)


def load_pairs() -> list:
    dialogues = {(d["split"], d["encounter_id"]): d["dialogue"]
                 for d in json.loads(DATA.read_text())["dialogues"]}
    pairs = []
    for f in sorted(CH9.glob("*__s1.json")):
        rec = json.loads(f.read_text())
        key = (rec["split"], rec["encounter_id"])
        pairs.append({"split": key[0], "encounter_id": key[1],
                      "dialogue": dialogues[key], "note": rec["note"]})
    return pairs


def call_cli(prompt: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    cmd = [CLI, "-p", "--model", MODEL, "--output-format", "json", "--system-prompt", SYSTEM,
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


def parse_json(text: str):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    a, b = t.find("{"), t.rfind("}")
    if a < 0:
        return None
    try:
        obj = json.loads(t[a:b + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) and "missing" in obj else None


def get_record(pair: dict, sample: int, live: bool) -> dict:
    path = FIXTURES / f"s{sample}" / f"{pair['split']}__{pair['encounter_id']}.json"
    if path.exists():
        return json.loads(path.read_text())
    if not live:
        raise FileNotFoundError(f"no recording: {path.name} (run with --live)")
    started = time.time()
    out = call_cli(USER.format(dialogue=pair["dialogue"], note=pair["note"]))
    record = {
        "experiment": "10.9-audit", "encounter_id": pair["encounter_id"], "split": pair["split"],
        "sample": sample, "model_requested": MODEL,
        "models_used": sorted((out.get("modelUsage") or {}).keys()),
        "result": out.get("result", ""), "parsed": parse_json(out.get("result", "")),
        "seconds": round(time.time() - started, 1), "notional_cost_usd": out.get("total_cost_usd"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1))
    return record


def words(text: str) -> set:
    return set(re.findall(r"[a-z]{4,}", text.lower()))


def check(claim_text: str, target: str) -> str:
    """Conservative: do the claim's content words appear in the target text?"""
    w = words(claim_text)
    if not w:
        return "no content words"
    hit = sum(1 for x in w if x in words(target))
    share = hit / len(w)
    return "mostly present" if share >= 0.6 else ("partly present" if share >= 0.3 else "absent")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--sample", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    pairs = load_pairs()
    if args.limit:
        pairs = pairs[: args.limit]
    records = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers if args.live else 1) as pool:
        futures = {pool.submit(get_record, p, args.sample, args.live): p for p in pairs}
        for fut in cf.as_completed(futures):
            p = futures[fut]
            records[(p["split"], p["encounter_id"])] = (p, fut.result())

    n_claims = n_notes_with = unparsable = 0
    dose_claims, note_has, dlg_lacks, seconds, cost = [], 0, 0, 0.0, 0.0
    print(f"Experiment 10.9, fix 3 on prose output · {len(records)} conversation-note pairs · run {args.sample}")
    for key in sorted(records):
        pair, rec = records[key]
        seconds += rec.get("seconds") or 0
        cost += rec.get("notional_cost_usd") or 0
        obj = rec.get("parsed")
        if obj is None:
            unparsable += 1
            continue
        claims = obj.get("missing") or []
        if claims:
            n_notes_with += 1
        print(f"\n=== {key[1]} · {len(claims)} claim(s)")
        for c in claims:
            text = c.get("content", c) if isinstance(c, dict) else str(c)
            quote = c.get("quote", "") if isinstance(c, dict) else ""
            n_claims += 1
            in_note = check(str(text), pair["note"])
            in_dlg = check(str(quote) or str(text), pair["dialogue"])
            flags = []
            if DOSE_RX.search(str(text)) or DOSE_RX.search(str(quote)):
                dose_claims.append((key[1], str(text)[:80]))
                flags.append("NAMES A DOSE (all doses verified present, Exp 10.5)")
            if in_note == "mostly present":
                note_has += 1
                flags.append("note seems to carry it")
            if in_dlg == "absent":
                dlg_lacks += 1
                flags.append("quote not found in dialogue")
            print(f"  - «{str(text)[:120]}»")
            if quote:
                print(f"    quote: «{str(quote)[:110]}»")
            print(f"    [content words in note: {in_note}; quote in dialogue: {in_dlg}]"
                  + (f"  ** {'; '.join(flags)}" if flags else ""))
    print(f"\nSummary: {n_claims} claims across {n_notes_with} of {len(records)} notes; "
          f"{unparsable} unparsable replies")
    print(f"  claims naming a dose (known false alarms): {len(dose_claims)}  {dose_claims[:6]}")
    print(f"  claims whose content words are mostly in the note already: {note_has}")
    print(f"  claims whose quote is not found in the dialogue: {dlg_lacks}")
    print(f"recorded seconds {seconds:.0f} · notional cost ${cost:.4f} (claude.ai plan, not billed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
