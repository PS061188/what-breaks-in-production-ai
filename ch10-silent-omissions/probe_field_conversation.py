"""Experiment 10.7 — Prompt 10-1's `not_extracted` field on text whose items are not delimited.

Every measurement of the field so far ran on FDA dosing sections, where every
dose carries a unit and a pattern can count them (Experiment 10.2: 8 entries on
3 of 6 labels, all correct judgement calls, 0 of 2 missing doses named). The
chapter went on to say that on a document whose items are not clearly delimited
the field "fills with noise rather than judgement". Nothing had measured that.

This probe puts Prompt 10-1, as printed in the book, to the 60 ACI-Bench
doctor-patient conversations (data/aci_bench_dialogues.json; role-played, CC BY
4.0) with {item_type} = "medication dose amount". Doses in a conversation are
spoken inside sentences, sometimes as words ("a thousand milligrams", "seven
and a half"), sometimes retracted mid-sentence, next to lab values and salt
targets that look like doses. A reader has to decide what counts.

Ground truth is Experiment 10.5's extractor (exp105_dialogue_doses/count_doses.py):
every number + mass/unit word in the dialogue, with its exclusions (lab values
per deciliter, dietary sodium targets, body mass) printed and auditable — 64
unique (dialogue, dose) pairs across 39 of the 60 conversations. The other 21
conversations state no dose, which tests what the field does when there is
nothing to leave out.

What is scored, per run:
  returned          ground-truth doses present in `extracted`
  silent omission   a ground-truth dose in neither `extracted` nor `not_extracted`
  routed            a ground-truth dose absent from `extracted` but named in `not_extracted`
  extras            `extracted` strings whose dose is not a ground-truth dose, classified:
                    excluded-by-ruler (lab value, sodium target, body mass) /
                    other number in the dialogue / not found in the dialogue
  field entries     every `not_extracted` entry, classified the same way, plus
                    "no dose unit" for durations, frequencies and unit-less numbers
Every entry and every extra is printed verbatim with its reason. The classes
are the scorer's claim; the printed cases are the record. Read them.

Model calls go through the Claude Code CLI on Prachi's claude.ai subscription
(`claude -p`), never the paid API, with the printed prompt as the system prompt,
no tools, no MCP servers, no settings files, an empty working directory.

    python3 probe_field_conversation.py                  # replay recorded runs
    python3 probe_field_conversation.py --live --sample 1
    python3 probe_field_conversation.py --show           # print every case
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
sys.path.insert(0, str(HERE / "exp105_dialogue_doses"))
from count_doses import dialogue_doses, extract  # noqa: E402

DATA = HERE.parent / "data" / "aci_bench_dialogues.json"
sys.path.insert(0, str(HERE.parent))
from shared.cli_defaults import SUFFIX, api_defaults  # noqa: E402
FIXTURES = HERE / ("fixtures_field_conversation" + SUFFIX)
CLI = str(Path.home() / ".local" / "bin" / "claude")
MODEL = "claude-haiku-4-5"
ITEM_TYPE = "medication dose amount"

# Prompt 10-1 exactly as printed in the book, with {item_type} substituted.
SYSTEM = """You are an extraction engine. Completeness is the quality measure
here, not brevity. A short list that looks tidy is worse than a long
one that is right.

Extract every {item_type} the document contains.

Then, in "not_extracted", record anything you considered and left out,
with a one-line reason. Examples of what belongs there:
  - a value that is not a {item_type} but could be mistaken for one
  - a figure you could not read with confidence
  - something ambiguous enough that a person should decide

An empty "not_extracted" list is a claim that nothing was ambiguous.
Do not make that claim lightly.

Return:
{
  "extracted": [ ... ],
  "not_extracted": [
    { "text": "<what you left out>", "reason": "<why>" }
  ]
}""".replace("{item_type}", ITEM_TYPE)

USER = "DOCUMENT:\n{dialogue}\n\nReturn only the JSON object."

# The one-line narrowing tested as the fourth condition: the printed prompt with a
# rule that the field is for look-alike values, not for every item without an amount.
NARROW_RULE = ("Do not list items that simply have no amount. List only values that could be "
               "mistaken for a {item_type}.\n\n").replace("{item_type}", ITEM_TYPE)
PROMPTS = {
    "as-printed": SYSTEM,
    "narrowed": SYSTEM.replace('An empty "not_extracted" list', NARROW_RULE + 'An empty "not_extracted" list'),
}
assert PROMPTS["narrowed"] != SYSTEM


def load_dialogues() -> list:
    return json.loads(DATA.read_text(encoding="utf-8"))["dialogues"]


def fixture_path(encounter: dict, sample: int, condition: str = "as-printed") -> Path:
    sub = f"s{sample}" if condition == "as-printed" else f"{condition}/s{sample}"
    return FIXTURES / sub / f"{encounter['split']}__{encounter['encounter_id']}.json"


def call_cli(prompt: str, system: str = SYSTEM) -> dict:
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


def parse_json(text: str):
    """The JSON object in the model's reply, or None."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < 0:
        return None
    try:
        obj = json.loads(t[a:b + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "extracted" not in obj:
        return None
    return obj


def get_record(encounter: dict, sample: int, live: bool, condition: str = "as-printed") -> dict:
    path = fixture_path(encounter, sample, condition)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recording: {path.relative_to(HERE)} (run with --live)")
    started = time.time()
    out = call_cli(USER.format(dialogue=encounter["dialogue"]), PROMPTS[condition])
    result = out.get("result", "")
    attempts = 1
    if parse_json(result) is None:            # one retry on an unparsable reply
        out = call_cli(USER.format(dialogue=encounter["dialogue"]), PROMPTS[condition])
        result = out.get("result", "")
        attempts = 2
    record = {
        "experiment": "10.7", "condition": condition, "item_type": ITEM_TYPE,
        "encounter_id": encounter["encounter_id"], "split": encounter["split"], "sample": sample,
        "model_requested": MODEL, "models_used": sorted((out.get("modelUsage") or {}).keys()),
        "result": result, "parsed": parse_json(result), "attempts": attempts,
        "seconds": round(time.time() - started, 1), "notional_cost_usd": out.get("total_cost_usd"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def doses_in(text: str) -> set:
    """Canonical dose strings a piece of text names, with no exclusions applied."""
    return {m["canonical"] for m in extract(str(text).lower(), permissive=True) if m["canonical"]}


NOT_A_DOSE = re.compile(
    r"lab|vital|blood pressure|temperature|reflex|murmur|grad(?:e|ing)|measurement|size|a1c|glucose|sugar"
    r"|cholesterol|disabilit|consumption|alcohol|cigarette|beer|surface area|\bvalue|reading|resection|tissue"
    r"|electrolyte|potassium level|percent|weight|bmi|physical therapy|not a medication|notation|rating", re.I)
HOW_OFTEN = re.compile(
    r"frequenc|duration|interval|route|how often|schedule|timing|per (?:day|week)|(?:once|twice) (?:a|per) day"
    r"|every (?:day|\w+ hours)|as needed|times (?:a|per) (?:day|week)|for \w+ days|\bdays?\b|\bweeks?\b", re.I)
HIDDEN_AMOUNT = re.compile(
    r"\b(?:puffs?|tablets?|pills?|caps?(?:ules?)?|cc|ml|milliliters?|teaspoons?|tsp|drops?|sprays?|patch(?:es)?"
    r"|ounces?|oz|%|percent)\b|\b(?:one|two|three|four|half|\d+(?:\.\d+)?)\s+(?:advils?|tylenols?|ibuprofens?|prednisone)", re.I)
UNITLESS_NUMBER = re.compile(r"\d")


def subclass(text: str, reason: str, in_field: bool) -> str:
    """Why a string with no dose unit is in the field (or in the extraction)."""
    t, r = str(text), str(reason)
    if HIDDEN_AMOUNT.search(t):
        return "amount in a form the ruler cannot see (puffs, tablets, cc, mL, teaspoons, %)"
    if NOT_A_DOSE.search(r) or NOT_A_DOSE.search(t):
        return "a number that is not a dose (lab value, vital sign, exam grade, measurement, habit)"
    if in_field and re.search(r"no (?:specific |numerical |quantified |actual |active )?(?:dose|dosage|amount|mg)", r, re.I) \
            and not UNITLESS_NUMBER.search(t) and not HOW_OFTEN.search(t):
        return "a medicine named without any amount"
    if HOW_OFTEN.search(t) or HOW_OFTEN.search(r):
        return "frequency, duration or route, no amount"
    if UNITLESS_NUMBER.search(t):
        return "a number the dialogue states without a unit"
    if in_field or not re.search(r"\d", t):
        # With thinking off (the API default), the extraction itself lists bare
        # medicine names ("aspirin", "Coreg (for hypertension)"); no digit, no amount.
        return "a medicine named without any amount"
    return "other"


def classify(canons: set, truth: dict, all_in_dialogue: set, excluded: dict, returned: set) -> str:
    """One label for a field entry or an extra, from the doses its text names."""
    if not canons:
        return "no dose unit"
    if canons & set(truth["doses"]):
        return "ground-truth dose" if not (canons & returned) else "hedge on an extracted dose"
    hit = [excluded[c] for c in canons if c in excluded]
    if hit:
        return "excluded by ruler: " + hit[0]
    if canons & all_in_dialogue:
        return "other number+unit in dialogue"
    return "not found in dialogue"


def score(records: dict, truth_all: dict) -> dict:
    """Per-run counts, plus every case for printing."""
    s = {
        "dialogues": 0, "unparsable": 0, "gt": 0, "returned": 0, "silent": [], "routed": [],
        "extras": {}, "entries": {}, "field_filled_with_doses": 0, "field_filled_without_doses": 0,
        "n_with_doses": 0, "n_without_doses": 0, "cases": [],
    }
    for key, rec in sorted(records.items()):
        truth = truth_all[key]
        s["dialogues"] += 1
        gt = set(truth["doses"])
        s["gt"] += len(gt)
        has = bool(gt)
        s["n_with_doses" if has else "n_without_doses"] += 1
        obj = rec.get("parsed")
        if obj is None:
            s["unparsable"] += 1
            s["silent"].extend((key[1], d) for d in sorted(gt))
            s["cases"].append((key, "UNPARSABLE", rec.get("result", "")[:300]))
            continue
        extracted = obj.get("extracted") or []
        entries = obj.get("not_extracted") or []
        all_in = doses_in(truth["text"])
        excluded = {m["canonical"]: m["excluded"] for m in truth["mentions"] if m["excluded"] and m["canonical"]}
        returned = set()
        for item in extracted:
            returned |= doses_in(item)
        hit = gt & returned
        s["returned"] += len(hit)
        field_named = set()
        for e in entries:
            text = e.get("text", e) if isinstance(e, dict) else e
            field_named |= doses_in(text)
        for d in sorted(gt - returned):
            if d in field_named:
                s["routed"].append((key[1], d))
            else:
                s["silent"].append((key[1], d))
        for item in extracted:
            canons = doses_in(item)
            if canons and not (canons & gt):
                label = classify(canons, truth, all_in, excluded, returned)
                if label == "not found in dialogue" and stated_without_unit(canons, truth["text"]):
                    label = "unit added to a number the dialogue states without one"
                s["extras"].setdefault(label, []).append((key[1], str(item)))
            elif not canons:
                s["extras"].setdefault(subclass(item, "", in_field=False), []).append((key[1], str(item)))
        if entries:
            s["field_filled_with_doses" if has else "field_filled_without_doses"] += 1
        for e in entries:
            if isinstance(e, dict):
                text, reason = str(e.get("text", "")), str(e.get("reason", ""))
            else:
                text, reason = str(e), ""
            canons = doses_in(text)
            label = classify(canons, truth, all_in, excluded, returned)
            if label == "no dose unit":
                label = subclass(text, reason, in_field=True)
            elif label == "not found in dialogue" and stated_without_unit(canons, truth["text"]):
                label = "unit added to a number the dialogue states without one"
            s["entries"].setdefault(label, []).append((key[1], text, reason))
    return s


_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_words(amount: float) -> list:
    """Spoken forms of a number: 2.5 -> 'two point five'; 500 -> 'five hundred'."""
    forms = []
    if amount != int(amount):
        whole, frac = str(amount).split(".")
        head, tail = number_words(int(whole))[:1], [_ONES[int(c)] or "zero" for c in frac]
        forms.append(" ".join(head + ["point"] + tail))
        forms.append(" ".join(head + ["."] + tail))      # ACI-Bench transcribes "two point five" as "two . five"
        return forms
    n = int(amount)
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")]
    if n < 1000:
        rest = number_words(n % 100)[0] if n % 100 else ""
        return [_ONES[n // 100] + " hundred" + (" " + rest if rest else "")]
    if n < 10000 and n % 100 == 0:
        return [_ONES[n // 1000] + " thousand" + (" " + number_words(n % 1000)[0] if n % 1000 else ""),
                number_words(n // 100)[0] + " hundred"]
    return [str(n)]


def stated_without_unit(canons: set, dialogue: str) -> bool:
    """Does the dialogue say this amount with no unit word next to it ('taking 300 or 100 ?')."""
    for c in canons:
        amount = float(c.split()[0])
        digits = ("%g" % amount)
        if re.search(r"(?<![\d.])" + re.escape(digits) + r"s?(?![\d.])", dialogue):
            return True
        if any(re.search(r"\b" + re.escape(w) + r"\b", dialogue) for w in number_words(amount) if w):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="record missing replies through the subscription CLI")
    parser.add_argument("--sample", type=int, default=0, help="run number (0 = every recorded run)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--show", action="store_true", help="print every entry and every extra in full")
    parser.add_argument("--condition", choices=sorted(PROMPTS), default="as-printed",
                        help="as-printed: Prompt 10-1 as in the book; narrowed: plus the one-line rule")
    args = parser.parse_args()

    dialogues = load_dialogues()
    if args.limit:
        dialogues = dialogues[: args.limit]
    truth_all = dialogue_doses()
    run_root = FIXTURES if args.condition == "as-printed" else FIXTURES / args.condition
    samples = [args.sample] if args.sample else sorted(
        int(p.name[1:]) for p in run_root.glob("s*") if p.is_dir())
    if not samples:
        print("no recorded runs; use --live --sample 1")
        return 1

    grand_seconds, grand_cost, models = 0.0, 0.0, set()
    for sample in samples:
        records = {}
        with cf.ThreadPoolExecutor(max_workers=args.workers if args.live else 1) as pool:
            futures = {pool.submit(get_record, d, sample, args.live, args.condition): d for d in dialogues}
            for fut in cf.as_completed(futures):
                d = futures[fut]
                records[(d["split"], d["encounter_id"])] = fut.result()
        for r in records.values():
            grand_seconds += r.get("seconds") or 0
            grand_cost += r.get("notional_cost_usd") or 0
            models |= set(r.get("models_used") or [])
        s = score(records, truth_all)
        n_entries = sum(len(v) for v in s["entries"].values())
        print(f"\n=== Run {sample} · {args.condition} · {s['dialogues']} conversations · Prompt 10-1, item type "
              f"\"{ITEM_TYPE}\" · {MODEL} via the subscription CLI")
        print(f"replies that were not a JSON object: {s['unparsable']}")
        print(f"ground-truth doses: {s['gt']} across {s['n_with_doses']} conversations "
              f"({s['n_without_doses']} state none)")
        print(f"  returned in `extracted`:            {s['returned']} of {s['gt']}")
        print(f"  silent omissions:                   {len(s['silent'])}   {s['silent']}")
        print(f"  routed to `not_extracted` instead:  {len(s['routed'])}   {s['routed']}")
        print("extras in `extracted` (strings whose dose is not a ground-truth dose):")
        for label, items in sorted(s["extras"].items(), key=lambda kv: -len(kv[1])):
            print(f"  {len(items):3}  {label}")
        print(f"`not_extracted` filled: {s['field_filled_with_doses']} of {s['n_with_doses']} conversations with a "
              f"dose, {s['field_filled_without_doses']} of {s['n_without_doses']} without; {n_entries} entries")
        for label, items in sorted(s["entries"].items(), key=lambda kv: -len(kv[1])):
            print(f"  {len(items):3}  {label}")
        if args.show:
            print("\n--- every `not_extracted` entry ---")
            for label, items in sorted(s["entries"].items()):
                for enc, text, reason in items:
                    print(f"  [{label}] {enc}: «{text}» — {reason}")
            print("\n--- every extra in `extracted` ---")
            for label, items in sorted(s["extras"].items()):
                for enc, text in items:
                    print(f"  [{label}] {enc}: «{text}»")
            for key, kind, text in s["cases"]:
                print(f"  [{kind}] {key[1]}: {text}")
    print(f"\nrecorded seconds {grand_seconds:.0f} · notional cost ${grand_cost:.4f} (claude.ai plan, not billed) "
          f"· models {sorted(models)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
