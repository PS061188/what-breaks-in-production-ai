"""Experiment 10.5, step 2: which conversation doses reach each of the 360 notes?

For every note (60 encounters x {template, permission} x s1..s3):
  - note's dose set = permissive extraction (digits incl. "20mg"/"20-mg",
    word forms, combined strengths "5/500 mg" counting both components)
  - candidate omission = dialogue dose whose canonical amount+unit is
    nowhere in the note's dose set

Prints a machine summary + a full case block per candidate for hand reading:
dialogue quotes, the note's MEDICATIONS and ASSESSMENT AND PLAN sections,
a loose scan for the bare amount anywhere in the note, and any line that
looks like it flags a missing dose.
"""
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from count_doses import dialogue_doses, extract  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "probe_conversation", REPO / "ch09-sparse-field-fabrication" / "probe_conversation.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
sections = probe.sections

FIXTURES = REPO / "ch09-sparse-field-fabrication" / "fixtures_conversation"
CONDITIONS = ("template", "permission")
SAMPLES = (1, 2, 3)

SIGNAL_RX = re.compile(
    r"[^\n]*(?:dos(?:e|age|ing)[^\n]{0,40}?(?:unknown|unclear|unspecified|uncertain|not\s+"
    r"(?:specified|stated|given|mentioned|documented|discussed|provided|recalled|confirmed))"
    r"|unknown\s+dos|unspecified\s+dos|unclear\s+dos|not\s+specified|does\s+not\s+recall"
    r"|unable\s+to\s+(?:recall|confirm)|\bunsure\b|\?\s*dose|dose\s*\?)[^\n]*", re.I)


def word_amount_variants(amount):
    """Rough word spellings of an amount, to loosely scan the note."""
    s = f"{amount:g}"
    return [s, s.replace(".", " point ")]


def main():
    dlg = dialogue_doses()
    rows = defaultdict(lambda: dict(doses=0, candidates=[]))
    all_notes = {}

    for cond in CONDITIONS:
        for s in SAMPLES:
            for (split, enc), rec in dlg.items():
                path = FIXTURES / cond / f"{split}__{enc}__s{s}.json"
                note = json.loads(path.read_text())["note"]
                all_notes[(cond, s, split, enc)] = note
                if not rec["doses"]:
                    continue
                note_mentions = extract(note, permissive=True)
                note_set = {m["canonical"] for m in note_mentions if m["canonical"]}
                key = (cond, s)
                rows[key]["doses"] += len(rec["doses"])
                for canonical, contexts in rec["doses"].items():
                    if canonical not in note_set:
                        rows[key]["candidates"].append((split, enc, canonical))

    print("=== candidate omissions per cell (before reading) ===")
    print(f"{'condition':<12} {'run':<4} {'doses':<7} {'candidates'}")
    for cond in CONDITIONS:
        for s in SAMPLES:
            r = rows[(cond, s)]
            print(f"{cond:<12} s{s:<3} {r['doses']:<7} {len(r['candidates'])}")

    # group candidates by encounter+dose for reading
    grouped = defaultdict(list)
    for (cond, s), r in rows.items():
        for split, enc, canonical in r["candidates"]:
            grouped[(split, enc, canonical)].append((cond, s))

    print(f"\n=== {len(grouped)} distinct (encounter, dose) omission groups; "
          f"{sum(len(v) for v in grouped.values())} note-level candidates ===\n")

    for (split, enc, canonical), cells in sorted(grouped.items()):
        amount = canonical.split()[0]
        print("#" * 100)
        print(f"CASE {split} {enc} — dose «{canonical}» missing from "
              f"{len(cells)}/6 notes: {sorted(cells)}")
        print("--- dialogue mentions:")
        for ctx in dlg[(split, enc)]["doses"][canonical]:
            print(f"    …{ctx}…")
        for cond, s in sorted(cells):
            note = all_notes[(cond, s, split, enc)]
            secs = sections(note)
            meds = (secs.get("MEDICATIONS") or "").strip()
            plan = (secs.get("ASSESSMENT AND PLAN") or "").strip()
            loose = [ln.strip() for ln in note.splitlines()
                     if any(v in ln.lower() for v in word_amount_variants(float(amount)))]
            signals = [m.group(0).strip() for m in SIGNAL_RX.finditer(note)]
            print(f"\n  ---- [{cond} s{s}] MEDICATIONS:")
            print("    " + (meds.replace(chr(10), "\n    ") or "(empty)"))
            print(f"  ---- [{cond} s{s}] ASSESSMENT AND PLAN:")
            print("    " + (plan.replace(chr(10), "\n    ") or "(empty)"))
            if loose:
                print(f"  ---- bare amount «{amount}» elsewhere in note:")
                for ln in loose[:6]:
                    print(f"    | {ln}")
            if signals:
                print("  ---- possible gap signals in this note:")
                for sg in set(signals):
                    print(f"    ! {sg}")
        print()


if __name__ == "__main__":
    main()
