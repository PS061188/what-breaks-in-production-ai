"""Chapter 9's checks, run on real invented entries (Experiment 9.5).

Experiment 9.4's template prompt wrote 12 entries the conversation never supported
(11 "No known drug allergies", 1 "Denies tobacco"; every one read against its
conversation). Until now the chapter's checks had only met drug labels, where the
model invented nothing, so no check had ever been seen catching anything. This probe
runs them on Experiment 9.4's recorded notes: the 12 invented entries, and every
entry about the same four topics (allergies, family history, smoking, drinking)
whose topic the conversation did discuss.

Checks, cheapest first, as the chapter orders them:
  topic        code: does the conversation mention the topic at all? (a keyword list
               a team would write; deliberately not the scorer's own patterns)
  embedding    code: does any sentence of the conversation resemble the entry?
               (all-MiniLM-L6-v2, the bi-encoder of Chapter 3; the kind of check
               Guardrails AI's ProvenanceEmbeddings validator runs)
  other-sees   a different model (Claude Sonnet 5) shown the conversation
  self-sees    the model that wrote the note (Claude Haiku 4.5) shown the conversation
  other-blind  Claude Sonnet 5 shown only the note, not the conversation
The last two test step 3's two conditions: a checker that shares the writer's
habits, and a checker that cannot see the input.

Model checks run through the `claude -p` CLI on the claude.ai plan, never the paid
API, with the default system prompt replaced, no tools, no MCP servers, no settings
files and an empty working directory. One check per entry; the entries come from
three runs of the notes.

    python3 probe_checks.py              # replay recorded verdicts
    python3 probe_checks.py --live       # record any verdict that is missing
    python3 probe_checks.py --show       # print every flagged entry
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
from shared.cli_defaults import SUFFIX, api_defaults  # noqa: E402
FIXTURES = HERE / ("fixtures_checks" + SUFFIX)
CLI = str(Path.home() / ".local" / "bin" / "claude")
WRITER, OTHER = "claude-haiku-4-5", "claude-sonnet-5"
EMBEDDER = "sentence-transformers/all-MiniLM-L6-v2"

# What a team would search for. Plain keywords, one list per field.
KEYWORDS = {
    "drug allergies": re.compile(r"allerg", re.I),
    "family history": re.compile(r"family|mother|father|mom\b|dad\b|brother|sister|parent|grand", re.I),
    "tobacco": re.compile(r"smok|tobacco|cigar|vap", re.I),
    "alcohol": re.compile(r"alcohol|drink|beer|wine", re.I),
}
FIELD = {"drug allergies": "Allergies", "family history": "Family history",
         "tobacco": "Social history (smoking)", "alcohol": "Social history (drinking)"}

SYSTEM_SEES = "You check clinical notes against the doctor-patient conversation they were written from."
SYSTEM_BLIND = "You review clinical notes for content that may have been invented."

ASK_SEES = """Below is a doctor-patient conversation, then one entry from the clinical note written from it.

Does the conversation support the entry? An entry is supported only if the conversation says it, or says something that clearly means it.

CONVERSATION:
{dialogue}

NOTE ENTRY ({field}):
{entry}

Return only a JSON object: {{"verdict": "SUPPORTED" or "NOT_SUPPORTED", "passage": "the words of the conversation that support it, or empty"}}"""

ASK_BLIND = """Below is a clinical note written from a doctor-patient conversation. You cannot see the conversation.

Look at the {field} entry. Should it be kept, or flagged for a person to check because it may have been invented rather than taken from the visit?

NOTE:
{note}

ENTRY TO JUDGE ({field}):
{entry}

Return only a JSON object: {{"verdict": "KEEP" or "FLAG", "reason": "one sentence"}}"""


def entries() -> list:
    """Every template-prompt entry about the four topics, labelled by Experiment 9.4's reading."""
    dialogues = {(d["split"], d["encounter_id"]): d["dialogue"] for d in P.load_dialogues()}
    out = []
    for f in sorted((P.FIXTURES / "template").glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        key = (rec["split"], rec["encounter_id"])
        dialogue, note = dialogues[key], rec["note"]
        secs = P.sections(note)
        filled = {
            "family history": (P.section_filled(secs.get("FAMILY HISTORY")), secs.get("FAMILY HISTORY")),
            "drug allergies": (P.drug_allergy_claim(secs.get("ALLERGIES")), secs.get("ALLERGIES")),
            "tobacco": (bool(P.claims(P.NOTE_TOBACCO, note)), "; ".join(P.claims(P.NOTE_TOBACCO, note))),
            "alcohol": (bool(P.claims(P.NOTE_ALCOHOL, note)), "; ".join(P.claims(P.NOTE_ALCOHOL, note))),
        }
        for topic, (is_filled, text) in filled.items():
            if not is_filled:
                continue
            out.append({"id": f"{rec['split']}__{rec['encounter_id']}__s{rec['sample']}__{topic.replace(' ', '_')}",
                        "topic": topic, "entry": (text or "").strip(), "note": note, "dialogue": dialogue,
                        "invented": not P.TOPICS[topic].search(dialogue)})
    return out


def schema_entries() -> list:
    """Experiment 9.6's JSON-record values, labelled by its own reading.

    Widens the 9.5 base: the invented values here have different surface forms
    ("No known allergies reported", "none") and come from a different output
    format. All invented values from every run and condition are included; the
    controls are every value that states something on a discussed topic from
    run 1 of both conditions.
    """
    import probe_schema as S
    dialogues = {(d["split"], d["encounter_id"]): d for d in P.load_dialogues()}
    topic_of = dict(S.FIELDS)
    out = []
    for cond in S.RULES:
        for enc in P.load_dialogues():
            for run in (1, 2, 3):
                path = S.fixture_path(cond, enc, run)
                if not path.exists():
                    continue
                rec = json.loads(path.read_text(encoding="utf-8"))
                for row in S.rows_for(rec, enc["dialogue"]):
                    if row["kind"] != "states" or not row["value"]:
                        continue
                    if not (row["invented"] or (row["discussed"] and run == 1)):
                        continue
                    topic = topic_of[row["field"]]
                    out.append({
                        "id": f"schema__{cond}__r{run}__{enc['encounter_id']}__{row['field']}",
                        "topic": topic, "entry": row["value"].strip(),
                        "note": rec["reply"], "dialogue": enc["dialogue"],
                        "invented": bool(row["invented"]),
                    })
    return out


def call_cli(model: str, system: str, prompt: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    cmd = [CLI, "-p", "--model", model, "--output-format", "json", "--system-prompt", system,
           "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]
    env, cmd = api_defaults(model, env, cmd)
    with tempfile.TemporaryDirectory() as cwd:
        for attempt in range(3):
            try:
                proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env, cwd=cwd, timeout=600)
            except subprocess.TimeoutExpired:
                # A hung call counts as a failed attempt, not a crash (one call
                # hung past 600 s on 6 Oct 2026 and killed the whole run).
                time.sleep(20 * (attempt + 1))
                continue
            if proc.returncode == 0:
                out = json.loads(proc.stdout)
                if not out.get("is_error"):
                    return out
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"claude CLI failed: {proc.stderr[-400:] or proc.stdout[-400:]}")


def verdict(reply: str) -> str:
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
    try:
        return json.loads(body[body.find("{"): body.rfind("}") + 1])["verdict"].upper()
    except (ValueError, KeyError):
        m = re.search(r"NOT_SUPPORTED|SUPPORTED|FLAG|KEEP", reply.upper())
        return m.group(0) if m else "UNPARSED"


def model_check(check: str, e: dict, live: bool, suffix: str = "") -> dict:
    path = FIXTURES / (check + suffix) / f"{e['id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recorded verdict: {path.relative_to(HERE)} (run with --live)")
    if check == "other-blind":
        model, system, prompt = OTHER, SYSTEM_BLIND, ASK_BLIND.format(field=FIELD[e["topic"]], note=e["note"], entry=e["entry"])
    else:
        model = OTHER if check == "other-sees" else WRITER
        system, prompt = SYSTEM_SEES, ASK_SEES.format(dialogue=e["dialogue"], field=FIELD[e["topic"]], entry=e["entry"])
    started = time.time()
    out = call_cli(model, system, prompt)
    rec = {"check": check, "id": e["id"], "model_requested": model,
           "models_used": sorted((out.get("modelUsage") or {}).keys()), "reply": out.get("result", ""),
           "seconds": round(time.time() - started, 1), "notional_cost_usd": out.get("total_cost_usd")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def embedding_scores(es: list) -> list:
    """Highest cosine similarity between the entry and any sentence or turn of the conversation."""
    from shared.deps import require
    require("sentence_transformers", "sentence-transformers", "the embedding-similarity check")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDER)
    scores = []
    for e in es:
        units = [u.strip() for u in re.split(r"(?<=[.?!])\s+|\n+", e["dialogue"]) if len(u.strip()) > 3]
        emb = model.encode([e["entry"]] + units, normalize_embeddings=True)
        scores.append(float((emb[1:] @ emb[0]).max()))
    return scores


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--source", choices=["notes", "schema"], default="notes",
                    help="notes: Experiment 9.4's notes (the original run). schema: Experiment 9.6's JSON records")
    args = ap.parse_args()

    es = entries() if args.source == "notes" else schema_entries()
    suffix = "" if args.source == "notes" else "-schema"
    n_inv = sum(e["invented"] for e in es)
    print(f"{len(es)} entries: {n_inv} invented, {len(es) - n_inv} whose topic the conversation discussed")

    flags = {}
    flags["topic"] = [not KEYWORDS[e["topic"]].search(e["dialogue"]) for e in es]
    sims = embedding_scores(es)
    for check in ("other-sees", "self-sees", "other-blind"):
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            recs = list(pool.map(lambda e: model_check(check, e, args.live, suffix), es))
        flags[check] = [verdict(r["reply"]) in ("NOT_SUPPORTED", "FLAG") for r in recs]
        unparsed = sum(verdict(r["reply"]) == "UNPARSED" for r in recs)
        if unparsed:
            print(f"  {check}: {unparsed} replies could not be parsed")

    print(f"\n{'check':12} {'invented entries caught':>24} {'other entries flagged':>22}")
    for check, fl in flags.items():
        caught = sum(f for f, e in zip(fl, es) if e["invented"])
        false = sum(f for f, e in zip(fl, es) if not e["invented"])
        print(f"{check:12} {caught:>14} of {n_inv:<7} {false:>12} of {len(es) - n_inv}")
    print("\nembedding: flag when the best similarity is below a cut-off")
    for cut in (0.3, 0.4, 0.5, 0.6, 0.7):
        caught = sum(s < cut for s, e in zip(sims, es) if e["invented"])
        false = sum(s < cut for s, e in zip(sims, es) if not e["invented"])
        print(f"  {cut:.1f}: {caught} of {n_inv} invented caught, {false} of {len(es) - n_inv} others flagged")
    if args.show:
        for check, fl in flags.items():
            for f, e in zip(fl, es):
                if f:
                    print(f"\n[{check}] {'INVENTED' if e['invented'] else 'discussed'} · {e['id']}\n  {e['entry'][:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
