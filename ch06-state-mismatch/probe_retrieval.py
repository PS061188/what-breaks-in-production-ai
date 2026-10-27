"""Experiment 6.7 — retrieval fetched the wrong document.

Every fix in Chapter 6 assumes the retrieval step handed the model a document
about the right subject, possibly a stale one. This probe measures how often
that assumption fails at the retrieval step itself, with no model involved:
BM25 lexical retrieval over the twelve FDA labels' sections, scored against the
one label each query is about.

Conditions, crossed:
  query arm   NAMED    the chapter 3 question as written ("What is the
                       recommended starting dose of Warfarin?")
              FOLLOWUP the same question with the drug name replaced by "this
                       medicine" — the form a follow-up turn takes in a chat,
                       and what a pipeline retrieves with when it embeds only
                       the latest turn
  chunking    SECTION  one chunk per label section, cut on the section boundary
              FIXED    800-character chunks, cut at fixed length mid-sentence

Scored per query: whether the top-ranked chunk comes from the right drug's
label, whether any of the top three does, and (where the label has the section
that answers the question) whether the top-ranked chunk contains text of that
section. Deterministic end to end: no model call, no fixture, no seed.

    python3 probe_retrieval.py
"""

import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.llm import load_labels  # noqa: E402

QUESTIONS = [
    ("What conditions is {drug} indicated to treat?", "indications_and_usage"),
    ("What is the recommended starting dose of {drug}?", "dosage_and_administration"),
    ("What are the most common adverse reactions to {drug}?", "adverse_reactions"),
    ("What is the recommended dose of {drug} for pediatric patients?", "pediatric_use"),
    ("Is {drug} safe to use during pregnancy?", "pregnancy"),
    ("Which other drugs interact with {drug}?", "drug_interactions"),
]

FIXED_LEN = 800


def tokens(text: str) -> list:
    return re.findall(r"[a-z0-9]+", text.lower())


def chunk_corpus(labels: list, mode: str) -> list:
    """[(drug, section, text)] — FIXED keeps the section a chunk starts in."""
    chunks = []
    for label in labels:
        for section, text in label["sections"].items():
            if not text:
                continue
            if mode == "SECTION":
                chunks.append((label["drug"], section, text))
            else:
                for i in range(0, len(text), FIXED_LEN):
                    chunks.append((label["drug"], section, text[i:i + FIXED_LEN]))
    return chunks


class BM25:
    """Plain Okapi BM25, k1=1.5, b=0.75."""

    def __init__(self, docs: list):
        self.docs = [tokens(d) for d in docs]
        self.avg = sum(map(len, self.docs)) / len(self.docs)
        self.tf = [Counter(d) for d in self.docs]
        df = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def rank(self, query: str, k: int = 3) -> list:
        q = tokens(query)
        scores = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            dl = len(self.docs[i])
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * dl / self.avg))
            scores.append((s, i))
        scores.sort(key=lambda x: (-x[0], x[1]))
        return [i for _, i in scores[:k]]


def main() -> int:
    labels = load_labels()
    drugs = [la["drug"] for la in labels]
    for chunking in ("SECTION", "FIXED"):
        chunks = chunk_corpus(labels, chunking)
        bm25 = BM25([c[2] for c in chunks])
        for arm in ("NAMED", "FOLLOWUP"):
            tally = Counter()
            wrong_docs = Counter()
            for drug in drugs:
                has = {s for s, t in next(la for la in labels if la["drug"] == drug)["sections"].items() if t}
                for template, needed in QUESTIONS:
                    query = template.format(drug=drug if arm == "NAMED" else "this medicine")
                    top = bm25.rank(query, 3)
                    tally["queries"] += 1
                    top_drug, top_section, _ = chunks[top[0]]
                    if top_drug != drug:
                        tally["top1 wrong document"] += 1
                        wrong_docs[top_drug] += 1
                    if any(chunks[i][0] == drug for i in top):
                        tally["right document in top 3"] += 1
                    if needed in has:
                        tally["needed section exists"] += 1
                        if top_drug == drug and top_section == needed:
                            tally["top1 is the needed section"] += 1
            print(f"\n{chunking} chunks ({len(chunks)}), {arm} queries:")
            for key in ("queries", "top1 wrong document", "right document in top 3",
                        "needed section exists", "top1 is the needed section"):
                print(f"  {key}: {tally[key]}")
            if wrong_docs:
                top3 = ", ".join(f"{d} ×{n}" for d, n in wrong_docs.most_common(3))
                print(f"  wrong documents most retrieved: {top3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
