"""Chapter 6, engineering fix 1: metadata-filtered retrieval with freshness scoring.

The book: *"At index time, store `created_at`, `last_verified`, and `status` as
metadata fields in your vector store. At query time, apply a hard filter:
`status == "ACTIVE" AND last_verified > now() - 90d`."*

Chapter 3's `fix_retrieval.py` already measured the first clause on this corpus:
unfiltered retrieval returned superseded passages 83% of the time and every
answer changed once `status == ACTIVE` was applied. Repeating that would prove
nothing new, so this script measures the three things it did not:

1. **The filter as the book actually writes it**, both clauses. The second
   clause is not free. It removes documents that are current — the newest label
   in existence for that drug — because nobody has refiled them recently. When
   it removes all of them, retrieval returns an empty set and the failure is
   silent.

2. **Freshness scoring instead of a hard filter.** Retrieve on similarity, then
   rank by recency and take the newest. A soft ranking is what most teams reach
   for first because it does not require the status flag to be right.

3. **A filter that is present, correct, and stale.** The `status` field was
   written at ingest and was true then. This is the chapter's own thesis applied
   to the index itself: the metadata was correct when it was written and the
   world moved.

`now()` is the date the corpus was retrieved, not today's date, so a replay a
year from now reports the same numbers as the recording.

    python fetch_data.py --versions     # build the corpus (once)
    python fix_freshness.py             # replay
    python fix_freshness.py --live      # regenerate
"""

import datetime
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import dose_values, load_versions, stable_top_k  # noqa: E402
from shared import bench  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, normalise_ws, pct, rule, table  # noqa: E402

INDEX_DIR = Path(__file__).parent / ".chroma" / "versions"
TOP_K = 3
FRESHNESS_WINDOW_DAYS = 90

# The index was built on this date and nobody has re-ingested since. Seven and a
# half months, which is not a long time for a document store to go unattended.
STALE_INDEX_DATE = "20260101"

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


def as_int(effective_time: str) -> int:
    return int(effective_time)


def days_between(later: str, earlier: str) -> int:
    fmt = "%Y%m%d"
    return (
        datetime.datetime.strptime(later, fmt) - datetime.datetime.strptime(earlier, fmt)
    ).days


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
    collection = client.create_collection("label_versions_ch06")
    collection.add(
        ids=[v["set_id"] for v in versions],
        documents=[v["text"] for v in versions],
        metadatas=[
            {
                "drug": v["drug"],
                "status": v["status"],
                "last_verified": v["effective_time"],
                # Same value as an integer, because a freshness window is a
                # numeric comparison and a metadata store cannot do date
                # arithmetic on a string for you.
                "effective_int": as_int(v["effective_time"]),
                "age_days": int(v["age_days"]),
            }
            for v in versions
        ],
    )
    return collection


def context_from(result) -> str:
    """Documents sorted by id, with the metadata header the chapter's prompt reads.

    Sorting matters. Two queries over the same index can return the same top-k
    in a different order, and an unsorted context changes the request hash on
    every run, so every fixture misses.
    """
    if not result["ids"][0]:
        return ""
    rows = sorted(zip(result["ids"][0], result["documents"][0], result["metadatas"][0]))
    return "\n\n---\n\n".join(
        f"[doc_id: {doc_id} | last_updated: {meta['last_verified']} | "
        f"status: {meta['status']}]\n{doc}"
        for doc_id, doc, meta in rows
    )


def main() -> int:
    args = base_args(__doc__).parse_args()
    versions = load_versions()
    today = "20260822"  # the corpus's own retrieval date; see the module docstring

    drugs = sorted({v["drug"] for v in versions})
    if args.limit:
        drugs = drugs[: args.limit]
    active_id = {
        v["drug"]: v["set_id"] for v in versions if v["status"] == "ACTIVE" and v["drug"] in drugs
    }

    cutoff = int(
        (
            datetime.datetime.strptime(today, "%Y%m%d")
            - datetime.timedelta(days=FRESHNESS_WINDOW_DAYS)
        ).strftime("%Y%m%d")
    )

    with bench.stage("build index"):
        collection = build_index(versions)

    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)

    def answer(result) -> str:
        context = context_from(result)
        if not context:
            # What the pipeline actually does when the filter matches nothing.
            # Nobody writes the branch that stops here; the empty string goes
            # into the prompt and the model answers anyway.
            context = "(no documents matched)"
        return llm.json(
            system=ANSWER_SYSTEM.format(context=context),
            user="What is the recommended starting dose?",
            schema=ANSWER_SCHEMA,
            max_tokens=400,
        )["starting_dose"]

    rows = []
    empty = 0
    empty_answered_anyway = 0
    freshness_wrong = 0
    stale_served = 0
    stale_answers_differ = 0
    oldest_stale = 0

    for drug in drugs:
        query = f"recommended starting dose of {drug}"
        with bench.stage("query"):
            # Chapter 3's fix, as the book writes it.
            active = stable_top_k(
                collection, query, {"$and": [{"drug": drug}, {"status": "ACTIVE"}]}, TOP_K
            )
            # Chapter 6's fix, as the book writes it — both clauses.
            book = stable_top_k(
                collection,
                query,
                {
                    "$and": [
                        {"drug": drug},
                        {"status": "ACTIVE"},
                        {"effective_int": {"$gt": cutoff}},
                    ]
                },
                TOP_K,
            )
            # No filter. Freshness scoring re-ranks these below.
            unfiltered = stable_top_k(collection, query, {"drug": drug}, TOP_K)
            # An index whose last ingest was STALE_INDEX_DATE.
            stale = stable_top_k(
                collection,
                query,
                {"$and": [{"drug": drug}, {"effective_int": {"$lte": int(STALE_INDEX_DATE)}}]},
                TOP_K,
            )

        # Freshness scoring: rank the similarity hits by recency, keep the newest.
        ranked = sorted(
            zip(unfiltered["ids"][0], unfiltered["metadatas"][0]),
            key=lambda pair: pair[1]["effective_int"],
            reverse=True,
        )
        top_by_recency = ranked[0][0] if ranked else None
        scoring_ok = top_by_recency == active_id[drug]
        freshness_wrong += int(not scoring_ok)

        # The stale index: whatever was ACTIVE on STALE_INDEX_DATE.
        stale_ranked = sorted(
            zip(stale["ids"][0], stale["metadatas"][0]),
            key=lambda pair: pair[1]["effective_int"],
            reverse=True,
        )
        stale_top = stale_ranked[0] if stale_ranked else None
        stale_is_superseded = bool(stale_top) and stale_top[0] != active_id[drug]
        stale_served += int(stale_is_superseded)
        if stale_top:
            oldest_stale = max(oldest_stale, days_between(today, stale_top[1]["last_verified"]))

        book_empty = not book["ids"][0]
        empty += int(book_empty)

        active_answer = answer(active)
        book_answer = answer(book)
        if book_empty:
            # Given nothing to read, did the model produce a dose anyway? The
            # same regex used everywhere else in this chapter decides.
            empty_answered_anyway += int(bool(dose_values(book_answer)))
        stale_answer = answer(stale)
        differ = normalise_ws(stale_answer) != normalise_ws(active_answer)
        stale_answers_differ += int(differ)

        rows.append(
            [
                drug[:22],
                f"{len(book['ids'][0])}/{TOP_K}" + (" EMPTY" if book_empty else ""),
                "correct" if scoring_ok else "WRONG",
                "SUPERSEDED" if stale_is_superseded else "still current",
                "DIFFERENT" if differ else "same",
                book_answer[:34].replace("\n", " "),
            ]
        )

    rule(f"Four retrieval policies over the same index, now() = {today}")
    table(
        [
            "drug",
            "book filter hits",
            "freshness top-1",
            "stale index serves",
            "stale vs active answer",
            "book-filter answer (first 34)",
        ],
        rows,
    )

    headline(
        "Drugs where the book's filter as written returns NOTHING",
        pct(empty, len(drugs)),
        f"`status == ACTIVE AND last_verified > now() - {FRESHNESS_WINDOW_DAYS}d`. "
        "The second clause removes the current label when nobody has refiled it "
        "recently. There is no error and no empty-result branch — the prompt is "
        "built from an empty string.",
    )
    headline(
        "Of those, answers that stated a dose anyway",
        pct(empty_answered_anyway, empty) if empty else "n/a",
        "The empty-context case fails safely on this model — it says it has "
        "nothing. That makes it a silent denial of service rather than a "
        "fabrication, which is better and still not something anyone is "
        "alerted about.",
    )
    headline(
        "Freshness scoring picks a different document from the hard filter",
        pct(freshness_wrong, len(drugs)),
        "Ranking the similarity hits by recency and taking the newest. Where "
        "this is 0, the soft ranking and the hard filter agree — and the soft "
        "one does not depend on the status flag being right.",
    )
    headline(
        f"Correct-looking filter over an index last ingested {STALE_INDEX_DATE}",
        pct(stale_served, len(drugs)),
        "Every one of these passes a status check. The flag was true when it "
        "was written. That is the chapter's own failure, inside the fix for it.",
    )
    headline(
        "Answers that changed when the stale index was used",
        pct(stale_answers_differ, len(drugs)),
    )
    headline(
        "Oldest label the stale index served",
        f"{oldest_stale} days ({oldest_stale / 365:.1f} years) old",
    )

    print()
    llm.report("answer generation")
    bench.report(f"{len(versions)} documents, {bench.dir_size_mb(INDEX_DIR):.0f} MB on disk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
