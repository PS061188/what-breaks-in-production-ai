"""Can a prompt cope when there is no status field at all?

Prompt 6-1 reads a `status` flag. Most corpora have none. What a document does
carry is a date. So the only rule a prompt can apply without a flag is: group
the documents that describe the same thing, and use the newest.

This script hands the model the same unfiltered top-3 as fix_prompt.py, but
with headers that carry a doc_id and a date only — no status. Two arms:

  neutral        answer from the documents, no rule
  newest wins    group by subject, use only the newest date, say which
                 document you relied on and its date, and do not claim the
                 answer is current beyond that date

The prediction being tested: "newest wins" can only choose among what it was
given. Where the current label is in the top-3 it should pick it. Where it is
not, the newest document it has is still superseded, and no prompt can know.
So results are split by whether the current label was retrieved at all.

Scoring is the chapter's usual set arithmetic on dose values: an answer that
contains a dose only a superseded label states used the superseded label.

    python fix_nostatus.py
    python fix_nostatus.py --live
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import dose_values, load_versions, stable_top_k  # noqa: E402
from fix_prompt import TOP_K, build_index  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

RUNS = 5

NEUTRAL = """You are a policy assistant. Answer using the retrieved documents below.

<retrieved_context>
{context}
</retrieved_context>"""

NEWEST_WINS = """You are a policy assistant. You ONLY answer based on documents
provided in <retrieved_context>. Each document has a metadata header with its
doc_id and the date it was last updated. There is no other information about
whether a document is current.

The documents may include several versions of the same policy. Before answering:
1. Group the documents that describe the same subject.
2. Within a group, rely only on the document with the latest last_updated date.
   Do not use an older one, even if it says more.
3. Say which document you relied on and its date, as: "Based on [doc_id],
   dated [date]."
4. You cannot know whether a newer version exists outside these documents. Do
   not describe the answer as current. Describe it as current as of the date
   of the document you relied on.

Today's date is 2026-08-22.

<retrieved_context>
{context}
</retrieved_context>"""

ARMS = [("neutral", NEUTRAL), ("newest wins", NEWEST_WINS)]

SCHEMA = {
    "type": "object",
    "properties": {
        "relied_on_doc_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "as_of_date": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "starting_dose": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["relied_on_doc_id", "as_of_date", "starting_dose"],
    "additionalProperties": False,
}


def main() -> int:
    args = base_args(__doc__).parse_args()
    versions = load_versions()
    by_id = {v["set_id"]: v for v in versions}
    drugs = sorted({v["drug"] for v in versions})
    if args.limit:
        drugs = drugs[: args.limit]
    collection = build_index(versions)
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)

    keys = ("used_stale", "no_dose", "relied_newest", "dated")
    stats = {name: {"in": {k: 0 for k in keys}, "out": {k: 0 for k in keys},
                    "runs": {k: [0] * RUNS for k in keys}} for name, _ in ARMS}
    n_in = n_out = 0
    rows = []
    for drug in drugs:
        result = stable_top_k(collection, f"recommended starting dose of {drug}", {"drug": drug}, TOP_K)
        retrieved = sorted(zip(result["ids"][0], result["documents"][0]))
        context = "\n\n---\n\n".join(
            f"[doc_id: {doc_id} | last_updated: {by_id[doc_id]['effective_time']}]\n{doc}"
            for doc_id, doc in retrieved
        )
        ids = [d for d, _ in retrieved]
        active_ids = {i for i in ids if by_id[i]["status"] == "ACTIVE"}
        stale_ids = [i for i in ids if i not in active_ids]
        newest_id = max(ids, key=lambda i: by_id[i]["effective_time"])
        current_values = set().union(*[dose_values(by_id[i]["text"]) for i in active_ids]) if active_ids else set()
        stale_only = (set().union(*[dose_values(by_id[i]["text"]) for i in stale_ids]) - current_values) if stale_ids else set()
        bucket = "in" if active_ids else "out"
        if bucket == "in":
            n_in += 1
        else:
            n_out += 1
        for name, system in ARMS:
            for k in range(1, RUNS + 1):
                ans = llm.json(system=system.format(context=context),
                               user=f"What is the recommended starting dose of {drug}?",
                               schema=SCHEMA, max_tokens=500, sample=k)
                vals = dose_values(str(ans["starting_dose"] or ""))
                used_stale = bool(vals & stale_only)
                relied_newest = ans["relied_on_doc_id"] == newest_id
                dated = bool(ans["as_of_date"]) and ans["relied_on_doc_id"] in by_id and \
                    by_id[ans["relied_on_doc_id"]]["effective_time"][:4] in str(ans["as_of_date"])
                hits = {"used_stale": used_stale, "no_dose": ans["starting_dose"] is None,
                        "relied_newest": relied_newest, "dated": dated}
                for key, hit in hits.items():
                    stats[name][bucket][key] += int(hit)
                    stats[name]["runs"][key][k - 1] += int(hit)
                rows.append([drug[:18], "current in top-3" if active_ids else "CURRENT NOT RETRIEVED",
                             name, k, "STALE VALUE" if used_stale else ("no dose" if hits["no_dose"] else "-"),
                             "newest" if relied_newest else "-", "dated" if dated else "-"])

    rule(f"Unfiltered top-{TOP_K}, headers carry a date and no status, two prompts, {RUNS} runs")
    table(["drug", "retrieval", "prompt", "run", "answer content", "relied on", "as-of date"], rows)
    headline("Drugs whose current label was in the top-3 at all", f"{n_in} of {len(drugs)}",
             "The ceiling for any prompt: it can only choose among what it was handed.")
    for name in stats:
        s_in, s_out, r = stats[name]["in"], stats[name]["out"], stats[name]["runs"]
        headline(f"[{name}] answered with a dose only a superseded label states, current label WAS retrieved",
                 pct(s_in["used_stale"], n_in * RUNS))
        headline(f"[{name}] answered with a dose only a superseded label states, current label NOT retrieved",
                 pct(s_out["used_stale"], n_out * RUNS))
        headline(f"[{name}] used a superseded label, all drugs",
                 pct(s_in["used_stale"] + s_out["used_stale"], len(drugs) * RUNS),
                 "runs " + ", ".join(str(x) for x in r["used_stale"]))
        headline(f"[{name}] returned no dose", pct(s_in["no_dose"] + s_out["no_dose"], len(drugs) * RUNS),
                 "runs " + ", ".join(str(x) for x in r["no_dose"]))
        headline(f"[{name}] relied on the newest document it was given",
                 pct(s_in["relied_newest"] + s_out["relied_newest"], len(drugs) * RUNS),
                 "runs " + ", ".join(str(x) for x in r["relied_newest"]))
        headline(f"[{name}] stated an as-of date matching the document it relied on",
                 pct(s_in["dated"] + s_out["dated"], len(drugs) * RUNS),
                 "runs " + ", ".join(str(x) for x in r["dated"]))
    print()
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
