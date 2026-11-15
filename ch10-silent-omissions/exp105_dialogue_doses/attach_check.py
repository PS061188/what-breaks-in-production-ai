"""Experiment 10.5, step 3: attachment check (stricter than the spec's
"amount+unit anywhere").

The spec-level matcher counts a dose PRESENT if its amount+unit appears
anywhere in the note. That would hide a dose that reached the note attached
to the wrong drug. Here every (drug, dose) fact from the dialogue must have
at least one occurrence of the amount+unit lying NEAR a name of its drug
(drug within 80 chars before the dose or 45 chars after). Failures are
printed in full for hand reading.

The drug for each dose was read by hand from the dialogue context printouts
of count_doses.py; synonyms cover brand/generic switches a scribe makes.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from count_doses import dialogue_doses, extract  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from shared.cli_defaults import SUFFIX  # noqa: E402
FIXTURES = REPO / "ch09-sparse-field-fabrication" / ("fixtures_conversation" + SUFFIX)

SYN = {
    "protonix": "protonix|pantoprazole",
    "carafate": "carafate|sucralfate",
    "clindamycin": "clindamycin",
    "oxycodone": "oxycodone|roxicodone",
    "ibuprofen": "ibuprofen|motrin|advil",
    "nicotine": "nicotine",
    "lisinopril": "lisinopril",
    "metformin": "metformin|glucophage",
    "guaifenesin": "guaifenesin|mucinex",
    "meloxicam": "meloxicam|mobic",
    "melatonin": "melatonin",
    "methotrexate": "methotrexate",
    "naprosyn": "naprosyn|naproxen",
    "omeprazole": "omeprazole|prilosec",
    "allopurinol": "allopurinol",
    "crestor": "crestor|rosuvastatin",
    "lortab": "lortab|hydrocodone|norco|vicodin",
    "lasix": "lasix|furosemide",
    "toprol": "toprol|metoprolol",
    "prozac": "prozac|fluoxetine",
    "aspirin": "aspirin|asa\\b",
    "tramadol": "tramadol|ultram",
    "doxycycline": "doxycycline",
    "vitamin d": "vitamin d|cholecalciferol|ergocalciferol",
    "coumadin": "coumadin|warfarin",
    "atenolol": "atenolol|tenormin",
    "finasteride": "finasteride|proscar|propecia",
    "cialis": "cialis|tadalafil",
    "testosterone": "testosterone|cypionate",
    "pepcid": "pepcid|famotidine",
    "torsemide": "torsemide|demadex",
    "amlodipine": "amlodipine|norvasc",
}

# (encounter_id, canonical dose) -> list of drugs that carry this dose in the dialogue
FACTS = {
    ("D2N062", "40 mg"): ["protonix"],
    ("D2N062", "1 g"): ["carafate"],
    ("D2N108", "400 mg"): ["clindamycin"],
    ("D2N049", "5 mg"): ["oxycodone"],
    ("D2N186", "800 mg"): ["ibuprofen"],
    ("D2N043", "21 mg"): ["nicotine"],
    ("D2N050", "5 mg"): ["oxycodone"],
    ("D2N199", "20 mg"): ["lisinopril"],
    ("D2N199", "1000 mg"): ["metformin"],
    ("D2N199", "600 mg"): ["guaifenesin"],
    ("D2N199", "15 mg"): ["meloxicam"],
    ("D2N111", "20 mg"): ["lisinopril"],
    ("D2N111", "500 mg"): ["metformin"],
    ("D2N111", "15 mg"): ["meloxicam"],
    ("D2N160", "800 mg"): ["ibuprofen"],
    ("D2N160", "20 mg"): ["lisinopril"],
    ("D2N160", "500 mg"): ["metformin"],
    ("D2N036", "600 mg"): ["ibuprofen"],
    ("D2N118", "500 mg"): ["metformin"],
    ("D2N118", "10 mg"): ["melatonin"],
    ("D2N122", "7.5 mg"): ["methotrexate"],
    ("D2N109", "500 mg"): ["naprosyn"],
    ("D2N123", "500 mg"): ["metformin"],
    ("D2N123", "20 mg"): ["omeprazole"],
    ("D2N129", "10 mg"): ["lisinopril"],
    ("D2N013", "500 mg"): ["metformin"],
    ("D2N088", "1000 mg"): ["metformin"],
    ("D2N088", "20 mg"): ["lisinopril"],
    ("D2N006", "40 mg"): ["omeprazole"],
    ("D2N006", "100 mg"): ["allopurinol"],
    ("D2N094", "15 mg"): ["meloxicam"],
    ("D2N171", "20 mg"): ["crestor"],
    ("D2N018", "5 mg"): ["lortab"],
    ("D2N096", "600 mg"): ["ibuprofen"],
    ("D2N089", "2.5 mg"): ["methotrexate"],
    ("D2N089", "40 mg"): ["protonix"],
    ("D2N093", "40 mg"): ["lasix"],
    ("D2N093", "20 mg"): ["omeprazole"],
    ("D2N072", "600 mg"): ["ibuprofen"],
    ("D2N008", "40 mg"): ["lasix"],
    ("D2N008", "50 mg"): ["toprol"],
    ("D2N008", "10 mg"): ["lisinopril"],
    ("D2N017", "15 mg"): ["meloxicam"],
    ("D2N007", "20 mg"): ["prozac"],
    ("D2N007", "40 mg"): ["prozac"],
    ("D2N007", "81 mg"): ["aspirin"],
    ("D2N005", "50 mg"): ["tramadol"],
    ("D2N002", "50 mg"): ["tramadol"],
    ("D2N137", "10 mg"): ["lisinopril"],
    ("D2N134", "100 mg"): ["doxycycline"],
    ("D2N134", "10 mg"): ["lisinopril"],
    ("D2N177", "1000 mg"): ["metformin"],
    ("D2N177", "20 mg"): ["lisinopril"],
    ("D2N027", "5000 units"): ["vitamin d"],      # retracted in the dialogue ("excuse me")
    ("D2N027", "50000 units"): ["vitamin d"],
    ("D2N103", "4 mg"): ["coumadin", "lasix"],    # two drugs share the amount
    ("D2N103", "50 mg"): ["atenolol"],
    ("D2N023", "5 mg"): ["finasteride", "cialis"],  # tablet strengths; two drugs share it
    ("D2N023", "2.5 mg"): ["cialis"],
    ("D2N023", "175 mg"): ["testosterone"],       # proposed by patient, resisted by doctor
    ("D2N185", "40 mg"): ["pepcid"],
    ("D2N025", "20 mg"): ["torsemide"],
    ("D2N025", "10 mg"): ["lisinopril"],
    ("D2N139", "10 mg"): ["amlodipine"],
}

BEFORE, AFTER = 80, 45


def main():
    dlg = dialogue_doses()
    # coverage check: every extracted canonical must be in FACTS
    missing = []
    for (split, enc), rec in dlg.items():
        for canonical in rec["doses"]:
            if (enc, canonical) not in FACTS:
                missing.append((enc, canonical, rec["doses"][canonical][0][:160]))
    if missing:
        print("!! canonicals NOT covered by the hand map — fix FACTS first:")
        for enc, c, ctx in missing:
            print(f"   {enc} «{c}»  …{ctx}…")
        return

    n_checks = 0
    fails = []
    per_cell = defaultdict(lambda: [0, 0])   # (cond, s) -> [checks, fails]
    for (split, enc), rec in dlg.items():
        facts_here = [(c, d) for (e, c), drugs in FACTS.items() if e == enc for d in drugs]
        if not facts_here:
            continue
        for cond in ("template", "permission"):
            for s in (1, 2, 3):
                note = json.loads((FIXTURES / cond / f"{split}__{enc}__s{s}.json").read_text())["note"]
                low = note.lower()
                mentions = extract(note, permissive=True)
                for canonical, drug in facts_here:
                    n_checks += 1
                    per_cell[(cond, s)][0] += 1
                    drug_rx = re.compile(SYN[drug])
                    spans = [(m["start"], m["end"]) for m in mentions if m["canonical"] == canonical]
                    ok = False
                    for a, b in spans:
                        lo, hi = max(0, a - BEFORE), min(len(low), b + AFTER)
                        if drug_rx.search(low[lo:a]) or drug_rx.search(low[b:hi]):
                            ok = True
                            break
                    if not ok:
                        per_cell[(cond, s)][1] += 1
                        fails.append((enc, split, canonical, drug, cond, s, note, spans))

    print(f"=== attachment check: {n_checks} (drug, dose, note) checks, {len(fails)} failures ===")
    print(f"{'condition':<12} {'run':<4} {'checks':<8} {'failures'}")
    for cond in ("template", "permission"):
        for s in (1, 2, 3):
            c, f = per_cell[(cond, s)]
            print(f"{cond:<12} s{s:<3} {c:<8} {f}")

    for enc, split, canonical, drug, cond, s, note, spans in fails:
        low = note.lower()
        print("\n" + "#" * 100)
        print(f"FAIL {enc} [{cond} s{s}] — «{canonical}» not near «{drug}» (syn: {SYN[drug]})")
        print("--- dialogue mention(s):")
        for ctx in dialogue_doses()[(split, enc)]["doses"][canonical][:3]:
            print(f"    …{ctx}…")
        print(f"--- note occurrences of «{canonical}» and their surroundings:")
        if not spans:
            print("    (none — the amount+unit is absent from this note entirely)")
        for a, b in spans:
            lo, hi = max(0, a - 120), min(len(note), b + 120)
            print(f"    …{note[lo:hi]}…".replace("\n", " ⏎ "))
        print(f"--- lines in note naming the drug:")
        for ln in note.splitlines():
            if re.search(SYN[drug], ln.lower()):
                print(f"    | {ln.strip()}")


if __name__ == "__main__":
    main()
