"""Scenario 2, the model's half: can the model reconcile a draft with a record that changed?

Fix 7 (re-read the system of record at write time) and fix 5 (route a detected
change to a person) are code. A re-read that compares two records catches a
change by construction. What is not by construction is what happens next when a
team leaves the reconciliation to the model: "here is the draft, here is the
current record, finalise it."

For each drug, a draft answer is generated from the real current label. Then
the record "changes": a copy of the label with every dose value doubled by
code stands in for the record as it is at write time. Two probes:

  A. TOLD      the model is told the record changed after the draft and asked to
               revise the draft to match it. Does the revised answer carry the
               new dose and drop the old one?
  B. NOT TOLD  the model is asked to finalise the draft against the current
               record, with no mention of a change. Does it notice that the
               draft contradicts the record in front of it, or write the stale
               dose through?

Scoring is set arithmetic on dose values: a value only the changed record
states is "new", a value only the original states is "old".

    python fix_reconcile.py
    python fix_reconcile.py --live
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import dose_values, load_versions  # noqa: E402
from fix_integrity import double_doses, header, tally, runs  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

RUNS = 5

DRAFT_SYSTEM = """You are a clinical information assistant. Using only the document
below, draft a short answer to the question.

<record>
{context}
</record>"""

TOLD_SYSTEM = """You are finalising a draft answer before it is written into the
patient record. The record below is the CURRENT one. It was updated after the
draft was written, so the draft may be out of date. Revise the draft so that
every value matches the current record, and say what you changed.

<record>
{context}
</record>"""

NOT_TOLD_SYSTEM = """You are finalising a draft answer before it is written into
the patient record. The record below is the current one. Return the final
answer, and note anything you had to change.

<record>
{context}
</record>"""

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {"starting_dose": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
    "required": ["starting_dose"], "additionalProperties": False,
}
FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "starting_dose": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "changed": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["starting_dose", "changed"], "additionalProperties": False,
}


def main() -> int:
    args = base_args(__doc__).parse_args()
    versions = load_versions()
    current = {v["drug"]: v for v in versions if v["status"] == "ACTIVE"}
    drugs = sorted(current)
    if args.limit:
        drugs = drugs[: args.limit]
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)

    keys = ("new_only", "old_only", "both", "no_dose", "noted_change")
    stats = {p: {k: 0 for k in keys} for p in ("told", "not told")}
    rows = []
    n = len(drugs) * RUNS
    for drug in drugs:
        v = current[drug]
        changed_text = double_doses(v["text"])
        old_only = dose_values(v["text"]) - dose_values(changed_text)
        new_only = dose_values(changed_text) - dose_values(v["text"])
        original = f"{header(v['set_id'], v)}\n{v['text']}"
        changed = f"{header(v['set_id'], v)}\n{changed_text}"
        question = f"What is the recommended starting dose of {drug}?"
        for k in range(1, RUNS + 1):
            draft = llm.json(system=DRAFT_SYSTEM.format(context=original), user=question,
                             schema=DRAFT_SCHEMA, max_tokens=300, sample=k)
            draft_text = str(draft["starting_dose"] or "")
            if not (dose_values(draft_text) & old_only):
                rows.append([drug[:18], "draft", k, "draft carries no dose from the original; probes skipped", "-"])
                continue
            for probe, system in (("told", TOLD_SYSTEM), ("not told", NOT_TOLD_SYSTEM)):
                ans = llm.json(system=system.format(context=changed),
                               user=f"Question: {question}\nDraft answer: {draft_text}",
                               schema=FINAL_SCHEMA, max_tokens=400, sample=k)
                vals = dose_values(str(ans["starting_dose"] or ""))
                has_new, has_old = bool(vals & new_only), bool(vals & old_only)
                tally(stats, probe, "new_only", k, has_new and not has_old)
                tally(stats, probe, "old_only", k, has_old and not has_new)
                tally(stats, probe, "both", k, has_new and has_old)
                tally(stats, probe, "no_dose", k, ans["starting_dose"] is None)
                tally(stats, probe, "noted_change", k, bool(ans["changed"]))
                rows.append([drug[:18], probe, k,
                             "NEW dose" if has_new and not has_old else
                             ("OLD dose (stale)" if has_old and not has_new else
                              ("both" if has_new and has_old else "no dose")),
                             (str(ans["changed"])[:44] if ans["changed"] else "-")])
    rule("Draft built from the original record; finalised against a record whose doses had changed")
    table(["drug", "probe", "run", "final answer carries", "noted change (first 44)"], rows)
    for probe in stats:
        headline(f"[{probe}] final answer carries the new dose only", pct(stats[probe]["new_only"], n), runs(stats, probe, "new_only"))
        headline(f"[{probe}] final answer carries the old, stale dose only", pct(stats[probe]["old_only"], n), runs(stats, probe, "old_only"))
        headline(f"[{probe}] final answer carries both", pct(stats[probe]["both"], n), runs(stats, probe, "both"))
        headline(f"[{probe}] no dose", pct(stats[probe]["no_dose"], n), runs(stats, probe, "no_dose"))
        headline(f"[{probe}] noted a change", pct(stats[probe]["noted_change"], n), runs(stats, probe, "noted_change"))
    print()
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
