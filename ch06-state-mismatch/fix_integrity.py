"""Chapter 6's CONTEXT INTEGRITY CHECK, tested on the failures it names.

The staleness test (fix_prompt.py) could not show the last block of the prompt
doing anything, because that test set never contained the failures the block
describes: every document was about the right drug, the only disagreements
were old-vs-new labels, and there was no conversation history.

This script builds each of those three failures on purpose and runs the
status-only prompt with and without the block. Only the block differs.

  A. WRONG ENTITY     the current label for the drug plus the current label for a
                      different drug, both marked ACTIVE. Does the answer use a
                      dose that only the wrong drug's label states?
  B. CONFLICT         two ACTIVE documents for the same drug that disagree: the
                      real current label and a copy in which every dose value is
                      doubled by code. Does the answer say they conflict, or
                      silently pick one?
  C. LATER UPDATE     the current label plus a short conversation transcript in
                      which a stated dose is corrected in a later turn. Does the
                      answer use the corrected value?

Scoring is set arithmetic on dose values, as in the rest of the chapter. No
model judges another model.

    python fix_integrity.py
    python fix_integrity.py --live
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import DOSE, dose_values, load_versions  # noqa: E402
from fix_prompt import STATUS_ONLY  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

RUNS = 5


def tally(stats: dict, name: str, key: str, run: int, hit: bool) -> None:
    """Count a hit both overall and per run, so the book can print every run."""
    stats[name][key] += int(hit)
    stats[name].setdefault("_runs", {}).setdefault(key, [0] * RUNS)
    stats[name]["_runs"][key][run - 1] += int(hit)


def runs(stats: dict, name: str, key: str) -> str:
    return "runs " + ", ".join(str(x) for x in stats[name].get("_runs", {}).get(key, [0] * RUNS))

INTEGRITY_BLOCK = """CONTEXT INTEGRITY CHECK:
Before answering, verify:
- Do retrieved documents address the same entity as the question?
- Is there any conflict between documents? If yes, cite both and flag the conflict.
- Does conversation history contain updates that override earlier statements?
  If yes, use the most recent.

"""

WITH_BLOCK = STATUS_ONLY.replace("<retrieved_context>", INTEGRITY_BLOCK + "<retrieved_context>", 1)
assert WITH_BLOCK != STATUS_ONLY

ARMS = [("status only", STATUS_ONLY), ("status + integrity block", WITH_BLOCK)]

SCHEMA = {
    "type": "object",
    "properties": {
        "usable_doc_ids": {"type": "array", "items": {"type": "string"}},
        "starting_dose": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "conflict": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["usable_doc_ids", "starting_dose", "conflict"],
    "additionalProperties": False,
}


def header(doc_id: str, v: dict, status: str = "ACTIVE") -> str:
    return (
        f"[doc_id: {doc_id} | last_updated: {v['effective_time']} | "
        f"status: {status} | version: {v['effective_time']}]"
    )


def double_doses(text: str) -> str:
    """Every dose value doubled, so the copy states doses the original never does."""

    def bump(m):
        n = float(m.group(1)) * 2
        n = int(n) if n == int(n) else n
        return f"{n} {m.group(2)}"

    return DOSE.sub(bump, text)


def main() -> int:
    args = base_args(__doc__).parse_args()
    versions = load_versions()
    current = {v["drug"]: v for v in versions if v["status"] == "ACTIVE"}
    drugs = sorted(current)
    if args.limit:
        drugs = drugs[: args.limit]
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)

    # ---------------- A. wrong entity ----------------
    rule("A. Wrong entity: the drug's current label plus another drug's current label, both ACTIVE")
    a_stats = {name: {"used_wrong": 0, "declared_wrong": 0, "no_dose": 0} for name, _ in ARMS}
    a_rows = []
    for i, drug in enumerate(drugs):
        other = drugs[(i + 1) % len(drugs)]
        v, w = current[drug], current[other]
        docs = sorted([(v["set_id"], v), (w["set_id"], w)])
        context = "\n\n---\n\n".join(f"{header(d, x)}\n{x['text']}" for d, x in docs)
        wrong_only = dose_values(w["text"]) - dose_values(v["text"])
        for name, system in ARMS:
            for k in range(1, RUNS + 1):
                ans = llm.json(
                    system=system.format(context=context),
                    user=f"What is the recommended starting dose of {drug}?",
                    schema=SCHEMA, max_tokens=500, sample=k,
                )
                used = bool(dose_values(str(ans["starting_dose"] or "")) & wrong_only)
                declared = w["set_id"] in set(ans["usable_doc_ids"])
                tally(a_stats, name, "used_wrong", k, used)
                tally(a_stats, name, "declared_wrong", k, declared)
                tally(a_stats, name, "no_dose", k, ans["starting_dose"] is None)
                a_rows.append([drug[:18], other[:18], name, k,
                               "WRONG DRUG'S DOSE" if used else "-",
                               "declared usable" if declared else "-"])
    table(["drug asked", "decoy label", "prompt", "run", "answer content", "decoy doc"], a_rows)
    n = len(drugs) * RUNS
    for name in a_stats:
        headline(f"[{name}] answered with a dose only the wrong drug's label states",
                 pct(a_stats[name]["used_wrong"], n), runs(a_stats, name, "used_wrong"))
        headline(f"[{name}] declared the wrong drug's label usable",
                 pct(a_stats[name]["declared_wrong"], n), runs(a_stats, name, "declared_wrong"))
        headline(f"[{name}] returned no dose", pct(a_stats[name]["no_dose"], n), runs(a_stats, name, "no_dose"))

    # ---------------- B. conflict ----------------
    rule("B. Conflict: two ACTIVE documents for the same drug, the second with every dose doubled by code")
    b_stats = {name: {"reported": 0, "named_both": 0, "dose_real": 0, "dose_doubled": 0,
                      "dose_both": 0, "no_dose": 0} for name, _ in ARMS}
    b_rows = []
    for drug in drugs:
        v = current[drug]
        copy_text = double_doses(v["text"])
        copy = dict(v, text=copy_text)
        copy_id = v["set_id"][:8] + "-b"
        docs = sorted([(v["set_id"], v), (copy_id, copy)])
        context = "\n\n---\n\n".join(f"{header(d, x)}\n{x['text']}" for d, x in docs)
        real_only = dose_values(v["text"]) - dose_values(copy_text)
        doubled_only = dose_values(copy_text) - dose_values(v["text"])
        for name, system in ARMS:
            for k in range(1, RUNS + 1):
                ans = llm.json(
                    system=system.format(context=context),
                    user=f"What is the recommended starting dose of {drug}?",
                    schema=SCHEMA, max_tokens=500, sample=k,
                )
                dose_vals = dose_values(str(ans["starting_dose"] or ""))
                conflict_text = str(ans["conflict"] or "")
                reported = bool(ans["conflict"])
                named_both = (bool(dose_values(conflict_text) & real_only)
                              and bool(dose_values(conflict_text) & doubled_only))
                has_real, has_doubled = bool(dose_vals & real_only), bool(dose_vals & doubled_only)
                no_dose = ans["starting_dose"] is None
                tally(b_stats, name, "reported", k, reported)
                tally(b_stats, name, "named_both", k, named_both)
                tally(b_stats, name, "dose_real", k, has_real and not has_doubled)
                tally(b_stats, name, "dose_doubled", k, has_doubled and not has_real)
                tally(b_stats, name, "dose_both", k, has_real and has_doubled)
                tally(b_stats, name, "no_dose", k, no_dose)
                b_rows.append([drug[:18], name, k,
                               "reported" if reported else "SILENT",
                               "both values" if named_both else "-",
                               "no dose" if no_dose else ("real" if has_real and not has_doubled else
                                ("DOUBLED" if has_doubled and not has_real else
                                 ("both" if has_real and has_doubled else "other")))])
    table(["drug", "prompt", "run", "conflict field", "names both", "dose given"], b_rows)
    for name in b_stats:
        headline(f"[{name}] reported a conflict", pct(b_stats[name]["reported"], n), runs(b_stats, name, "reported"))
        headline(f"[{name}] named a value from each document", pct(b_stats[name]["named_both"], n), runs(b_stats, name, "named_both"))
        headline(f"[{name}] gave the real label's dose", pct(b_stats[name]["dose_real"], n), runs(b_stats, name, "dose_real"))
        headline(f"[{name}] gave the doubled dose", pct(b_stats[name]["dose_doubled"], n), runs(b_stats, name, "dose_doubled"))
        headline(f"[{name}] gave both", pct(b_stats[name]["dose_both"], n), runs(b_stats, name, "dose_both"))
        headline(f"[{name}] gave no dose", pct(b_stats[name]["no_dose"], n), runs(b_stats, name, "no_dose"))

    # ---------------- C. later update in the conversation ----------------
    rule("C. Later update: the current label plus a transcript in which a stated dose is corrected")
    c_stats = {name: {"used_corrected": 0, "used_first": 0, "used_label": 0, "no_dose": 0}
               for name, _ in ARMS}
    c_rows = []
    for drug in drugs:
        v = current[drug]
        label_vals = sorted(dose_values(v["text"]))
        # two numbers that no label states, so the answer's source is unambiguous
        first, corrected = "7 mg", "9 mg"
        assert first not in label_vals and corrected not in label_vals
        context = f"{header(v['set_id'], v)}\n{v['text']}"
        transcript = (
            "Conversation so far:\n"
            f"[10:02] Pharmacist: For this patient we agreed to record a starting dose of {first} of {drug}.\n"
            "[10:03] Assistant: Noted.\n"
            f"[10:15] Pharmacist: Correction to my earlier message: the agreed starting dose is {corrected}, not {first}.\n\n"
            f"Question: According to the conversation, what starting dose should I record for {drug}?"
        )
        for name, system in ARMS:
            for k in range(1, RUNS + 1):
                ans = llm.json(
                    system=system.format(context=context),
                    user=transcript, schema=SCHEMA, max_tokens=500, sample=k,
                )
                vals = dose_values(str(ans["starting_dose"] or ""))
                used_corr = corrected in vals and first not in vals
                used_first = first in vals and corrected not in vals
                used_label = bool(vals & set(label_vals)) and not (vals & {first, corrected})
                tally(c_stats, name, "used_corrected", k, used_corr)
                tally(c_stats, name, "used_first", k, used_first)
                tally(c_stats, name, "used_label", k, used_label)
                tally(c_stats, name, "no_dose", k, ans["starting_dose"] is None)
                c_rows.append([drug[:18], name, k,
                               "corrected value" if used_corr else
                               ("FIRST VALUE" if used_first else
                                ("label's value" if used_label else
                                 ("no dose" if ans["starting_dose"] is None else "other")))])
    table(["drug", "prompt", "run", "answer used"], c_rows)
    for name in c_stats:
        headline(f"[{name}] used the corrected value", pct(c_stats[name]["used_corrected"], n), runs(c_stats, name, "used_corrected"))
        headline(f"[{name}] used the first, superseded value", pct(c_stats[name]["used_first"], n), runs(c_stats, name, "used_first"))
        headline(f"[{name}] ignored the conversation and answered from the label", pct(c_stats[name]["used_label"], n), runs(c_stats, name, "used_label"))
        headline(f"[{name}] returned no dose", pct(c_stats[name]["no_dose"], n), runs(c_stats, name, "no_dose"))

    print()
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
