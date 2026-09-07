"""Chapter 3, engineering fix: version-locked document retrieval.

The book: *"For any system advising on policies, terms, or regulations: store
status and last_verified as metadata fields in your vector store (Pinecone,
Weaviate, Qdrant all support metadata filters). Apply a hard filter —
status == 'ACTIVE' — at query time."*

This builds a real vector store and runs the query both ways. Chroma is used
instead of the three named services because it runs locally with no account, no
server, and no key; the metadata filter is the same idea in all of them.

**The corpus is genuinely versioned.** openFDA carries hundreds of labels per
generic drug, filed by different repackagers over many years, each with its own
`effective_time`. The newest per drug is ACTIVE; every older one is a real
superseded version of a real document. Nothing is synthetic. The oldest label
in the index is years behind its drug's current one — which is exactly the
Air Canada shape: a confident answer generated from a version of the policy
that is no longer in force.

    python fetch_data.py --versions     # build the corpus (once)
    python fix_retrieval.py             # replay the answers
    python fix_retrieval.py --live      # regenerate them
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.retrieval import stable_top_k  # noqa: E402

from shared import bench  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, normalise_ws, pct, rule, table  # noqa: E402

INDEX_DIR = Path(__file__).parent / ".chroma"
CORPUS = Path(__file__).resolve().parent.parent / "data" / "label_versions.json"
TOP_K = 3

ANSWER_SYSTEM = """You are a clinical information assistant. Answer using only
the retrieved label passages below.

<retrieved_passages>
{context}
</retrieved_passages>"""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"starting_dose": {"type": "string"}},
    "required": ["starting_dose"],
    "additionalProperties": False,
}


def build_index(versions: list):
    from shared.deps import require

    require("chromadb", "chromadb", "building the version-locked vector index")
    import chromadb
    from chromadb.config import Settings

    # Rebuild from scratch so the build time measured below is a real cold
    # build, not an append to a warm index.
    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR)

    client = chromadb.PersistentClient(
        path=str(INDEX_DIR), settings=Settings(anonymized_telemetry=False)
    )
    collection = client.create_collection("label_versions")
    collection.add(
        ids=[v["set_id"] for v in versions],
        documents=[v["text"] for v in versions],
        metadatas=[
            {
                "drug": v["drug"],
                "status": v["status"],          # the filter the chapter specifies
                "last_verified": v["effective_time"],
                "age_days": v["age_days"],
                "labeler": v["labeler"][:60],
            }
            for v in versions
        ],
    )
    return collection


def main() -> int:
    args = base_args(__doc__).parse_args()

    if not CORPUS.is_file():
        print("Run `python fetch_data.py --versions` first.", file=sys.stderr)
        return 1

    versions = json.loads(CORPUS.read_text())["versions"]
    drugs = sorted({v["drug"] for v in versions})
    if args.limit:
        drugs = drugs[: args.limit]

    with bench.stage("build index"):
        collection = build_index(versions)

    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)

    rows = []
    stale_hits = total_hits = 0
    answers_differ = 0
    oldest_served = 0

    for drug in drugs:
        query = f"recommended starting dose of {drug}"

        with bench.stage("query"):
            # stable_top_k, not collection.query. An approximate index does not
            # promise a stable top-k *membership* when several documents sit at
            # effectively the same distance, and this corpus is 48 near-identical
            # versions of six labels, so ties are the normal case. Before this,
            # the script failed to replay roughly one run in two: a different
            # top-k built different prompt text, which is a different cache key.
            unfiltered = stable_top_k(collection, query, {"drug": drug}, TOP_K)
            filtered = stable_top_k(
                collection, query,
                {"$and": [{"drug": drug}, {"status": "ACTIVE"}]}, TOP_K,
            )

        un_meta = unfiltered["metadatas"][0]
        stale = [m for m in un_meta if m["status"] == "SUPERSEDED"]
        stale_hits += len(stale)
        total_hits += len(un_meta)
        worst_age = max((m["age_days"] for m in un_meta), default=0)
        oldest_served = max(oldest_served, worst_age)

        def answer(result) -> str:
            # stable_top_k already fixes membership and rank. Sorting by id here
            # additionally fixes the order the documents are concatenated in.
            ordered = sorted(zip(result["ids"][0], result["documents"][0]))
            context = "\n\n---\n\n".join(doc for _, doc in ordered)
            return llm.json(
                system=ANSWER_SYSTEM.format(context=context),
                user=f"What is the recommended starting dose of {drug}?",
                schema=ANSWER_SCHEMA,
                max_tokens=400,
            )["starting_dose"]

        un_answer, ac_answer = answer(unfiltered), answer(filtered)
        differ = normalise_ws(un_answer) != normalise_ws(ac_answer)
        answers_differ += int(differ)

        rows.append(
            [
                drug[:22],
                f"{len(stale)}/{len(un_meta)}",
                f"{worst_age}d",
                "DIFFERENT" if differ else "same",
                un_answer[:44].replace("\n", " "),
            ]
        )

    rule(f"Top-{TOP_K} retrieval per drug, unfiltered vs status == ACTIVE")
    table(
        ["drug", "stale in top-k", "oldest served", "answer", "unfiltered answer (first 44)"],
        rows,
    )

    headline(
        "Retrieved passages that were superseded versions",
        pct(stale_hits, total_hits),
        "Unfiltered. With the status filter this is 0% by construction — that is "
        "the whole fix, and it is one clause in the query.",
    )
    headline(
        "Oldest superseded label served to the model",
        f"{oldest_served} days ({oldest_served / 365:.1f} years) behind the current label",
    )
    headline(
        "Drugs where the two answers differ",
        pct(answers_differ, len(drugs)),
        "Where they match, the stale version happened to still be right. That is "
        "luck, and it is not visible from the answer.",
    )

    print()
    llm.report("answer generation")
    bench.report(f"index {bench.dir_size_mb(INDEX_DIR):.0f} MB on disk, {len(versions)} documents")
    print(
        "  [note] the filter itself costs nothing at query time. The cost is the "
        "index, and the discipline of writing status/last_verified at ingest.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
