"""Assemble the Evidence Pack for a real fix, from the recorded runs.

The companion pack's Evidence Pack is a five-item checklist for closing a
ticket. This tries to actually produce all five for one real failure and one
real fix, and reports which items came out automatically, which needed work,
and which could not be produced at all.

    python evidence_pack.py

The failure used is the one Chapter 9 measured: asked for a paediatric dose on
a label that has no paediatric section, the model returned adult dosing text
lifted from the indications section. The fix is the source-section constraint.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ch09-sparse-field-fabrication"))

from shared.llm import LLM  # noqa: E402
from shared.scoring import rule, table  # noqa: E402

CASE_DRUG = "Prednisone"
CASE_FIELD = "pediatric_dosage"


def main() -> int:
    import broken as before
    import common as c9
    import fixed as after

    case = next(c for c in c9.build_cases() if c["drug"] == CASE_DRUG)
    llm = LLM(ROOT / "ch09-sparse-field-fabrication", live=False)

    produced, notes = {}, {}

    # ---- 1. The exact input passage that proves what should have happened ----
    label = next(
        l for l in json.loads((ROOT / "data" / "labels.json").read_text())["labels"]
        if l["drug"] == CASE_DRUG
    )
    section = dict(zip([f for f, _ in c9.FIELDS], [s for _, s in c9.FIELDS]))[CASE_FIELD]
    passage = label["sections"].get(section)

    rule("1 · The input passage that proves what should have been produced")
    if passage is None:
        print(f"  The '{section}' section does not exist in this label.")
        print("  That absence IS the ground truth: the correct output is nothing.")
        produced["1 · Ground-truth input passage"] = "yes — as a proven absence"
        notes["1 · Ground-truth input passage"] = (
            "Easy here because the corpus records which sections exist. In a "
            "production pipeline, proving a section was absent is usually harder "
            "than proving one was present — nobody logs what was not there."
        )
    else:
        print(f"  {passage[:300]}")
        produced["1 · Ground-truth input passage"] = "yes"

    # ---- 2. Before / after on the original sample ----
    rule("2 · Before and after, same input")
    old = llm.json(
        system=before.SYSTEM.format(context=case["context"]),
        user=f"Extract these fields: {c9.FIELD_LIST}",
        schema=before.schema(),
        max_tokens=2000,
    )[CASE_FIELD]
    new_raw = llm.json(
        system=after.SYSTEM.format(context=case["context"]),
        user=f"Extract the following fields: {c9.FIELD_LIST}",
        schema=after.schema(),
        max_tokens=2000,
    )[CASE_FIELD]
    new_value, reason = after.enforce(CASE_FIELD, new_raw, case)

    table(
        ["", "value stored", "quote supplied"],
        [
            ["BEFORE", str(old["value"])[:58], str(old["source_quote"])[:44]],
            ["AFTER", str(new_value)[:58] or "(nothing)", str(new_raw["source_quote"])[:44]],
        ],
    )
    print(f"  the check that changed it: {reason}")
    produced["2 · Before/after on the original"] = "yes — automatic"
    notes["2 · Before/after on the original"] = (
        "Free, because every run is recorded. Without recorded runs this item "
        "requires re-running the old code, which usually no longer exists."
    )

    # ---- 3. Confidence behaviour unchanged ----
    rule("3 · Confidence scoring behaviour")
    print("  Chapter 9's schema carries no confidence field, so there is nothing")
    print("  to compare. Chapter 2's does — and measured there, the model reported")
    print("  confidence on 83% of deliberately corrupted documents.")
    produced["3 · Confidence unchanged"] = "NO — cannot be produced"
    notes["3 · Confidence unchanged"] = (
        "Two problems. Most schemas have no confidence field at all, so the "
        "comparison is impossible. And where one exists it was measured to be "
        "unrelated to input quality — so an unchanged confidence score is not "
        "evidence of anything. This is the weakest item on the checklist."
    )

    # ---- 4. Regression on adjacent samples ----
    rule("4 · Regression check on adjacent samples")
    kept = lost = 0
    for other in c9.build_cases():
        if other["drug"] == CASE_DRUG:
            continue
        result = llm.json(
            system=after.SYSTEM.format(context=other["context"]),
            user=f"Extract the following fields: {c9.FIELD_LIST}",
            schema=after.schema(),
            max_tokens=2000,
        )
        for field, sect in c9.FIELDS:
            if sect not in c9.CONTEXT_SECTIONS:
                continue  # only fields that SHOULD be filled
            value, _ = after.enforce(field, result[field], other)
            kept += int(value is not None)
            lost += int(value is None)
    print(f"  11 adjacent labels, fields that should be filled: {kept} kept, {lost} lost")
    produced["4 · Regression on adjacent samples"] = "yes — automatic"
    notes["4 · Regression on adjacent samples"] = (
        "Free here because every chapter already measures recall on the cases "
        "that were working. That is not standard practice and it should be: "
        "without it, a fix that works by refusing to answer looks like a success."
    )

    # ---- 5. Traceable record ----
    rule("5 · A traceable record")
    fixtures = sorted((ROOT / "ch09-sparse-field-fabrication" / "fixtures").glob("*.json"))
    print(f"  {len(fixtures)} recorded runs on disk, each named by a hash of its exact request.")
    print("  Any number in the report can be traced to the request that produced it.")
    print("  Missing: a ticket number and a code-change reference — this repo has")
    print("  neither an issue tracker nor, yet, version control.")
    produced["5 · Traceable record"] = "partly"
    notes["5 · Traceable record"] = (
        "The evidence is traceable; the decision is not. Content-addressed runs "
        "prove what happened but not who asked for the change or why."
    )

    rule("Which of the five could actually be produced")
    table(
        ["Checklist item", "Produced?", "What it took"],
        [[k, v, notes[k][:96]] for k, v in produced.items()],
    )
    print()
    print("  3 of 5 automatic · 1 partial · 1 not producible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
