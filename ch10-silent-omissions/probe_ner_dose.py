"""Experiment 10.8 — fix 1 with taggers that DO have a dose label.

Experiment 10.4 ran the tagger the book names, spaCy en_core_web_trf, and found it
has no dose type: doses land in QUANTITY next to lab values, so a unit filter had
to be written in code, a serum-creatinine line still got through, and the renal
tables (unit in the column heading) were invisible. The open question Prachi put
(12 Oct 2026): is there a tagger with a dose label, and does having the label
remove the domain work?

Two off-the-shelf models carry one:

  med7     spaCy en_core_med7_lg (Kormilitzin et al., 2020; MIT): DRUG, STRENGTH,
           DOSAGE, FORM, FREQUENCY, ROUTE, DURATION. Trained on MIMIC-III notes.
           STRENGTH is the amount in the product ("500 mg"), DOSAGE the amount
           taken ("two tablets"). Pins spaCy 3.4.
  deberta  blaze999/Medical-NER (DeBERTa-v3-base, MIT), 41 types incl. DOSAGE,
           MEDICATION, FREQUENCY, DURATION, MASS, VOLUME, LAB_VALUE. Trained on
           PubMed case reports. Runs through transformers, 512-token windows.

Not run: Amazon Comprehend Medical, whose DetectEntitiesV2 returns MEDICATION
attributes typed DOSAGE and STRENGTH. It needs an AWS account; none is on this
machine. Plain Amazon Comprehend, the product the chapter named, has QUANTITY
and no medication type, like en_core_web_trf.

Same documents, same ruler, same 60 recorded extractions as probe_ner.py, same
counting rule: distinct dose amounts (number + mg/mcg/g/unit) inside an entity
whose label is a dose label. Per model, the three tables Experiment 10.4 printed:
where the pattern's dose mentions land by label; the per-document counts against
the pattern and the hand-read set; and what the model's count flags across the
60 document-runs, with the real drops read rather than scored.

    .venv-med/bin/python probe_ner_dose.py --model med7
    .venv-med/bin/python probe_ner_dose.py --model deberta
"""

import argparse
import platform
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from common import DOSE, LAB_UNIT_AFTER, build_cases, dose_figures  # noqa: E402
from probe_ner import OTHER_DRUG, READ, RUN_LABELS, dose_spans, installed, recorded_lists, verdict  # noqa: E402
from shared.scoring import rule, table  # noqa: E402

MODELS = {
    "med7": {"name": "en_core_med7_lg", "dose_labels": ("STRENGTH", "DOSAGE"), "variant": ("STRENGTH",)},
    "deberta": {"name": "blaze999/Medical-NER", "dose_labels": ("DOSAGE",), "variant": ("DOSAGE", "MASS")},
}


def spacy_entities(model: str):
    from shared.deps import load_spacy
    nlp = load_spacy(model, "Experiment 10.8 (med7)",
                     "en_core_med7_lg 3.4.2.1 on spaCy 3.4, from huggingface.co/kormilitzin/en_core_med7_lg")
    meta = f"{model} {nlp.meta['version']} · spaCy {installed('spacy')}"

    def run(text: str) -> list:
        return [(e.start_char, e.end_char, e.label_, e.text) for e in nlp(text).ents]
    return run, meta


def hf_entities(model: str, window: int = 1500):
    """Token classification in character windows cut at sentence ends; offsets re-based."""
    from shared.deps import require
    require("torch", "torch", "Experiment 10.8 (deberta)")
    require("transformers", "transformers", "Experiment 10.8 (deberta)")
    from transformers import pipeline
    pipe = pipeline("token-classification", model=model, aggregation_strategy="simple")
    meta = f"{model} · transformers {installed('transformers')} · torch {installed('torch')}"

    def run(text: str) -> list:
        ents, pos = [], 0
        while pos < len(text):
            end = min(len(text), pos + window)
            if end < len(text):
                cut = text.rfind(". ", pos + window // 2, end)
                end = cut + 2 if cut > 0 else end
            chunk = text[pos:end]
            for e in pipe(chunk):
                ents.append((pos + e["start"], pos + e["end"], e["entity_group"], chunk[e["start"]:e["end"]]))
            pos = end
        return ents
    return run, meta


def entity_at(ents: list, start: int, end: int):
    return next((e for e in ents if e[0] < end and e[1] > start), None)


def model_amounts(ents: list, labels: tuple, skip_lab: bool = False) -> set:
    """The counting rule: distinct dose amounts inside entities carrying a dose label."""
    found = set()
    for _, _, label, text in ents:
        if label not in labels:
            continue
        for m in DOSE.finditer(text):
            if skip_lab and LAB_UNIT_AFTER.match(text[m.end(): m.end() + 6]):
                continue
            found |= dose_figures(m.group(0))
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", choices=sorted(MODELS), help="default: med7, then deberta")
    args = ap.parse_args(argv)
    if args.model is None:
        for name in MODELS:
            main(["--model", name])
        return 0
    spec = MODELS[args.model]
    started = time.time()
    run, meta = (spacy_entities if args.model == "med7" else hf_entities)(spec["name"])
    load_seconds = time.time() - started

    cases = build_cases()
    lists = recorded_lists(cases)
    ents, seconds = {}, {}
    for case in cases:
        started = time.time()
        ents[case["drug"]] = run(case["text"])
        seconds[case["drug"]] = time.time() - started
    labels, variant = spec["dose_labels"], spec["variant"]
    print(f"Python {platform.python_version()} ({platform.machine()}, CPU) · {meta}")
    print(f"load {load_seconds:.1f}s · per document " + ", ".join(f"{s:.1f}s" for s in seconds.values()))
    print(f"dose labels counted: {' + '.join(labels)} · variant: {' + '.join(variant)}")

    rule("Where the pattern's dose mentions land, by entity label")
    rows, examples, totals = [], [], {"with unit": Counter(), "no unit": Counter()}
    for case in cases:
        text, es = case["text"], ents[case["drug"]]
        tally = {"with unit": Counter(), "no unit": Counter()}
        previous = -100
        for start, end, kind in dose_spans(text):
            e = entity_at(es, start, end)
            label = e[2] if e else "no entity"
            tally[kind][label] += 1
            if label in labels or kind != "with unit":
                continue
            if start - previous > 60 and sum(x[0] == case["drug"] for x in examples) < 3:
                examples.append((case["drug"], label, e[3] if e else "-", text[max(0, start - 45): end + 25]))
            previous = start
        for kind, counts in tally.items():
            totals[kind].update(counts)
            rows.append([case["drug"][:13], kind, sum(counts.values())] +
                        [counts[l] for l in labels] + [sum(v for k, v in counts.items() if k not in labels and k != "no entity"),
                                                       counts["no entity"]])
    for kind, counts in totals.items():
        rows.append(["all six", kind, sum(counts.values())] +
                    [counts[l] for l in labels] + [sum(v for k, v in counts.items() if k not in labels and k != "no entity"),
                                                   counts["no entity"]])
    table(["drug", "dose printed", "mentions"] + list(labels) + ["other label", "no entity"], rows)
    other = Counter()
    for case in cases:
        for start, end, kind in dose_spans(case["text"]):
            e = entity_at(ents[case["drug"]], start, end)
            if e and e[2] not in labels:
                other[e[2]] += 1
    if other:
        print("  other labels that covered a dose mention: " + ", ".join(f"{k} {v}" for k, v in other.most_common()))
    print("\nExamples of doses with a unit that did not land in a dose label:")
    for drug, label, ent_text, context in examples:
        context = re.sub("​+", lambda m: f"[{len(m.group())} zero-width spaces]", " ".join(context.split()))
        print(f"  {drug[:13]:13} {label:12} entity {ent_text!r:16} in ...{context}...")

    rule("Counts of distinct dose amounts per document")
    ner, ner_var, rows = {}, {}, []
    for case in cases:
        key, es = case["drug"].split()[0].lower(), ents[case["drug"]]
        ner[key], ner_var[key] = model_amounts(es, labels), model_amounts(es, variant)
        raw = sum(e[2] in labels for e in es)
        rows.append([case["drug"][:13], len(case["expected"]), len(READ[key]), raw, len(ner[key]), len(ner_var[key]),
                     ", ".join(sorted(ner[key] - case["expected"])) or "-",
                     ", ".join(sorted(case["expected"] - ner[key], key=lambda f: float(f.split()[0]))) or "-"])
    table(["drug", "pattern", "read", "dose-label ents", "model rule", "variant", "model only", "pattern only"], rows)

    rule("Each recorded extraction: distinct figures in the list, against the model count")
    rows, outcomes = [], []
    for case in cases:
        key = case["drug"].split()[0].lower()
        cells = []
        for label in RUN_LABELS:
            items = lists[key, label]
            got = dose_figures(" ".join(map(str, items)), expand_ranges=True)
            truth = verdict(key, items)
            flags = {
                "model rule": len(got) < len(ner[key]),
                "model rule, variant labels": len(got) < len(ner_var[key]),
                "pattern count, same rule": len(got) < len(case["expected"]),
            }
            outcomes.append((truth, flags))
            mark = {"short": "*", "other drug": "~", "complete": ""}[truth]
            cells.append(f"{len(got)}{'!' if flags['model rule'] else ''}{mark}")
        rows.append([case["drug"][:13], len(case["expected"]), len(ner[key])] + cells)
    table(["drug", "pattern", "model"] + RUN_LABELS, rows)
    print("  ap = as-printed, di = distinct, pr = protocol (fixtures_count/); api = fixed.py's run (fixtures/)\n"
          "  ! flagged by the model rule   * really short (read)   ~ short only by another drug's dose")

    rule("What each check flags, of 60 document-runs")
    n = Counter(truth for truth, _ in outcomes)
    rows = []
    for check in outcomes[0][1]:
        hit = Counter(truth for truth, flags in outcomes if flags[check])
        rows.append([check, f"{hit['short']}/{n['short']}", f"{hit['other drug']}/{n['other drug']}",
                     f"{hit['complete']}/{n['complete']}"])
    table(["check", "really short, flagged", "other drug only, flagged", "complete, flagged (false)"], rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
