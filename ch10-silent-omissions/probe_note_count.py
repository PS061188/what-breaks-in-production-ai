"""Experiment 10.9, part 2 — the tagger count (fix 1) on prose output.

Fix 1 compares an outside count of the source against the extractor's output.
On an extraction task the output is a list and the comparison is direct. On the
conversation-to-note task the output is prose, so the only way to run fix 1 is
to pick a fact type that is countable on both sides and compare counts.

The fact type here is drug names. Med7 (en_core_med7_lg) tags DRUG spans; it
runs over each of the 60 ACI-Bench dialogues and each of its 6 recorded notes
(Experiment 9.4: template / permission prompts, runs s1-s3). A note is flagged
when it carries fewer distinct drug names than the dialogue. Both sides are
normalised the same way (lowercase, longest-match dedup inside multiword spans).

What this can and cannot show, stated up front: Experiment 10.5 settled that
every stated dose reaches every note, but drugs named without a dose were never
checked, so a flag here is a lead to read, not a verdict. Every flagged case
prints the two name sets so the difference can be read.

    .venv-med/bin/python probe_note_count.py
"""

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
CH9 = HERE.parent / "ch09-sparse-field-fabrication" / "fixtures_conversation"
DATA = HERE.parent / "data" / "aci_bench_dialogues.json"

CONDITIONS = ("template", "permission")
RUNS = (1, 2, 3)


def drug_names(nlp, text: str) -> set:
    names = set()
    for ent in nlp(text).ents:
        if ent.label_ != "DRUG":
            continue
        name = re.sub(r"[^a-z0-9 ]", "", ent.text.lower()).strip()
        if name:
            names.add(name)
    # dedup: drop a name fully contained in another ("lisinopril 20" vs "lisinopril")
    return {n for n in names if not any(n != m and n in m for m in names)}


def main() -> int:
    from shared.deps import load_spacy
    nlp = load_spacy("en_core_med7_lg", "Experiment 10.9",
                     "en_core_med7_lg 3.4.2.1 on spaCy 3.4, from huggingface.co/kormilitzin/en_core_med7_lg")
    dialogues = {(d["split"], d["encounter_id"]): d["dialogue"]
                 for d in json.loads(DATA.read_text())["dialogues"]}
    started = time.time()
    dlg_drugs = {k: drug_names(nlp, v) for k, v in dialogues.items()}
    flags, rows, read = Counter(), [], []
    n_notes = 0
    for cond in CONDITIONS:
        for run in RUNS:
            for f in sorted((CH9 / cond).glob(f"*__s{run}.json")):
                rec = json.loads(f.read_text())
                key = (rec["split"], rec["encounter_id"])
                note_set = drug_names(nlp, rec["note"])
                n_notes += 1
                src = dlg_drugs[key]
                if len(note_set) < len(src):
                    flags[cond, run] += 1
                    read.append((key[1], cond, run, sorted(src - note_set), sorted(note_set - src)))
    per_dlg = [len(v) for v in dlg_drugs.values()]
    print(f"Med7 DRUG spans · {len(dialogues)} dialogues · {n_notes} notes · "
          f"{time.time()-started:.0f}s total, local")
    print(f"distinct drug names per dialogue: min {min(per_dlg)}, median {sorted(per_dlg)[30]}, max {max(per_dlg)}; "
          f"{sum(1 for p in per_dlg if p==0)} dialogues with none tagged")
    print("\nnotes flagged (note has fewer distinct drug names than its dialogue):")
    for cond in CONDITIONS:
        print(f"  {cond}: " + ", ".join(f"run {r}: {flags[cond, r]}/60" for r in RUNS))
    print(f"\nEvery flagged case — dialogue-only names vs note-only names ({len(read)} cases):")
    for enc, cond, run, only_dlg, only_note in read:
        print(f"  {enc} {cond} s{run}: dialogue-only {only_dlg} | note-only {only_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
