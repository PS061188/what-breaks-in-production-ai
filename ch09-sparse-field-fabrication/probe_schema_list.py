"""Experiment 9.7: a list of quotes per value, so a two-place value can be checked.

Experiment 9.6's schema carries one source_quote per value. Its read rejection
case is a correct value whose evidence sits in two places of the conversation;
the model glued both into one quote, no single stretch matched, and the check
rejected it (scored 82 against the 85 cut-off). The book's fix-2 note proposes
the schema change: "source_quotes" as a LIST, each item one continuous passage,
each checked on its own. This probe measures that change on the same sixty
ACI-Bench conversations (data/aci_bench_dialogues.json), one condition:

  optional-list  fields may be null (fix 1), and "source_quotes" is a list,
                 one item per place in the conversation.

Three runs. The comparison baseline is Experiment 9.6's recorded "optional"
condition (single quote): wrong rejections there were 3 of 92 discussed-topic
values; invented values 2 of 603, one caught by the quote gate.

Gate semantics reported here, strictest first:
  all-found   a value is kept only when every quote in its list is found
  any-found   kept when at least one quote is found

    python3 probe_schema_list.py              # replay recorded replies
    python3 probe_schema_list.py --live       # record any missing reply
    python3 probe_schema_list.py --show       # print every counted case
"""

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import probe_schema as S  # noqa: E402
from shared.scoring import quote_supported  # noqa: E402

COND = "optional-list"
RUNS = (1, 2, 3)

FORMAT = """{
  "allergies": {"value": ..., "source_quotes": [...]},
  "family_history": {"value": ..., "source_quotes": [...]},
  "tobacco": {"value": ..., "source_quotes": [...]},
  "alcohol": {"value": ..., "source_quotes": [...]}
}"""

RULE = ('"source_quotes" is a list of the conversation\'s exact word-for-word passages that '
        'together support "value". Use one list item for each separate place in the '
        'conversation; never join two places into one item. '
        'A "value" is optional: it may be null when the conversation does not cover that '
        'field, and its "source_quotes" is then null too.')


def build_prompt(dialogue: str) -> str:
    return (
        "Extract these four fields about the patient from the doctor-patient conversation below:\n"
        "  allergies: the patient's allergies\n"
        "  family_history: medical conditions in the patient's family\n"
        "  tobacco: the patient's tobacco use\n"
        "  alcohol: the patient's alcohol use\n\n"
        "Return only a JSON object, with no other text, in this format:\n" + FORMAT + "\n\n"
        + RULE + "\n\n"
        "CONVERSATION:\n" + dialogue
    )


def call(prompt: str) -> dict:
    """S.call_cli, with a hung call treated as a failed attempt (probe_checks lesson)."""
    for attempt in range(3):
        try:
            return S.call_cli(prompt)
        except subprocess.TimeoutExpired:
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("claude CLI hung three times")


def get_record(encounter: dict, run: int, live: bool) -> dict:
    path = S.fixture_path(COND, encounter, run)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recorded reply: {path.relative_to(HERE)} (run with --live)")
    started = time.time()
    out = call(build_prompt(encounter["dialogue"]))
    record = {"condition": COND, "encounter_id": encounter["encounter_id"], "split": encounter["split"],
              "sample": run, "model_requested": S.MODEL,
              "models_used": sorted((out.get("modelUsage") or {}).keys()),
              "reply": out.get("result", ""), "seconds": round(time.time() - started, 1),
              "notional_cost_usd": out.get("total_cost_usd")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def rows_for(record: dict, dialogue: str) -> list:
    obj, malformed = S.parse(record["reply"])
    out = []
    for field, topic in S.FIELDS.items():
        entry = (obj or {}).get(field)
        value = S.as_text(entry.get("value")) if isinstance(entry, dict) else None
        quotes = entry.get("source_quotes") if isinstance(entry, dict) else None
        if quotes is None:
            qlist = []
        elif isinstance(quotes, list):
            qlist = [S.as_text(q) for q in quotes if S.as_text(q)]
        else:
            qlist = [S.as_text(quotes)] if S.as_text(quotes) else []
        kind = S.kind(field, value)
        discussed = bool(S.P.TOPICS[topic].search(dialogue))
        invented = (kind == "states" and not discussed) or (
            kind == "other-allergy" and not S.ANY_ALLERGY.search(dialogue))
        found = [bool(q) and quote_supported(q, dialogue) for q in qlist]
        out.append({
            "run": record["sample"], "encounter": record["encounter_id"], "field": field,
            "kind": kind, "discussed": discussed, "invented": invented, "value": value,
            "quotes": qlist, "found": found, "n_quotes": len(qlist),
            "all_found": bool(qlist) and all(found),
            "any_found": any(found),
            "malformed": malformed,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    dialogues = S.P.load_dialogues()
    by_id = {(d["split"], d["encounter_id"]): d["dialogue"] for d in dialogues}
    jobs = [(d, r) for r in RUNS for d in dialogues]
    with cf.ThreadPoolExecutor(max_workers=min(args.workers, 3) if args.live else 1) as pool:
        records = list(pool.map(lambda j: get_record(j[0], j[1], args.live), jobs))

    rows = []
    for (d, r), rec in zip(jobs, records):
        rows.extend(rows_for(rec, by_id[(d["split"], d["encounter_id"])]))

    print(f"{len(dialogues)} conversations x runs {RUNS} · {S.MODEL} via the subscription CLI · "
          f"condition {COND}\n")
    print(f"{'run':>3} {'states/disc':>11} {'rej all-found':>13} {'rej any-found':>13} "
          f"{'invented':>8} {'inv caught (all/any)':>20} {'null':>5} {'multi-quote':>11}")
    for r in RUNS:
        rr = [x for x in rows if x["run"] == r]
        disc = [x for x in rr if x["kind"] == "states" and x["discussed"]]
        inv = [x for x in rr if x["invented"]]
        nulls = sum(1 for x in rr if x["value"] is None)
        multi = sum(1 for x in rr if x["n_quotes"] >= 2)
        rej_all = sum(1 for x in disc if not x["all_found"])
        rej_any = sum(1 for x in disc if not x["any_found"])
        c_all = sum(1 for x in inv if not x["all_found"])
        c_any = sum(1 for x in inv if not x["any_found"])
        print(f"{r:>3} {len(disc):>11} {rej_all:>13} {rej_any:>13} {len(inv):>8} "
              f"{c_all:>12}/{c_any:<7} {nulls:>5} {multi:>11}")

    disc = [x for x in rows if x["kind"] == "states" and x["discussed"]]
    inv = [x for x in rows if x["invented"]]
    print(f"\n>> Discussed-topic values wrongly rejected, every quote must be found: "
          f"{sum(1 for x in disc if not x['all_found'])} of {len(disc)} "
          f"(Experiment 9.6's single quote: 3 of 92)")
    no_source = sum(1 for x in rows if not x["discussed"])
    print(f">> Invented values: {len(inv)} of {no_source} fields with no source; "
          f"quote gate (all-found) caught {sum(1 for x in inv if not x['all_found'])}")
    print(f">> Values carrying two or more quotes: {sum(1 for x in rows if x['n_quotes'] >= 2)} "
          f"of {sum(1 for x in rows if x['value'] is not None)} non-null values")

    if args.show:
        for x in rows:
            if x["invented"] or (x["kind"] == "states" and x["discussed"] and not x["all_found"]):
                tag = "INVENTED" if x["invented"] else "REJECTED(all-found)"
                print(f"\n--- [{tag}] r{x['run']} {x['encounter']} {x['field']}\n  value: {x['value']}")
                for q, f in zip(x["quotes"], x["found"]):
                    print(f"  quote[{'found' if f else 'MISSING'}]: {q[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
