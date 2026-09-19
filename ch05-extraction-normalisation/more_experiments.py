"""Chapter 5, three follow-up measurements (15 Sep 2026).

A. Dose ranges, five runs each of the three prompts (plain / normalise-inside /
   capture), with the corrected range counter. Also reports the other two
   measures per run.
B. Retries: for every dose or frequency value the normaliser cannot parse, feed
   the error back to the model up to three times and count how many get fixed.
C. Format drift across models: the capture prompt on Haiku 4.5, Sonnet 5 and
   GPT-4.1-mini; per-field exact match of the normalised value against Haiku.

    python more_experiments.py --live    # ~$1
    python more_experiments.py           # replay
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from broken import PLAIN, SYSTEM as STANDARDISE  # noqa: E402
from fixed import SYSTEM as CAPTURE  # noqa: E402
from common import FIELDS_ASKED, SCHEMA, build_cases, score_case, summarise  # noqa: E402
from normalise import normalise_dose, normalise_frequency  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

HERE = Path(__file__).parent
PROMPTS = {"plain": PLAIN, "normalise inside the prompt": STANDARDISE, "capture prompt": CAPTURE}


def extract(llm, prompt, case, sample):
    return llm.json(system=prompt.format(source=case["source"]), user=f"Extract these fields: {FIELDS_ASKED}",
                    schema=SCHEMA, max_tokens=1500, sample=sample)


def parse(field):
    name = field["field"].lower()
    if "dose" in name: return normalise_dose(field["value"])[0], "dose"
    if "frequency" in name: return normalise_frequency(field["value"])[0], "frequency"
    return {"raw_text": field["value"]}, "other"


def main():
    parser = base_args(__doc__)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    cases = build_cases(limit=args.limit)
    haiku = LLM(HERE, model="claude-haiku-4-5", live=args.live)

    # ---------- A ----------
    rule("A. Five runs each, corrected range counter")
    rows = []; capture_results = {}
    for name, prompt in PROMPTS.items():
        for k in range(1, args.runs + 1):
            results = [extract(haiku, prompt, c, k) for c in cases]
            if name == "capture prompt": capture_results[k] = results
            t = summarise([score_case(c, r) for c, r in zip(cases, results)])
            rows.append([name, k, f"{t['docs_range_preserved']}/{t['docs_with_range']}",
                         pct(t["qualifiers_retained"], t["qualifiers_present"]),
                         f"{pct(t['values_verbatim'], t['values'])} ({t['values']} values)"])
    table(["prompt", "run", "ranges kept", "qualifiers kept", "values findable (values returned)"], rows)

    # ---------- B ----------
    rule("B. Retries on values the normaliser cannot parse (capture prompt, 5 runs)")
    total_fields = errors = 0; fixed_at = defaultdict(int); unfixed = []
    RETRY_SCHEMA = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False}
    for k, results in capture_results.items():
        for case, result in zip(cases, results):
            for field in result["fields"]:
                parsed, kind = parse(field)
                if kind == "other": continue
                total_fields += 1
                if parsed is not None: continue
                errors += 1
                value = field["value"]; ok = False
                for attempt in (1, 2, 3):
                    what = "a dose (a number followed by a unit such as mg)" if kind == "dose" else "a frequency (how often per day, or an interval in hours)"
                    fb = haiku.json(system="You correct one extracted field so that it can be parsed. Return the value exactly as the document states it; do not invent a number or a unit.",
                                    user=f"Field: {field['field']}\nYou returned: {value!r}\nThis could not be parsed as {what}.\nThe source passage is: {field['source_quote']!r}\nReturn the value again, as written in the source.",
                                    schema=RETRY_SCHEMA, max_tokens=100, sample=k * 10 + attempt)
                    value = fb["value"]
                    if (normalise_dose(value)[0] if kind == "dose" else normalise_frequency(value)[0]) is not None:
                        fixed_at[attempt] += 1; ok = True; break
                if not ok: unfixed.append((case["drug"][:18], field["field"], field["value"][:40]))
    headline("Dose and frequency values checked", str(total_fields))
    headline("Could not be parsed at first (format errors)", f"{errors} ({pct(errors, total_fields)})")
    for a in (1, 2, 3): headline(f"Fixed on retry {a}", str(fixed_at[a]))
    headline("Still unparseable after 3 retries", str(len(unfixed)))
    if unfixed: table(["drug", "field", "value"], unfixed[:12])

    # ---------- C ----------
    rule("C. Same capture prompt on three models, one run: per-field agreement with Haiku 4.5")
    models = {"claude-sonnet-5": LLM(HERE, model="claude-sonnet-5", live=args.live),
              "gpt-4.1-mini": LLM(HERE, model="gpt-4.1-mini", live=args.live)}
    ref = {}
    for case, result in zip(cases, capture_results[1]):
        for f in result["fields"]: ref[(case["drug"], f["field"].lower())] = (f["value"], parse(f)[0])
    out = []
    for mname, llm in models.items():
        agree_raw = defaultdict(int); agree_norm = defaultdict(int); n = defaultdict(int); missing = 0
        for case in cases:
            result = extract(llm, CAPTURE, case, 1)
            got = {f["field"].lower(): (f["value"], parse(f)[0]) for f in result["fields"]}
            for (drug, fname), (rv, rn) in ref.items():
                if drug != case["drug"]: continue
                n[fname] += 1
                if fname not in got: missing += 1; continue
                v, pn = got[fname]
                agree_raw[fname] += int(v.strip().lower() == rv.strip().lower())
                agree_norm[fname] += int(pn == rn)
        for fname in sorted(n):
            out.append([mname, fname, pct(agree_raw[fname], n[fname]), pct(agree_norm[fname], n[fname])])
        out.append([mname, "fields Haiku returned that this model did not", str(missing), ""])
    table(["model", "field", "same raw value as Haiku", "same normalised value as Haiku"], out)
    haiku.report()
    for llm in models.values(): llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
