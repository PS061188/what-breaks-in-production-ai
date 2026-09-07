"""Deterministic top-k over a vector store.

Approximate nearest-neighbour indexes do not promise a stable result. Two
queries over two builds of the same index can return a different top-k
*membership* when several documents sit at effectively the same distance, and
on a corpus of near-identical document versions that is the normal case rather
than the edge case.

That instability is invisible until something downstream is content-addressed.
Chapter 3's retrieval script failed to replay roughly half the time before this
was applied to it, because a different top-k produced different prompt text and
therefore a different cache key.
"""

def stable_top_k(collection, query_text: str, where: dict, k: int, pool: int = 64) -> dict:
    """Deterministic top-k, returned in Chroma's own result shape.

    Chapter 3 hit a version of this and fixed half of it: two queries over the
    same index can return the same top-k in a different *order*, so it sorted
    the documents by id before building the prompt. That is not the whole
    problem. On this corpus the same query can also return a different top-k
    *membership* from one index build to the next — the label versions are filed
    by different repackagers and many of them are near-identical text, so
    several documents sit at effectively the same distance and an approximate
    index breaks the tie however it likes. One drug in six missed its fixture on
    replay because of it.

    Over-fetching past the size of the filtered set makes the candidate list
    complete, and sorting on (distance, id) makes the choice among ties
    reproducible. Both are the caller's job; the vector store does not promise
    either.
    """
    result = collection.query(query_texts=[query_text], n_results=pool, where=where)
    ranked = sorted(
        zip(
            result["distances"][0],
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
        ),
        key=lambda row: (round(row[0], 6), row[1]),
    )[:k]
    return {
        "ids": [[row[1] for row in ranked]],
        "documents": [[row[2] for row in ranked]],
        "metadatas": [[row[3] for row in ranked]],
        "distances": [[row[0] for row in ranked]],
    }
