"""Chapter 6's prompt template: the staleness protocol, run against stale documents.

The chapter gives one prompt. It hands the model a metadata header per document
and asks it to check that header before using the content:

    - "last_updated": must be within the last 90 days for policy questions
    - "status": must be "ACTIVE" (not "SUPERSEDED", "DRAFT", or "ARCHIVED")

The book is careful to call this *"a second line of defence, not the primary
one"*, so the question here is not whether it replaces the retrieval filter. It
is narrower and answerable: given documents that are honestly labelled
SUPERSEDED, does the model stop using them?

Both arms retrieve the same unfiltered top-3, get the same metadata headers, and
return the same schema. Only the system prompt differs.

Scoring is set arithmetic on dose values. A superseded label states doses the
current label does not; if one of those values appears in the answer, the answer
used the superseded document, whatever the model said about it.

    python fix_prompt.py
    python fix_prompt.py --live
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import dose_values, load_versions, stable_top_k  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

INDEX_DIR = Path(__file__).parent / ".chroma" / "prompt"
TOP_K = 3

NEUTRAL = """You are a policy assistant. Answer using the retrieved documents below.

<retrieved_context>
{context}
</retrieved_context>"""

# From Chapter 6, "Prompt template". Reproduced as printed apart from the
# domain noun — the book's version says "policy assistant" over policy
# documents; this corpus is drug labels, and the check being tested is the
# metadata check, not the noun.
STALENESS_PROTOCOL = """You are a policy assistant. You ONLY answer based on
documents provided in <retrieved_context>. Each document has a metadata header —
check it before using it.

STALENESS PROTOCOL:
Before using any retrieved document, check its metadata:
- "last_updated": must be within the last 90 days for policy questions
- "status": must be "ACTIVE" (not "SUPERSEDED", "DRAFT", or "ARCHIVED")
- "version": prefer the highest version number if multiple docs address the topic
If a retrieved document is stale or inactive:
1. Do NOT use its content to answer
2. State explicitly: "The retrieved document [doc_id] is dated [date] and marked
   [status]. I cannot rely on it for current policy."
3. If no fresh document is available, say: "I don't have a current version of
   this policy in my context. Please verify with the source system."

CONTEXT INTEGRITY CHECK:
Before answering, verify:
- Do retrieved documents address the same entity as the question?
- Is there any conflict between documents? If yes, cite both and flag the conflict.
- Does conversation history contain updates that override earlier statements?
  If yes, use the most recent.

Today's date is 2026-08-22.

<retrieved_context>
{context}
</retrieved_context>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "usable_doc_ids": {"type": "array", "items": {"type": "string"}},
        "starting_dose": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["usable_doc_ids", "starting_dose"],
    "additionalProperties": False,
}


# --- Arm split, Aug 2026 -------------------------------------------------
# The book gives ONE prompt bundling six separate rules. Measured as one thing,
# no effect can be attributed to any rule -- and Task 6.1 already establishes
# that one of the six (the 90-day window) is broken. These arms isolate them.

STATUS_ONLY = """You are a policy assistant. You ONLY answer based on
documents provided in <retrieved_context>. Each document has a metadata header —
check it before using it.

STATUS CHECK:
Before using any retrieved document, check its metadata:
- "status": must be "ACTIVE" (not "SUPERSEDED", "DRAFT", or "ARCHIVED")
If a retrieved document is not ACTIVE:
1. Do NOT use its content to answer
2. State explicitly: "The retrieved document [doc_id] is marked [status].
   I cannot rely on it for current policy."
3. If no ACTIVE document is available, say: "I don't have a current version of
   this policy in my context. Please verify with the source system."

<retrieved_context>
{context}
</retrieved_context>"""

DATE_ONLY = """You are a policy assistant. You ONLY answer based on
documents provided in <retrieved_context>. Each document has a metadata header —
check it before using it.

FRESHNESS CHECK:
Before using any retrieved document, check its metadata:
- "last_updated": must be within the last 90 days for policy questions
If a retrieved document is older than that:
1. Do NOT use its content to answer
2. State explicitly: "The retrieved document [doc_id] is dated [date].
   I cannot rely on it for current policy."
3. If no fresh document is available, say: "I don't have a current version of
   this policy in my context. Please verify with the source system."

Today's date is 2026-08-22.

<retrieved_context>
{context}
</retrieved_context>"""

METADATA_ONLY = """You are a policy assistant. You ONLY answer based on
documents provided in <retrieved_context>. Each document has a metadata header —
check it before using it.

STALENESS PROTOCOL:
Before using any retrieved document, check its metadata:
- "last_updated": must be within the last 90 days for policy questions
- "status": must be "ACTIVE" (not "SUPERSEDED", "DRAFT", or "ARCHIVED")
- "version": prefer the highest version number if multiple docs address the topic
If a retrieved document is stale or inactive:
1. Do NOT use its content to answer
2. State explicitly: "The retrieved document [doc_id] is dated [date] and marked
   [status]. I cannot rely on it for current policy."
3. If no fresh document is available, say: "I don't have a current version of
   this policy in my context. Please verify with the source system."

Today's date is 2026-08-22.

<retrieved_context>
{context}
</retrieved_context>"""

ARMS = [
    ("neutral", NEUTRAL),
    ("status only", STATUS_ONLY),
    ("date only", DATE_ONLY),
    ("status+date+version", METADATA_ONLY),
    ("full protocol", STALENESS_PROTOCOL),
]


def build_index(versions: list):
    from shared.deps import require

    require("chromadb", "chromadb", "building the retrieval index")
    import chromadb
    from chromadb.config import Settings

    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR)
    client = chromadb.PersistentClient(
        path=str(INDEX_DIR), settings=Settings(anonymized_telemetry=False)
    )
    collection = client.create_collection("staleness_prompt")
    collection.add(
        ids=[v["set_id"] for v in versions],
        documents=[v["text"] for v in versions],
        metadatas=[
            {
                "drug": v["drug"],
                "status": v["status"],
                "last_verified": v["effective_time"],
                "age_days": int(v["age_days"]),
            }
            for v in versions
        ],
    )
    return collection


def main() -> int:
    args = base_args(__doc__).parse_args()
    versions = load_versions()
    by_id = {v["set_id"]: v for v in versions}
    drugs = sorted({v["drug"] for v in versions})
    if args.limit:
        drugs = drugs[: args.limit]

    collection = build_index(versions)
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)

    rows = []
    stats = {
        name: {"kept_stale": 0, "refused_all": 0, "used_stale_value": 0, "no_dose": 0}
        for name, _ in ARMS
    }
    active_in_topk = 0

    for drug in drugs:
        result = stable_top_k(
            collection, f"recommended starting dose of {drug}", {"drug": drug}, TOP_K
        )
        # Sorted by id: an unsorted context changes the request hash run to run.
        retrieved = sorted(zip(result["ids"][0], result["documents"][0]))
        context = "\n\n---\n\n".join(
            f"[doc_id: {doc_id} | last_updated: {by_id[doc_id]['effective_time']} | "
            f"status: {by_id[doc_id]['status']} | version: {by_id[doc_id]['effective_time']}]\n{doc}"
            for doc_id, doc in retrieved
        )

        ids = [doc_id for doc_id, _ in retrieved]
        active_ids = {i for i in ids if by_id[i]["status"] == "ACTIVE"}
        stale_ids = [i for i in ids if i not in active_ids]
        active_in_topk += int(bool(active_ids))

        # Values a superseded label states that the current one does not. If one
        # of these is in the answer, the answer came from the stale document.
        current_values = set().union(
            *[dose_values(by_id[i]["text"]) for i in active_ids]
        ) if active_ids else set()
        stale_only = set().union(
            *[dose_values(by_id[i]["text"]) for i in stale_ids]
        ) - current_values if stale_ids else set()

        for name, system in ARMS:
            answer = llm.json(
                system=system.format(context=context),
                user=f"What is the recommended starting dose of {drug}?",
                schema=SCHEMA,
                max_tokens=700,
            )
            declared = set(answer["usable_doc_ids"])
            kept_stale = bool(declared & set(stale_ids))
            refused_all = not declared
            answer_values = dose_values(str(answer["starting_dose"] or ""))
            used_stale = bool(answer_values & stale_only)

            stats[name]["kept_stale"] += int(kept_stale)
            stats[name]["refused_all"] += int(refused_all)
            stats[name]["used_stale_value"] += int(used_stale)
            stats[name]["no_dose"] += int(answer["starting_dose"] is None)

            rows.append(
                [
                    drug[:20],
                    name,
                    f"{len(active_ids)}/{len(ids)}",
                    f"{len(declared)} declared usable",
                    "KEPT STALE" if kept_stale else ("refused all" if refused_all else "active only"),
                    "STALE VALUE" if used_stale else "-",
                ]
            )

    rule(f"Unfiltered top-{TOP_K} with honest metadata headers, two system prompts")
    table(
        ["drug", "prompt", "active in top-k", "model's verdict", "outcome", "answer content"],
        rows,
    )

    headline(
        "Retrievals where an ACTIVE document was in the top-k at all",
        pct(active_in_topk, len(drugs)),
        "The prompt cannot rescue a retrieval that never returned the current "
        "document. This is the ceiling on anything the prompt can do.",
    )
    for name in stats:
        headline(
            f"[{name}] declared a SUPERSEDED document usable",
            pct(stats[name]["kept_stale"], len(drugs)),
        )
        headline(
            f"[{name}] answered with a dose only a superseded label states",
            pct(stats[name]["used_stale_value"], len(drugs)),
            "The check that does not depend on what the model said about its "
            "own sources.",
        )
        headline(
            f"[{name}] refused every document / returned no dose",
            f"{stats[name]['refused_all']}/{len(drugs)} refused, "
            f"{stats[name]['no_dose']}/{len(drugs)} no dose",
            "The prompt's 90-day rule applies to the current label too. On this "
            "corpus most current labels are older than 90 days.",
        )

    print()
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
