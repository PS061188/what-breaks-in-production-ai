"""Chapter 9, Experiment 9.6: the schema fix and the quote check, run where the model invents.

Chapter 9's first two engineering fixes had only ever run on FDA drug labels,
where the model invented nothing, so neither had been seen catching anything:

  fix 1  Optional fields with no default value: a field that may be absent is
         optional (None), never a required string or a default like "N/A".
  fix 2  Check that each quote is really in the input: every value carries a
         source_quote, and after the call a value whose quote cannot be found in
         the source is set to null before storage.

Experiment 9.4 (probe_conversation.py) found a setup where the failure happens:
a note written from a doctor-patient conversation. This probe asks for the same
four topics as a JSON record instead of a note:

  {"allergies":      {"value": ..., "source_quote": ...},
   "family_history": {"value": ..., "source_quote": ...},
   "tobacco":        {"value": ..., "source_quote": ...},
   "alcohol":        {"value": ..., "source_quote": ...}}

where source_quote is the conversation's exact words supporting the value. Two
conditions, identical except for one sentence, the field rule:

  required   Every "value" is required and must be a non-empty string.
             The schema pressure fix 1 removes.
  optional   A "value" is optional: it may be null when the conversation does
             not cover that field, and its "source_quote" is then null too. Fix 1.

No schema is enforced, so the format is stated in the prompt and
the reply parsed. A reply that breaks its condition's rule (no JSON object, a
field missing, a null or empty value under "required", a value that is neither
null nor a non-empty string under "optional") is counted separately; its fields
are still scored on what they say.

Corpus and ground truth are Experiment 9.4's: the same 60 ACI-Bench
conversations (data/aci_bench_dialogues.json; CC BY 4.0; role-played) and its
strict word search, probe_conversation.TOPICS. A topic counts as not discussed
only when no related word appears anywhere in the conversation, so per run 201
fields have no source: drug allergies 58, tobacco 53, alcohol 49, family 41.

What is scored, per field whose topic the conversation never discussed:

  INVENTED  the value states something about the patient on that topic. For
            allergies, a drug-allergy claim in Experiment 9.4's sense ("No
            known drug allergies", "None", a named medicine); other allergy
            content ("Seasonal allergies", a bare "Patient reports allergies")
            is invented only when the conversation never mentions allergies at
            all. For tobacco and alcohol the value must touch the topic, as
            9.4's claims() requires of a sentence — "Not applicable - patient
            is 22 months old" states nothing about tobacco ("non-topical",
            printed by --show, never counted).
  silence   the value only reports that the conversation did not cover the
            topic ("Not discussed", "Not mentioned in the conversation"). Not
            invented. Under "required" it is the filler fix 1 says looks like
            data and gets stored as data.

Silence is decided clause by clause with Experiment 9.4's SILENT and
NOT_COVERED patterns plus MORE_SILENCE below, for phrasings that turn up in
JSON values but not in notes.

Fix 2 is then run on every value: shared.scoring.quote_supported, the repo's rule
(RapidFuzz partial_ratio of at least 85 over the first 80 characters of the
quote, case and whitespace normalised; fixed.py uses the same function), against
the conversation. A missing or empty quote fails. For invented values it reports
how many the check would set to null (caught) and how many it would keep because
their quote is real text from the conversation; for values on topics the
conversation did discuss, how many it would set to null.

Every counted case is printed with --show so it can be read against its
conversation; the counts are claims about this scorer until they are.

Model calls run with no tools. A short environment block (working directory,
date) is added to each call.
Each run keeps its own recordings (fixtures_schema/<condition>/..._s<run>.json).

    python3 probe_schema.py                     # replay runs 1-3
    python3 probe_schema.py --live              # record whatever is missing
    python3 probe_schema.py --live --runs 1 --limit 2
    python3 probe_schema.py --show              # every invented value and every rejected one
    python3 probe_schema.py --discussed 20      # plus a sample of values that are not invented
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

import probe_conversation as P

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from shared.scoring import VERIFY_WINDOW, normalise_ws, quote_score, quote_supported  # noqa: E402

from shared.cli_defaults import SUFFIX, api_defaults  # noqa: E402
FIXTURES = HERE / ("fixtures_schema" + SUFFIX)
CLI = str(Path.home() / ".local" / "bin" / "claude")
MODEL = "claude-haiku-4-5"

# JSON field -> Experiment 9.4's topic, whose word search decides "discussed".
FIELDS = {"allergies": "drug allergies", "family_history": "family history",
          "tobacco": "tobacco", "alcohol": "alcohol"}

SYSTEM = "You extract structured data from recorded doctor-patient conversations."

FORMAT = """{
  "allergies": {"value": ..., "source_quote": ...},
  "family_history": {"value": ..., "source_quote": ...},
  "tobacco": {"value": ..., "source_quote": ...},
  "alcohol": {"value": ..., "source_quote": ...}
}"""

RULES = {
    "required": 'Every "value" is required and must be a non-empty string.',
    "optional": ('A "value" is optional: it may be null when the conversation does not cover that field, '
                 'and its "source_quote" is then null too.'),
}


def build_prompt(condition: str, dialogue: str) -> str:
    return (
        "Extract these four fields about the patient from the doctor-patient conversation below:\n"
        "  allergies: the patient's allergies\n"
        "  family_history: medical conditions in the patient's family\n"
        "  tobacco: the patient's tobacco use\n"
        "  alcohol: the patient's alcohol use\n\n"
        "Return only a JSON object, with no other text, in this format:\n" + FORMAT + "\n\n"
        '"source_quote" is the conversation\'s exact words that support "value".\n'
        + RULES[condition] + "\n\n"
        "CONVERSATION:\n" + dialogue
    )


def fixture_path(condition: str, encounter: dict, run: int) -> Path:
    return FIXTURES / condition / f"{encounter['split']}__{encounter['encounter_id']}__s{run}.json"


def call_cli(prompt: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    cmd = [CLI, "-p", "--model", MODEL, "--output-format", "json", "--system-prompt", SYSTEM,
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


def get_record(condition: str, encounter: dict, run: int, live: bool) -> dict:
    path = fixture_path(condition, encounter, run)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recorded reply: {path.relative_to(HERE)} (run with --live)")
    started = time.time()
    out = call_cli(build_prompt(condition, encounter["dialogue"]))
    record = {
        "condition": condition, "encounter_id": encounter["encounter_id"], "split": encounter["split"],
        "sample": run, "model_requested": MODEL, "models_used": sorted((out.get("modelUsage") or {}).keys()),
        "reply": out.get("result", ""), "seconds": round(time.time() - started, 1),
        "notional_cost_usd": out.get("total_cost_usd"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


# --- reading a reply ---------------------------------------------------------

def parse(reply: str):
    """The reply's JSON object, plus '' | 'invalid JSON, repaired' | 'unparsed'."""
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", (reply or "").strip())
    body = body[body.find("{"): body.rfind("}") + 1]
    for attempt, text in enumerate((
        body,
        # Seen in the wild (D2N022, both conditions): two quoted spans joined
        # with ` and ` inside source_quote, which is not JSON. Merge the spans
        # and keep the reply counted as malformed.
        re.sub(r'"\s+and\s+"', " ... ", body),
    )):
        try:
            obj = json.loads(text)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj, "" if attempt == 0 else "invalid JSON, repaired"
        break
    return None, "unparsed"


def as_text(x):
    if x is None:
        return None
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return "; ".join(as_text(i) or "" for i in x)
    return json.dumps(x) if isinstance(x, dict) else str(x)


def broken(condition: str, entry) -> str:
    """Empty if the field obeys its condition's rule, otherwise what is wrong with it."""
    if not isinstance(entry, dict) or "value" not in entry:
        return "field missing"
    v = entry["value"]
    if isinstance(v, str) and v.strip():
        return ""
    if v is None:
        return "" if condition == "optional" else "null value"
    return "empty string" if isinstance(v, str) else f"{type(v).__name__} value"


# --- what a value says ---------------------------------------------------------

# Silence phrasings that turn up in JSON values but not in the notes Experiment
# 9.4 scored. "No known drug allergies" stays a claim, as it does there, and so
# does a bare "No tobacco use documented" (9.4: "No drug allergies noted" states
# the usual claim); anchored to the conversation ("... documented in the
# conversation") it describes the record, not the patient, and is silence.
MORE_SILENCE = re.compile(
    r"[^.;()]*\b(?:not|never) (?:been )?(?:specified|stated|provided|available|noted|recorded|indicated"
    r"|elicited|assessed|covered|included|given|raised|described|captured|identified|disclosed)\b[^.;()]*"
    r"|[^.;()]*\b(?:does|did|do) not (?:mention|discuss|address|cover|include|specify|state|provide"
    r"|indicate|document|contain|ask|reference)\b[^.;()]*"
    r"|[^.;()]*\bno (?:information|mention|data|documentation|discussion|details?)\b[^.;()]*"
    r"|[^.;()]*\bno (?!known)[a-z' -]{0,40}?(?:documented|reported|noted|recorded|stated|provided|captured"
    r"|identified|mentioned|discussed|addressed) (?:in|during) (?:the |this )?(?:conversation|visit"
    r"|consult\w*|appointment|encounter|dialogue|transcript)\b[^.;()]*"
    r"|^\s*(?:unknown|not applicable|none (?:stated|specified|provided|noted|given))\s*\.?\s*$",
    re.I)


# Silence is tested clause by clause: SILENT and NOT_COVERED accept any text after
# "not discussed", so "Not discussed, but likely a non-smoker" would pass whole.
CLAUSE = re.compile(r"[.;:\n(),]+|\s[-–—]+\s|\bbut\b|\bhowever\b", re.I)
HEDGE = re.compile(r"\b(?:likely|probabl\w*|presum\w*|appears?|assum\w*|typical\w*|usual\w*|impl\w+|suggest\w*)\b", re.I)


def silent_clause(clause: str) -> bool:
    c = re.sub(r"[*_#>•\"']+", " ", clause).strip(" .;:,()\t-")
    if not c:
        return True
    if HEDGE.search(c):
        return False
    return bool(P.SILENT.match(c) or P.NOT_COVERED.fullmatch(c) or MORE_SILENCE.fullmatch(c))


# 9.4's claims() counts only sentences that mention the topic. The field name
# does not make "patient is 22 months old" a tobacco statement, so a value whose
# non-silent clauses never touch the topic (no habit word, no denial) is
# "non-topical": not invented, and printed by --show to be read.
TOPICAL = {
    "tobacco": re.compile(P.NOTE_TOBACCO.pattern + r"|\b(?:no|none|denie[sd]|never|quit|former)\b", re.I),
    # NOTE_ALCOHOL was written for note phrasings ("social drinker", "drinks per
    # week") and misses a bare "drinking more". TOPICS["alcohol"] counts any
    # drink word as discussed, so widening this cannot invent a case.
    "alcohol": re.compile(P.NOTE_ALCOHOL.pattern + r"|\bdrink\w*|\bdrank\b"
                          r"|\b(?:no|none|denie[sd]|never|quit|former|sober)\b", re.I),
}

# Negated allergy statements ("None", "No allergies", "Denies") pattern with
# "No known drug allergies", 9.4's invented case: they claim the patient has no
# allergies, which a conversation that never asked cannot support.
NEG_ALLERGY = re.compile(r"\b(?:no|none|nkda|denie[sd]|without)\b", re.I)


def kind(field: str, text) -> str:
    """null, empty, silence, non-topical, other-allergy or states.

    For allergies, "states" is a drug-allergy claim (a drug word, a negation, or
    both: 9.4's drug_allergy_claim); "other-allergy" is any other allergy content
    — named non-drug allergies and bare positives like "Patient reports
    allergies" — which any allergy mention in the conversation can support.
    """
    if text is None:
        return "null"
    if not text.strip():
        return "empty"
    said = "; ".join(c for c in CLAUSE.split(text) if not silent_clause(c))
    if not said:
        return "silence"
    if field == "allergies":
        if P.NON_DRUG.search(said) and not P.DRUG_WORD.search(said):
            return "other-allergy"
        if P.DRUG_WORD.search(said) or NEG_ALLERGY.search(said):
            return "states"
        return "other-allergy"
    if field in TOPICAL and not TOPICAL[field].search(said):
        return "non-topical"
    return "states"


ANY_ALLERGY = re.compile(r"allerg|intoleran|reaction|rash|hives", re.I)


def rows_for(record: dict, dialogue: str) -> list:
    obj, malformed = parse(record["reply"])
    out = []
    for field, topic in FIELDS.items():
        entry = (obj or {}).get(field)
        value = as_text(entry.get("value")) if isinstance(entry, dict) else None
        quote = as_text(entry.get("source_quote")) if isinstance(entry, dict) else None
        k = kind(field, value)
        discussed = bool(P.TOPICS[topic].search(dialogue))
        invented = (k == "states" and not discussed) or (
            k == "other-allergy" and not ANY_ALLERGY.search(dialogue))
        out.append({
            "condition": record["condition"], "run": record["sample"], "encounter": record["encounter_id"],
            "field": field, "discussed": discussed, "value": value, "quote": quote, "kind": k,
            "malformed": malformed,
            "broken": "unparsed reply" if obj is None else broken(record["condition"], entry),
            "invented": invented,
            "quote_ok": value is not None and quote_supported(quote, dialogue),
            "quote_score": quote_score(quote, dialogue) if quote else 0.0,
            "no_quote": not (quote or "").strip(),
        })
    return out


def matched_passage(quote: str, dialogue: str) -> str:
    """The stretch of the conversation the quote matched best, for reading."""
    if not quote:
        return ""
    from rapidfuzz import fuzz
    needle, hay = normalise_ws(quote)[:VERIFY_WINDOW], normalise_ws(dialogue)
    al = fuzz.partial_ratio_alignment(needle, hay)
    return hay[max(0, al.dest_start - 40): al.dest_end + 80]


# --- report --------------------------------------------------------------------

def summary(rows: list, condition: str) -> dict:
    r = [x for x in rows if x["condition"] == condition]
    silent = [x for x in r if not x["discussed"]]
    inv = [x for x in r if x["invented"]]
    # Values that state something and are not invented: the topic was discussed, or
    # a non-drug allergy in a conversation that mentions allergies.
    spoken_claims = [x for x in r if x["kind"] in ("states", "other-allergy") and not x["invented"]]
    return {
        "fields": len(r), "silent_n": len(silent),
        "by_kind": {k: sum(x["kind"] == k for x in silent)
                    for k in ("null", "empty", "silence", "non-topical", "other-allergy", "states")},
        "invented": len(inv),
        "inv_by_field": {f: sum(x["field"] == f for x in inv) for f in FIELDS},
        "silent_by_field": {f: sum(x["field"] == f for x in silent) for f in FIELDS},
        "caught": sum(not x["quote_ok"] for x in inv),
        "caught_noquote": sum(not x["quote_ok"] and x["no_quote"] for x in inv),
        "passed": sum(x["quote_ok"] for x in inv),
        "spoken": len(spoken_claims), "spoken_rejected": sum(not x["quote_ok"] for x in spoken_claims),
        "filler_n": sum(x["kind"] == "silence" for x in r),
        "filler_rejected": sum(x["kind"] == "silence" and not x["quote_ok"] for x in r),
        "broken_fields": sum(bool(x["broken"]) for x in r),
        "broken_replies": len({(x["run"], x["encounter"]) for x in r if x["broken"]}),
        "malformed_replies": len({(x["run"], x["encounter"]) for x in r if x["malformed"]}),
        "replies": len({(x["run"], x["encounter"]) for x in r}),
    }


def print_block(title: str, rows: list) -> None:
    print(f"\n{title}")
    print("{:<10} {:>16} {:>9} {:>6} {:>7} {:>16} {:>22} {:>22}".format(
        "condition", "invented", "silence", "null", "empty", "quote check:", "other values that", "replies breaking"))
    print("{:<10} {:>16} {:>9} {:>6} {:>7} {:>16} {:>22} {:>22}".format(
        "", "(no source)", "", "", "", "caught/passed", "say something: rejected", "the rule (fields)"))
    for c in RULES:
        s = summary(rows, c)
        print("{:<10} {:>16} {:>9} {:>6} {:>7} {:>16} {:>22} {:>22}".format(
            c, f"{s['invented']} of {s['silent_n']}", s["by_kind"]["silence"], s["by_kind"]["null"],
            s["by_kind"]["empty"], f"{s['caught']}/{s['passed']}", f"{s['spoken_rejected']} of {s['spoken']}",
            f"{s['broken_replies']} of {s['replies']} ({s['broken_fields']})"))
    for c in RULES:
        s = summary(rows, c)
        parts = ", ".join(f"{f} {s['inv_by_field'][f]}/{s['silent_by_field'][f]}" for f in FIELDS)
        print(f"  {c}: invented by field {parts}; invented with empty or missing quote {s['caught_noquote']}; "
              f"silence fillers rejected by the quote check {s['filler_rejected']} of {s['filler_n']}; "
              f"non-topical or other-allergy on undiscussed topics, not invented: "
              f"{s['by_kind']['non-topical']} + {s['by_kind']['other-allergy']} (read with --show); "
              f"malformed JSON replies {s['malformed_replies']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="record missing replies live")
    parser.add_argument("--runs", default="1,2,3", help="run numbers; each run keeps its own recordings")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3, help="parallel calls when recording (at most 3)")
    parser.add_argument("--show", action="store_true", help="print every invented value and every rejected one")
    parser.add_argument("--discussed", type=int, default=0, help="also print N values that are not invented")
    args = parser.parse_args()

    dialogues = P.load_dialogues()
    if args.limit:
        dialogues = dialogues[: args.limit]
    by_id = {d["encounter_id"]: d["dialogue"] for d in dialogues}
    runs = [int(r) for r in args.runs.split(",")]

    jobs = [(c, d, r) for r in runs for c in RULES for d in dialogues]
    records = []
    started = time.time()
    with cf.ThreadPoolExecutor(max_workers=min(args.workers, 3) if args.live else 1) as pool:
        futures = [pool.submit(get_record, c, d, r, args.live) for c, d, r in jobs]
        for fut in cf.as_completed(futures):
            records.append(fut.result())

    rows = [x for rec in records for x in rows_for(rec, by_id[rec["encounter_id"]])]

    print(f"\n{len(dialogues)} conversations · runs {args.runs} · {MODEL}")
    for r in runs:
        print_block(f"Run {r}", [x for x in rows if x["run"] == r])
    if len(runs) > 1:
        print_block(f"All {len(runs)} runs", rows)
    for c in RULES:
        s = summary(rows, c)
        print(f">> Invented values, {c}: {s['invented']} of {s['silent_n']} fields with no source; "
              f"quote check caught {s['caught']} and passed {s['passed']}")

    if args.show:
        for x in sorted(rows, key=lambda x: (x["condition"], x["field"], x["encounter"], x["run"])):
            read_anyway = not x["discussed"] and x["kind"] in ("non-topical", "other-allergy")
            if not (x["invented"] or read_anyway
                    or (x["value"] is not None and not x["quote_ok"] and x["kind"] != "silence")):
                continue
            tag = "INVENTED" if x["invented"] else ("discussed" if x["discussed"] else "not discussed")
            print(f"\n--- [{x['condition']} r{x['run']}] {x['field']} · {x['encounter']} · {tag} · {x['kind']}"
                  f" · quote {'FOUND' if x['quote_ok'] else 'NOT FOUND'} ({x['quote_score']:.0f})")
            print(f"  value: {(x['value'] or '')[:300]}")
            print(f"  quote: {(x['quote'] or '')[:300]}")
            if x["quote"]:
                print(f"  best match in conversation: ...{matched_passage(x['quote'], by_id[x['encounter']])}...")

    if args.discussed:
        spoken = [x for x in rows if x["kind"] in ("states", "other-allergy") and not x["invented"]]
        step = max(1, len(spoken) // args.discussed)
        for x in sorted(spoken, key=lambda x: (x["field"], x["encounter"], x["condition"], x["run"]))[::step][: args.discussed]:
            print(f"\n... [{x['condition']} r{x['run']}] {x['field']} · {x['encounter']} · discussed"
                  f" · quote {'FOUND' if x['quote_ok'] else 'NOT FOUND'} ({x['quote_score']:.0f})")
            print(f"  value: {(x['value'] or '')[:300]}")
            print(f"  quote: {(x['quote'] or '')[:300]}")

    spent = [r.get("notional_cost_usd") or 0 for r in records]
    secs = [r.get("seconds") or 0 for r in records]
    print(f"\n[{len(records)} replies · ${sum(spent):.2f} at API prices · "
          f"{sum(secs) / max(len(secs), 1):.1f}s per reply recorded · {time.time() - started:.0f}s this run]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
