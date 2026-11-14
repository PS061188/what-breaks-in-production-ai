"""Chapter 10's first engineering fix as printed: a named-entity model's count (Experiment 10.4).

The chapter says: after extraction, run the source through "a fast named-entity
recognition (NER) model — spaCy en_core_web_trf or AWS Comprehend" for an
independent count, and flag the extraction for review when the model returned
fewer items than the NER model found. common.py stands a regular expression in
for that model. This probe runs the model the book names on the same six
documents and holds every recorded extraction against it: fixed.py's API run
(fixtures/) and the nine subscription runs of Experiment 10.3 (fixtures_count/),
sixty document-runs. No model calls; every answer replays.

Counting rule. A dose amount is a number with a dose unit (mg, mcg, g, unit: the
units common.DOSE counts) inside a QUANTITY entity, normalised the way
common.dose_figures normalises the model's list ("20 mg/kg/day" is 20 mg) and
counted once however often it appears. QUANTITY because it is the label for
measurements and where en_core_web_trf puts the doses it finds. Distinct amounts
because the model's side is distinct figures; a raw entity count also counts
every repeat. None of common.py's hand-made exclusions is applied to the NER side;
skipping lab values is shown as a variant.

Whether a run really dropped something is decided by reading, not by either
count. READ holds every dose amount each section states, including the ones the
pattern cannot see, and each list is read as written, so "10 to 15 mg/kg/day"
holds 10.

Needs spaCy in its own environment (the rest of the repo is plain Python 3.9;
spaCy 3.8.7 is the newest release with Python 3.9 wheels):

    python3 -m venv .venv-ner
    .venv-ner/bin/pip install spacy==3.8.7 https://github.com/explosion/spacy-models/releases/download/en_core_web_trf-3.8.0/en_core_web_trf-3.8.0-py3-none-any.whl
    .venv-ner/bin/python probe_ner.py                          # en_core_web_trf
    .venv-ner/bin/python probe_ner.py --model en_core_web_sm   # after installing that wheel
"""

import argparse
import json
import platform
import re
import sys
import time
from collections import Counter
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from common import DOSE, FOLLOWED_BY_COMPARISON, IDENTIFIER_BEFORE, LAB_UNIT_AFTER, build_cases, dose_figures  # noqa: E402
from fixed import SCHEMA, SYSTEM  # noqa: E402
from probe_count import RUNS, parse  # noqa: E402
from shared.llm import LLM  # noqa: E402
from shared.scoring import rule, table  # noqa: E402

RUN_LABELS = ["api"] + [f"{tag}{r}" for tag in ("ap", "di", "pr") for r in RUNS]
CONDITIONS = {"ap": "as-printed", "di": "distinct", "pr": "protocol"}

# Every dose amount each section states, read by hand (4 Oct 2026): the pattern's
# figures plus the ones it cannot see. Levothyroxine adds the range starts 2, 4 and
# 12.5 mcg ("12.5 to 25 mcg"), Warfarin 0.5 and 3 mg ("0.5 to 2 mg" in the genotype
# table), Gabapentin the eleven renal-table cells whose unit sits in the heading.
READ = {
    "lisinopril": "6.25 10 12.5 20 25 50 80",
    "levothyroxine": "1 1.6 2 3 4 5 6 8 10 12.5 15 25 200 300",
    "amoxicillin": "6.4 28.5 42.9 57 90 200 400 500 600 875",
    "sertraline": "1 25 50 70 100 150 200",
    "warfarin": "0.5 2 3 4 5 7 10 100",
    "gabapentin": "10 15 25 35 40 50 100 125 150 200 250 300 350 400 500 600 700 800 900 1200 1400 1800 2400 3600",
}
READ = {k: {float(n) for n in v.split()} for k, v in READ.items()}
# Doses of another drug named in the section: methylene blue "1 mg/kg" (Sertraline)
# and low-dose aspirin "100 mg/day" (Warfarin). A list without them is short only
# by the letter of "every dose amount mentioned".
OTHER_DRUG = {"sertraline": {1.0}, "warfarin": {100.0}}

UNIT_IN_ITEM = re.compile(r"\d\s*(?:mg|mcg|g|units?)\b", re.I)
BARE_CELL = re.compile(r"^[\d.\s]+(?:to[\d.\s]+)?(?:TID|BID|QD)?$", re.I)  # "300 TID", "900 to 3600", "125"
RANGE_START = re.compile(r"\b\d+(?:\.\d+)?(?=\s*(?:to|-|–)\s*\d+(?:\.\d+)?\s*(?:mg|mcg|g|units?)\b)", re.I)
TABLE_CELL = re.compile(r"\b\d+(?=\s+(?:TID|BID|QD)\b)")


def recorded_lists(cases: list) -> dict:
    """Every recorded extraction: {(drug key, run label): list of dose strings}."""
    llm = LLM(HERE, live=False)  # replay only: a missing fixture raises, it never calls
    lists = {}
    for case in cases:
        key = case["drug"].split()[0].lower()
        # The same request as fixed.py's extract(), so it replays fixed.py's recorded answer.
        answer = llm.json(system=SYSTEM.format(text=case["text"]),
                          user="List every dose amount mentioned in the text.",
                          schema=SCHEMA, max_tokens=2000)
        lists[key, "api"] = answer["doses"]
        for tag, condition in CONDITIONS.items():
            for run in RUNS:
                path = HERE / "fixtures_count" / condition / f"{key}__s{run}.json"
                lists[key, f"{tag}{run}"] = parse(json.loads(path.read_text(encoding="utf-8"))["reply"])["doses"]
    return lists


def as_written(items: list) -> set:
    """Every number a list states as a dose, range starts and bare table cells
    included; parenthetical notes (renal bands, ages, genotypes) left out."""
    numbers = set()
    for item in map(str, items):
        if UNIT_IN_ITEM.search(item) or BARE_CELL.match(item.strip()):
            numbers |= {float(n) for n in re.findall(r"\d+(?:\.\d+)?", re.sub(r"\([^)]*\)", "", item))}
    return numbers


def verdict(key: str, items: list) -> str:
    missing = READ[key] - as_written(items)
    if missing - OTHER_DRUG.get(key, set()):
        return "short"
    return "other drug" if missing else "complete"


def ner_amounts(doc, skip_lab: bool = False) -> set:
    """The counting rule: distinct dose amounts inside QUANTITY entities."""
    found = set()
    for ent in doc.ents:
        if ent.label_ != "QUANTITY":
            continue
        for m in DOSE.finditer(ent.text):
            if skip_lab and LAB_UNIT_AFTER.match(ent.text[m.end(): m.end() + 6]):
                continue
            found |= dose_figures(m.group(0))
    return found


def dose_spans(text: str) -> list:
    """(start, end, kind) for each dose the pattern counts, and for unit-less ones:
    range starts and renal-table cells marked TID/BID/QD."""
    spans = []
    for m in DOSE.finditer(text):
        if (IDENTIFIER_BEFORE.search(text[max(0, m.start() - 12): m.start()])
                or FOLLOWED_BY_COMPARISON.match(text[m.end(): m.end() + 4])
                or LAB_UNIT_AFTER.match(text[m.end(): m.end() + 6])):
            continue
        spans.append((m.start(), m.end(), "with unit"))
    for pattern in (RANGE_START, TABLE_CELL):
        spans += [(m.start(), m.end(), "no unit") for m in pattern.finditer(text)]
    return spans


def entity_at(doc, start: int, end: int):
    return next((e for e in doc.ents if e.start_char < end and e.end_char > start), None)


def installed(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not installed"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="en_core_web_trf", help="spaCy pipeline (default: the one the book names)")
    args = ap.parse_args()

    from shared.deps import load_spacy

    started = time.time()
    nlp = load_spacy(args.model, "Experiment 10.4", "install lines are at the top of probe_ner.py")
    load_seconds = time.time() - started
    cases = build_cases()
    lists = recorded_lists(cases)

    docs, seconds = {}, {}
    for case in cases:
        started = time.time()
        docs[case["drug"]] = nlp(case["text"])
        seconds[case["drug"]] = time.time() - started

    print(f"Python {platform.python_version()} ({platform.machine()}, CPU) · spaCy {installed('spacy')} · "
          f"{args.model} {nlp.meta['version']} · spacy-curated-transformers {installed('spacy-curated-transformers')} · "
          f"torch {installed('torch')}")
    print(f"load {load_seconds:.1f}s · per document " + ", ".join(f"{s:.1f}s" for s in seconds.values()))

    rule("Where the dose amounts land")
    rows, examples, totals = [], [], {"with unit": Counter(), "no unit": Counter()}
    for case in cases:
        doc, text = docs[case["drug"]], case["text"]
        tally = {"with unit": Counter(), "no unit": Counter()}
        previous = -100
        for start, end, kind in dose_spans(text):
            ent = entity_at(doc, start, end)
            label = ent.label_ if ent else "no entity"
            tally[kind][label if label in ("QUANTITY", "CARDINAL", "DATE", "no entity") else "other"] += 1
            if label == "QUANTITY" or kind != "with unit":
                continue
            # One example per stretch of text: a table row of misses is one example, not twenty.
            if start - previous > 60 and sum(e[0] == case["drug"] for e in examples) < 3:
                examples.append((case["drug"], label, ent.text if ent else "-", text[max(0, start - 45): end + 25]))
            previous = start
        for kind, counts in tally.items():
            totals[kind].update(counts)
            rows.append([case["drug"][:13], kind, sum(counts.values()), counts["QUANTITY"], counts["CARDINAL"],
                         counts["DATE"], counts["other"], counts["no entity"]])
    for kind, counts in totals.items():
        rows.append(["all six", kind, sum(counts.values()), counts["QUANTITY"], counts["CARDINAL"],
                     counts["DATE"], counts["other"], counts["no entity"]])
    table(["drug", "dose printed", "mentions", "QUANTITY", "CARDINAL", "DATE", "other", "no entity"], rows)
    print("\nExamples of doses with a unit that did not land in QUANTITY:")
    for drug, label, ent_text, context in examples:
        context = re.sub("​+", lambda m: f"[{len(m.group())} zero-width spaces]", " ".join(context.split()))
        print(f"  {drug[:13]:13} {label:9} entity {ent_text!r:14} in ...{context}...")

    rule("Counts of distinct dose amounts per document")
    ner, ner_lab, rows = {}, {}, []
    for case in cases:
        key, doc = case["drug"].split()[0].lower(), docs[case["drug"]]
        ner[key], ner_lab[key] = ner_amounts(doc), ner_amounts(doc, skip_lab=True)
        raw = sum(e.label_ == "QUANTITY" for e in doc.ents)
        rows.append([case["drug"][:13], len(case["expected"]), len(READ[key]), raw, len(ner[key]), len(ner_lab[key]),
                     ", ".join(sorted(ner[key] - case["expected"])) or "-",
                     ", ".join(sorted(case["expected"] - ner[key], key=lambda f: float(f.split()[0]))) or "-"])
    table(["drug", "pattern", "read", "QUANTITY ents", "NER rule", "NER, no lab", "NER only", "pattern only"], rows)

    rule("Each recorded extraction: distinct figures in the list, against the NER count")
    rows, outcomes = [], []
    for case in cases:
        key = case["drug"].split()[0].lower()
        cells = []
        for label in RUN_LABELS:
            items = lists[key, label]
            got = dose_figures(" ".join(map(str, items)), expand_ranges=True)
            truth = verdict(key, items)
            flags = {
                "NER rule": len(got) < len(ner[key]),
                "NER rule, lab values skipped": len(got) < len(ner_lab[key]),
                "NER rule, items listed (len of the list)": len(items) < len(ner[key]),
                "pattern count, same rule": len(got) < len(case["expected"]),
                "pattern set comparison (as common.score matches)": bool(case["expected"] - got),
            }
            outcomes.append((truth, flags))
            mark = {"short": "*", "other drug": "~", "complete": ""}[truth]
            cells.append(f"{len(got)}{'!' if flags['NER rule'] else ''}{mark}")
        rows.append([case["drug"][:13], len(case["expected"]), len(ner[key])] + cells)
    table(["drug", "pattern", "NER"] + RUN_LABELS, rows)
    print("  ap = as-printed, di = distinct, pr = protocol (fixtures_count/); api = fixed.py's run (fixtures/)\n"
          "  ! flagged by the NER rule   * really short (read)   ~ short only by another drug's dose")

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
