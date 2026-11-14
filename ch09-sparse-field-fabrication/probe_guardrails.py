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

"Every threshold" is exact, not a grid: the validator fails a value when its
worst sentence's nearest-chunk distance is >= threshold, so each value has one
distance, and one threshold per distinct distance gives every result the
validator can produce. Those distances come from the validator's own query
function; at the seven listed thresholds the script checks that they give the
validator's own pass/fail on every entry.

It needs its own environment: guardrails-ai 0.6.8, the validator package from
github.com/guardrails-ai/provenance_embeddings, and sentence-transformers.
run_all.py skips it when they are missing.

  python3.11 -m venv .venv-guardrails && . .venv-guardrails/bin/activate
  pip install guardrails-ai==0.6.8 sentence-transformers \\
      git+https://github.com/guardrails-ai/provenance_embeddings
  python -m nltk.downloader punkt_tab        # the validator needs it; its setup does not fetch it
  python probe_guardrails.py | tee guardrails_sweep_log.txt

guardrails_sweep_log.txt is the last run's output.
"""

import sys
import warnings
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
warnings.filterwarnings("ignore")

from shared.deps import require  # noqa: E402

require("guardrails", "guardrails-ai==0.6.8", "Experiment 9.5's packaged-validator rerun")
require("validator", "git+https://github.com/guardrails-ai/provenance_embeddings", "Experiment 9.5's packaged-validator rerun")
require("sentence_transformers", "sentence-transformers", "Experiment 9.5's packaged-validator rerun")

import nltk  # noqa: E402
import numpy as np  # noqa: E402
import probe_checks as C  # noqa: E402
from validator import ProvenanceEmbeddings  # noqa: E402
from guardrails.settings import settings  # noqa: E402
from guardrails.validator_base import FailResult  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

# Without a ~/.guardrailsrc saying otherwise, every validator built sends usage
# traces to the Guardrails hub. Nothing here needs the hub.
settings.rc.enable_metrics = False
settings.rc.use_remote_inferencing = False

GRID = (0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2)
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


def meta(e, chunk_size, chunk_overlap):
    return {"sources": safe_sources(e["dialogue"], chunk_size, chunk_overlap),
            "embed_function": embed_function,
            "chunk_strategy": "sentence", "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap}


def run(entries, threshold, chunk_size, chunk_overlap):
    """The validator's own pass/fail for each entry."""
    v = ProvenanceEmbeddings(threshold=threshold, validation_method="sentence")
    return [isinstance(v.validate(e["entry"], meta(e, chunk_size, chunk_overlap)), FailResult)
            for e in entries]


def distances(entries, chunk_size, chunk_overlap):
    """Each entry's worst-sentence distance, from the validator's own query function.
    The validator fails the entry at every threshold <= this distance."""
    v = ProvenanceEmbeddings(validation_method="sentence")
    out = []
    for e in entries:
        query = v.get_query_function(meta(e, chunk_size, chunk_overlap))
        out.append(max((float(query(text=s, k=1)[0][1]) for s in nltk.sent_tokenize(e["entry"])),
                       default=float("-inf")))
    return out


def check(entries, dist, threshold, chunk, where):
    """Fail loudly if the distances and the validator ever disagree on an entry."""
    failed = run(entries, threshold, *chunk)
    if failed != [d >= threshold for d in dist]:
        raise SystemExit(f"distances disagree with the validator: {where}, threshold {threshold}")
    return failed


def tally(entries, failed):
    caught = sum(f and e["invented"] for e, f in zip(entries, failed))
    flagged = sum(f and not e["invented"] for e, f in zip(entries, failed))
    return caught, flagged


def every_threshold(entries, dist):
    inv = [d for e, d in zip(entries, dist) if e["invented"]]
    other = [d for e, d in zip(entries, dist) if not e["invented"]]
    cuts = sorted({d for d in dist if d > float("-inf")}) + [float("inf")]
    rows = [(th, sum(d >= th for d in inv), sum(d >= th for d in other)) for th in cuts]
    all_caught = [r for r in rows if r[1] == len(inv)]
    loosest = max(all_caught, key=lambda r: r[0])
    best = max(rows, key=lambda r: r[1] / len(inv) - r[2] / len(other))
    auc = sum((a > b) + 0.5 * (a == b) for a in inv for b in other) / (len(inv) * len(other))
    return len(cuts), loosest, best, auc


def main() -> int:
    note = C.entries()
    rec = C.schema_entries()
    sets = [("notes", note, sum(e["invented"] for e in note)),
            ("records", rec, sum(e["invented"] for e in rec))]
    print("validator: guardrails/provenance_embeddings · sentence method · k=1 · cosine distance")
    print(f"guardrails-ai {version('guardrails-ai')} · provenance-embeddings {version('provenance-embeddings')}"
          f" · sentence-transformers {version('sentence-transformers')} · nltk {version('nltk')}"
          " · embeddings all-MiniLM-L6-v2")
    print("threshold is a DISTANCE: pass when nearest-chunk distance < threshold\n")
    for label, chunk in (("default chunking (5-sentence windows, overlap 2)", (5, 2)),
                         ("sentence-fine chunking (size 1, overlap 0)", (1, 0))):
        print(f"== {label}")
        dist = {name: distances(es, *chunk) for name, es, _ in sets}
        print(f"{'distance threshold':>18} | " + " | ".join(
            f"{name}: caught/of {ninv}, flagged/of {len(es)-ninv}" for name, es, ninv in sets))
        for th in GRID:
            cells = []
            for name, es, ninv in sets:
                c, f = tally(es, check(es, dist[name], th, chunk, f"{label}, {name}"))
                cells.append(f"{name}: {c}/{ninv}, {f}/{len(es)-ninv}")
            print(f"{th:>18} | " + " | ".join(cells))
        print("   every threshold — one per distinct distance. Best balance = highest share caught minus")
        print("   share flagged. AUC = chance an invented entry sits further from its source than a")
        print("   discussed one (0.5 = coin flip, 1.0 = perfect separation):")
        for name, es, ninv in sets:
            n, loosest, best, auc = every_threshold(es, dist[name])
            for th in (loosest[0], best[0]):
                check(es, dist[name], th, chunk, f"{label}, {name}")
            nother = len(es) - ninv
            print(f"   {name}: {n} settings · loosest that catches all {ninv}: distance {loosest[0]:.3f}, "
                  f"flags {loosest[2]}/{nother} ({loosest[2]/nother:.0%}) · best balance: distance {best[0]:.3f}, "
                  f"catches {best[1]}/{ninv}, flags {best[2]}/{nother} · AUC {auc:.2f}")
        print("   (the validator's own pass/fail was checked against these distances, entry by entry,")
        print("    at the seven thresholds in the table and at every distance named above)\n")
    print("from-scratch 9.5 on the notes, for comparison (similarity cut = 1 - distance):")
    print("  sim 0.5 -> caught 6/12, flagged 19/89 · sim 0.7 -> caught 10/12, flagged 72/89")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
