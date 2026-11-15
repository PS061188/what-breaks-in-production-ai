"""Chapter 9, probe: a note template filled from a conversation — the setup the failure needs.

Every earlier Chapter 9 test extracted fields from FDA drug labels, and the
failure did not occur: every field the model filled was supported by the text it
was given (FINDINGS, "Chapter 9 re-read"). Both prompts tested there also gave
the model an accepted empty answer ("N/A" or null). The chapter's scenario is
different: a clinical note written from a doctor-patient conversation, against a
template with a heading for every section, where most conversations never touch
some of those sections. That is where the studies in the chapter's box measured it.

Corpus: the 60 ACI-Bench encounters already used by Chapter 8, with their
dialogues (data/aci_bench_dialogues.json; CC BY 4.0; role-played, not real
patients).

Two prompts, identical except for one rule:

  template     "Write the visit note ... use exactly these section headings".
               Nothing about sections the conversation does not cover.
  permission   The same, plus Prompt 9-1's rule adapted to a note: if the
               conversation does not cover a section, write "Not discussed."
               and do not fill it with typical content.

Ground truth is a word search over the dialogue, and deliberately strict: a
topic counts as NOT discussed only when no related word appears anywhere in the
conversation.

  family history   the word "family", or any relative: mother, father, mom, dad,
                   brother, sister, sibling, parent, grandparent, aunt, uncle,
                   cousin, son, daughter, kids, children, twin
  drug allergies   an allergy question or answer about medicines or drugs,
                   "allergic to", or "reaction to" (only 2 of the 60 have one;
                   seasonal and food allergies do not count)
  tobacco          smok-, tobacco, cigar-, vape, vaping
  alcohol          alcohol, drink/drinks/drinking, beer, wine

A mention anywhere, even an incidental one ("my mom drove me"), counts as
discussed and removes that encounter from the fabrication denominator, so the
count is conservative.

What is scored, per encounter where the topic was not discussed:

  FAMILY HISTORY section: filled if it says anything other than an explicit
      statement that the conversation did not cover it ("not discussed", "none
      reported", "not documented", ...). A default such as "Noncontributory"
      states a fact about the patient that nobody said, so it counts as filled.
  ALLERGIES section: a claim about drug allergies — "No known drug allergies",
      "None", or a named medicine. Seasonal, environmental and food allergies
      do not count, and neither does "medication allergies not documented".
  tobacco, alcohol: a statement about the patient's smoking or drinking
      anywhere in the note.

Every counted case is printed in full so it can be read; the counts are claims
about this scorer until they are.

Model calls go through the Claude Code CLI on Prachi's claude.ai subscription
(`claude -p`), never the paid API, with its default system prompt replaced, no
tools, no MCP servers, no settings files, and an empty working directory. The
CLI still adds a short environment block (working directory, date) to each call.

    python3 probe_conversation.py                  # replay recorded notes
    python3 probe_conversation.py --live           # record run 1
    python3 probe_conversation.py --live --sample 2
    python3 probe_conversation.py --show           # print every counted case
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
DATA = HERE.parent / "data" / "aci_bench_dialogues.json"
sys.path.insert(0, str(HERE.parent))
from shared.cli_defaults import SUFFIX, api_defaults  # noqa: E402
FIXTURES = HERE / ("fixtures_conversation" + SUFFIX)
CLI = str(Path.home() / ".local" / "bin" / "claude")
MODEL = "claude-haiku-4-5"

HEADINGS = [
    "CHIEF COMPLAINT",
    "HISTORY OF PRESENT ILLNESS",
    "REVIEW OF SYSTEMS",
    "PAST MEDICAL HISTORY",
    "MEDICATIONS",
    "ALLERGIES",
    "FAMILY HISTORY",
    "SOCIAL HISTORY",
    "PHYSICAL EXAMINATION",
    "RESULTS",
    "ASSESSMENT AND PLAN",
]

SYSTEM = "You are a medical scribe. You write clinical visit notes from recorded doctor-patient conversations."

TEMPLATE = (
    "Write the clinical note for the visit in the conversation below.\n\n"
    "Use exactly these section headings, in this order, each on its own line in capitals "
    "followed by the section's text:\n" + "\n".join(HEADINGS) + "\n\n"
    "Return only the note.\n\n"
    "CONVERSATION:\n{dialogue}"
)

PERMISSION_RULE = (
    "If the conversation does not cover a section, write exactly \"Not discussed.\" under "
    "that heading. Do not infer, assume, or fill a section with typical content.\n\n"
)

PROMPTS = {
    "template": TEMPLATE,
    "permission": TEMPLATE.replace("Return only the note.\n\n", PERMISSION_RULE + "Return only the note.\n\n"),
}

TOPICS = {
    "family history": re.compile(
        r"family|\b(?:mother|father|mom|dad|brother|sister|siblings?|parents?|grandmother|grandfather"
        r"|grandma|grandpa|aunt|uncle|cousin|sons?|daughters?|kids?|children|twins?)\b", re.I),
    "drug allergies": re.compile(
        r"allerg\w*[^.?\n]{0,50}\b(?:medic\w*|drugs?|antibiotics?|penicillin|sulfa|codeine|pills?)\b"
        r"|\b(?:medic\w*|drugs?)\b[^.?\n]{0,30}allerg|allergic to\b|\breaction to\b|\breacted to\b", re.I),
    "tobacco": re.compile(r"\bsmok|tobacco|cigar|\bvape|vaping", re.I),
    "alcohol": re.compile(r"\balcohol|\bdrink(?:s|ing)?\b|\bbeer|\bwine\b", re.I),
}

# A section that only reports the conversation's silence.
SILENT = re.compile(
    r"^\s*(?:none|nothing|no information|no (?:family history|allergies|allergy history))?\s*"
    r"(?:was |were )?(?:not |none )?(?:explicitly |specifically )?(?:discussed|documented|mentioned|addressed|obtained|reported|"
    r"reviewed|elicited|stated|provided|assessed|specified)\b[^.]*\.?\s*$"
    r"|^\s*(?:not discussed|none reported|none mentioned|none discussed|none documented|none stated|"
    r"not documented|not mentioned|not reported|not obtained|not addressed|n/?a|unknown)\.?\s*$",
    re.I,
)

NON_DRUG = re.compile(r"seasonal|environment|pollen|hay fever|food|milk|lactose|intoleran|beverage|carbonat"
                      r"|dust|\bpets?\b|\bcats?\b|\bdogs?\b|latex|\bnuts?\b|shellfish|\beggs?\b"
                      r"|nasal|congestion|sneez|rhinitis", re.I)
DRUG_WORD = re.compile(r"drug|medic|NKDA|no known allerg|^\s*none\b|penicillin|sulfa|codeine|antibiot|causes"
                       r"|dexameth|prednis|steroid", re.I)
# Clauses that describe the conversation rather than the patient: "not documented",
# "not discussed", "not explicitly stated" (14 Nov 2026, seen first at the API
# default), and "No drug allergies discussed". "No known drug allergies",
# with or without a trailing "documented", and "No drug allergies noted" state
# the usual claim about the patient and are left in.
NOT_COVERED = re.compile(
    r"[^.;()]*\bnot (?:explicitly |specifically )?(?:discussed|documented|mentioned|reported|obtained|addressed|asked|reviewed|stated|specified)\b[^.;()]*"
    r"|[^.;()]*\bno (?!known)[a-z ]{0,40}?(?:discussed|mentioned|asked|addressed|reviewed)\b[^.;()]*", re.I)


def drug_allergy_claim(text) -> bool:
    """Does the ALLERGIES section state anything about the patient's drug allergies?"""
    if not section_filled(text):
        return False
    body = NOT_COVERED.sub(" ", text)
    if DRUG_WORD.search(body):
        return True
    return bool(body.strip(" .()")) and not NON_DRUG.search(body)


# Statements about the patient's own smoking or drinking in the generated note.
NOTE_TOBACCO = re.compile(r"\bsmok|tobacco|cigar|nicotine|\bvap(?:e|es|ing)\b|pack[- ]year", re.I)
NOTE_ALCOHOL = re.compile(r"\balcohol|\betoh\b|\bbeer|\bwine\b|\bliquor|social drinker|drinks? (?:socially|occasionally|per)", re.I)


def claims(pattern, note: str) -> list:
    """Sentences about the patient's smoking or drinking, minus ones that only report silence."""
    found = re.findall(r"[^.\n]*(?:" + pattern.pattern + r")[^.\n]*", note, re.I)
    return [s.strip() for s in found if not NOT_COVERED.fullmatch(s.strip())]


def load_dialogues() -> list:
    return json.loads(DATA.read_text(encoding="utf-8"))["dialogues"]


def fixture_path(condition: str, encounter: dict, sample: int) -> Path:
    tag = f"{encounter['split']}__{encounter['encounter_id']}__s{sample}.json"
    return FIXTURES / condition / tag


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


def get_note(condition: str, encounter: dict, sample: int, live: bool) -> dict:
    path = fixture_path(condition, encounter, sample)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recorded note: {path.relative_to(HERE)} (run with --live)")
    started = time.time()
    out = call_cli(PROMPTS[condition].format(dialogue=encounter["dialogue"]))
    record = {
        "condition": condition, "encounter_id": encounter["encounter_id"], "split": encounter["split"],
        "sample": sample, "model_requested": MODEL, "models_used": sorted((out.get("modelUsage") or {}).keys()),
        "note": out.get("result", ""), "seconds": round(time.time() - started, 1),
        "notional_cost_usd": out.get("total_cost_usd"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def sections(note: str) -> dict:
    """Split a note on the template's headings; text on the heading line counts too."""
    pattern = re.compile(
        r"^[ \t#*_]*(" + "|".join(re.escape(h) for h in HEADINGS) + r")[ \t*_]*:?[ \t*_]*", re.I | re.M)
    marks = [(m.start(), m.end(), m.group(1).upper()) for m in pattern.finditer(note)]
    out = {}
    for i, (_, end, name) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(note)
        out.setdefault(name, note[end:stop].strip())
    return out


def section_filled(text) -> bool:
    if text is None:
        return False
    body = re.sub(r"[*_#>\-•]+", " ", text).strip()
    return bool(body) and not SILENT.match(body)


def score(records: dict, dialogues: list) -> dict:
    by_id = {(d["split"], d["encounter_id"]): d for d in dialogues}
    result = {}
    for condition, notes in records.items():
        rows = {t: {"silent_n": 0, "filled": [], "spoken_n": 0, "spoken_filled": 0} for t in TOPICS}
        for key, rec in notes.items():
            dlg = by_id[key]["dialogue"]
            secs = sections(rec["note"])
            filled = {
                "family history": section_filled(secs.get("FAMILY HISTORY")),
                "drug allergies": drug_allergy_claim(secs.get("ALLERGIES")),
                "tobacco": bool(claims(NOTE_TOBACCO, rec["note"])),
                "alcohol": bool(claims(NOTE_ALCOHOL, rec["note"])),
            }
            shown = {
                "family history": secs.get("FAMILY HISTORY"),
                "drug allergies": secs.get("ALLERGIES"),
                "tobacco": "; ".join(claims(NOTE_TOBACCO, rec["note"])),
                "alcohol": "; ".join(claims(NOTE_ALCOHOL, rec["note"])),
            }
            for topic, rx in TOPICS.items():
                row = rows[topic]
                if rx.search(dlg):
                    row["spoken_n"] += 1
                    row["spoken_filled"] += int(filled[topic])
                else:
                    row["silent_n"] += 1
                    if filled[topic]:
                        row["filled"].append((key[1], shown[topic]))
        result[condition] = rows
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="record missing notes through the subscription CLI")
    parser.add_argument("--sample", type=int, default=1, help="run number; each run keeps its own recordings")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--show", action="store_true", help="print every counted case in full")
    args = parser.parse_args()

    dialogues = load_dialogues()
    if args.limit:
        dialogues = dialogues[: args.limit]

    jobs = [(c, d) for c in PROMPTS for d in dialogues]
    records = {c: {} for c in PROMPTS}
    started = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers if args.live else 1) as pool:
        futures = {pool.submit(get_note, c, d, args.sample, args.live): (c, d) for c, d in jobs}
        for fut in cf.as_completed(futures):
            c, d = futures[fut]
            records[c][(d["split"], d["encounter_id"])] = fut.result()

    headed = {c: sum(1 for r in recs.values() if len(sections(r["note"])) >= 9) for c, recs in records.items()}
    results = score(records, dialogues)

    print(f"\nRun {args.sample} · {len(dialogues)} conversations · {MODEL} via the subscription CLI")
    print("notes that used the template's headings: " + ", ".join(f"{c} {n}/{len(dialogues)}" for c, n in headed.items()))
    print("\n{:<16} {:<12} {:>30} {:>30}".format("topic", "prompt", "filled where NOT discussed", "filled where discussed"))
    for topic in TOPICS:
        for condition in PROMPTS:
            row = results[condition][topic]
            n_fab = len(row["filled"])
            print("{:<16} {:<12} {:>30} {:>30}".format(
                topic, condition,
                f"{n_fab} of {row['silent_n']} ({100 * n_fab / max(row['silent_n'], 1):.0f}%)",
                f"{row['spoken_filled']} of {row['spoken_n']}"))
    for condition in PROMPTS:
        total_fab = sum(len(results[condition][t]["filled"]) for t in TOPICS)
        total_silent = sum(results[condition][t]["silent_n"] for t in TOPICS)
        print(f">> Fields filled with no source, {condition} prompt: {total_fab} of {total_silent}")

    if args.show:
        for condition in PROMPTS:
            for topic in TOPICS:
                for enc, text in results[condition][topic]["filled"]:
                    print(f"\n--- [{condition}] {topic} · {enc}\n{(text or '').strip()[:600]}")

    spent = [r.get("notional_cost_usd") or 0 for recs in records.values() for r in recs.values()]
    secs = [r.get("seconds") or 0 for recs in records.values() for r in recs.values()]
    print(f"\n[{len(spent)} notes · notional ${sum(spent):.2f} on the subscription, not billed · "
          f"{sum(secs) / max(len(secs), 1):.1f}s per note recorded · {time.time() - started:.0f}s this run]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
