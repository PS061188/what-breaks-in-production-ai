"""Experiment 9.5, rerun with the packaged validator (Guardrails ProvenanceEmbeddings).

The book's fix 6 cites Guardrails AI's ProvenanceEmbeddings validator; 9.5
measured the check it packages with a from-scratch implementation. Prachi asked
for the product itself to be run. This probe runs the installed validator
(guardrails-ai 0.6.8; the validator package installed from its GitHub source,
because the hub's API host does not resolve from this machine) over the same
labelled entries as 9.5: the 101 note entries (12 invented) and the 56 record
values (7 invented). No model calls; everything is local embeddings.

How the validator works (read from its source):
  - the OUTPUT is split into sentences with nltk; each sentence is scored
    against its nearest SOURCE CHUNK (k=1); a sentence fails when the cosine
    DISTANCE to that chunk is >= threshold (default 0.8 distance = 0.2
    similarity); any failing sentence fails the whole value.
  - the SOURCES are chunked with chunk_strategy "sentence", chunk_size 5,
    chunk_overlap 2 by default: five-sentence windows, not single sentences.
  - metadata must carry either query_function, or sources + embed_function.

Run it with the experiment's own environment, not the system python:

    .../scratchpad/venv-guardrails/bin/python probe_guardrails.py
"""

import sys
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
warnings.filterwarnings("ignore")

import probe_checks as C  # noqa: E402
from validator import ProvenanceEmbeddings  # noqa: E402
from guardrails.validator_base import FailResult  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
_CACHE = {}


def embed_function(text):
    texts = [text] if isinstance(text, str) else list(text)
    new = [x for x in texts if x not in _CACHE]
    if new:
        for x, v in zip(new, MODEL.encode(new)):
            _CACHE[x] = v
    return np.array([_CACHE[x] for x in texts])


from validator.main import get_chunks_from_text  # noqa: E402


def safe_sources(dialogue, chunk_size, chunk_overlap):
    """The validator squeezes a single-chunk embedding matrix to 1-D and then
    crashes on norm(axis=1) — a bug in the package, hit by transcripts with
    sparse punctuation. Duplicating the source doubles its chunks without
    changing any nearest-chunk distance, so k=1 results are identical."""
    chunks = get_chunks_from_text(dialogue, "sentence", chunk_size, chunk_overlap)
    return [dialogue, dialogue] if len(chunks) < 2 else [dialogue]


def run(entries, threshold, chunk_size, chunk_overlap):
    v = ProvenanceEmbeddings(threshold=threshold, validation_method="sentence")
    caught = flagged = 0
    fails = []
    for e in entries:
        meta = {"sources": safe_sources(e["dialogue"], chunk_size, chunk_overlap),
                "embed_function": embed_function,
                "chunk_strategy": "sentence", "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap}
        res = v.validate(e["entry"], meta)
        failed = isinstance(res, FailResult)
        if failed and e["invented"]:
            caught += 1
        elif failed:
            flagged += 1
            fails.append(e["id"])
    return caught, flagged, fails


def main() -> int:
    note = C.entries()
    rec = C.schema_entries()
    sets = [("notes", note, sum(e["invented"] for e in note)),
            ("records", rec, sum(e["invented"] for e in rec))]
    print("validator: guardrails/provenance_embeddings · sentence method · k=1 · cosine distance")
    print("threshold is a DISTANCE: pass when nearest-chunk distance < threshold\n")
    for label, chunk in (("default chunking (5-sentence windows, overlap 2)", (5, 2)),
                         ("sentence-fine chunking (size 1, overlap 0)", (1, 0))):
        print(f"== {label}")
        print(f"{'distance threshold':>18} | " + " | ".join(
            f"{name}: caught/of {ninv}, flagged/of {len(es)-ninv}" for name, es, ninv in sets))
        for th in (0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2):
            cells = []
            for name, es, ninv in sets:
                c, f, _ = run(es, th, *chunk)
                cells.append(f"{name}: {c}/{ninv}, {f}/{len(es)-ninv}")
            print(f"{th:>18} | " + " | ".join(cells))
        print()
    print("from-scratch 9.5 on the notes, for comparison (similarity cut = 1 - distance):")
    print("  sim 0.5 -> caught 6/12, flagged 19/89 · sim 0.7 -> caught 10/12, flagged 72/89")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
