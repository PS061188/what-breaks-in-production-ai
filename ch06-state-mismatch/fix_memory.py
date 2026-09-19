"""Scenario 3: the world moved inside the model.

Nothing in the context is stale; the model's own training is. Three arms per
drug, five runs each:

  MEMORY     no document at all. The model answers from what it remembers.
             Scored against the real current label: does the remembered dose
             appear in the current label, and does the answer state a dose the
             current label does not?
  DOCUMENT   the real current label in context, with an instruction to prefer
             the document over memory. Same scoring.
  CHANGED    a copy of the label with every dose doubled by code, standing in
             for a world that moved after training. If the model follows the
             document it answers with doubled values; if memory wins it answers
             with the real ones.

Scoring is set arithmetic on dose values, as elsewhere in the chapter.

    python fix_memory.py
    python fix_memory.py --live
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import dose_values, load_versions  # noqa: E402
from fix_integrity import double_doses, header, tally, runs  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

RUNS = 5

MEMORY_SYSTEM = """You are a clinical information assistant. Answer from your own
knowledge. Give the recommended starting dose as a number with a unit."""

DOCUMENT_SYSTEM = """You are a clinical information assistant. Answer using the
document below. Where the document and your own knowledge disagree, the
document is current and your knowledge may be out of date: follow the document.

<document>
{context}
</document>"""

SCHEMA = {
    "type": "object",
    "properties": {"starting_dose": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
    "required": ["starting_dose"], "additionalProperties": False,
}


def main() -> int:
    args = base_args(__doc__).parse_args()
    versions = load_versions()
    current = {v["drug"]: v for v in versions if v["status"] == "ACTIVE"}
    drugs = sorted(current)
    if args.limit:
        drugs = drugs[: args.limit]
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)

    keys = ("in_label", "not_in_label", "no_dose", "doc_won", "memory_won", "both")
    stats = {a: {k: 0 for k in keys} for a in ("memory", "document", "changed")}
    rows = []
    n = len(drugs) * RUNS
    for drug in drugs:
        v = current[drug]
        real_vals = dose_values(v["text"])
        changed_text = double_doses(v["text"])
        real_only = real_vals - dose_values(changed_text)
        doubled_only = dose_values(changed_text) - real_vals
        question = f"What is the recommended starting dose of {drug}?"
        arms = (("memory", MEMORY_SYSTEM, None),
                ("document", DOCUMENT_SYSTEM.format(context=f"{header(v['set_id'], v)}\n{v['text']}"), None),
                ("changed", DOCUMENT_SYSTEM.format(context=f"{header(v['set_id'], v)}\n{changed_text}"), None))
        for name, system, _ in arms:
            for k in range(1, RUNS + 1):
                ans = llm.json(system=system, user=question, schema=SCHEMA, max_tokens=300, sample=k)
                vals = dose_values(str(ans["starting_dose"] or ""))
                tally(stats, name, "no_dose", k, ans["starting_dose"] is None)
                if name in ("memory", "document"):
                    tally(stats, name, "in_label", k, bool(vals & real_vals))
                    tally(stats, name, "not_in_label", k, bool(vals - real_vals))
                    rows.append([drug[:18], name, k, "in label" if vals & real_vals else "-",
                                 "STATES A DOSE NOT IN LABEL" if vals - real_vals else "-",
                                 str(ans["starting_dose"])[:40]])
                else:
                    d, m = bool(vals & doubled_only), bool(vals & real_only)
                    tally(stats, name, "doc_won", k, d and not m)
                    tally(stats, name, "memory_won", k, m and not d)
                    tally(stats, name, "both", k, d and m)
                    rows.append([drug[:18], name, k,
                                 "document won" if d and not m else ("MEMORY WON" if m and not d else ("both" if d and m else "neither")),
                                 "-", str(ans["starting_dose"])[:40]])
    rule("Scenario 3: memory alone, the current label, and a label the world moved away from")
    table(["drug", "arm", "run", "outcome", "flag", "answer (first 40)"], rows)
    for name in ("memory", "document"):
        headline(f"[{name}] answer contains a dose the current label states", pct(stats[name]["in_label"], n), runs(stats, name, "in_label"))
        headline(f"[{name}] answer states a dose the current label does not", pct(stats[name]["not_in_label"], n), runs(stats, name, "not_in_label"))
        headline(f"[{name}] no dose", pct(stats[name]["no_dose"], n), runs(stats, name, "no_dose"))
    headline("[changed] the document won over memory", pct(stats["changed"]["doc_won"], n), runs(stats, "changed", "doc_won"))
    headline("[changed] memory won over the document", pct(stats["changed"]["memory_won"], n), runs(stats, "changed", "memory_won"))
    headline("[changed] both", pct(stats["changed"]["both"], n), runs(stats, "changed", "both"))
    headline("[changed] no dose", pct(stats["changed"]["no_dose"], n), runs(stats, "changed", "no_dose"))
    print()
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
