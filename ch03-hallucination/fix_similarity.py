"""Chapter 3, engineering fix: semantic similarity cross-check after generation.

The book: *"Run a cross-encoder model (cross-encoder/ms-marco-MiniLM-L-6-v2 via
sentence-transformers) to score each generated claim against retrieved
passages. Claims scoring below 0.4 cosine similarity with any retrieved passage
are flagged before delivery."*

That instruction cannot be followed as written, and the reason is worth knowing:

**A cross-encoder does not produce a cosine similarity.** It takes a (query,
passage) pair and emits a single unbounded relevance logit — for
ms-marco-MiniLM-L-6-v2, roughly -11 to +11. There is no cosine anywhere in it,
so "below 0.4 cosine" has no meaning against that model. Cosine similarity
comes from a **bi-encoder**, which embeds the two texts separately and compares
the vectors.

So this script runs both, on the same claims, and sweeps the threshold:

  cross-encoder  ms-marco-MiniLM-L-6-v2, logit -> sigmoid -> 0..1
  bi-encoder     all-MiniLM-L6-v2, cosine -> the 0.4 the book actually describes

No API calls: this fix runs entirely on your machine. What it costs is a
dependency, a model download, and CPU. Those numbers are printed at the end.

    python fix_similarity.py            # replay the answers, score locally
    python fix_similarity.py --live     # regenerate the answers too
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broken import SCHEMA, SOFT_INFERENCE  # noqa: E402
from common import build_cases  # noqa: E402
from shared import bench  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"
BI_ENCODER = "sentence-transformers/all-MiniLM-L6-v2"

# Where sentence-transformers caches the weights, so the footprint can be shown.
HF_CACHE = Path.home() / ".cache" / "huggingface"


def sentences(text: str) -> list:
    """Claim-level split. Crude on purpose — this is what a pipeline does."""
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 25]


def passages(context: str) -> list:
    """The retrieved passages a claim is scored against."""
    chunks = [c.strip() for c in re.split(r"\n\s*\n", context) if len(c.strip()) > 40]
    out = []
    for chunk in chunks:
        # Long label sections are chunked so a claim is compared against
        # something its own size. Comparing one sentence to 3,000 characters
        # dilutes every score toward the middle.
        for i in range(0, len(chunk), 600):
            piece = chunk[i : i + 600].strip()
            if len(piece) > 40:
                out.append(piece)
    return out


def main() -> int:
    parser = base_args(__doc__)
    parser.add_argument(
        "--threshold", type=float, default=0.4, help="flag claims scoring below this (default 0.4)"
    )
    args = parser.parse_args()

    # Always replayed: this check scores the same answers broken.py measured.
    generator = LLM(Path(__file__).parent, model=args.model, live=False)
    cases = build_cases(limit=args.limit)

    with bench.stage("load models"):
        from shared.deps import require

        require("sentence_transformers", "sentence-transformers",
                "scoring each claim against the retrieved passages")
        from sentence_transformers import CrossEncoder, SentenceTransformer
        from sentence_transformers.util import cos_sim

        cross = CrossEncoder(CROSS_ENCODER)
        bi = SentenceTransformer(BI_ENCODER)

    def sigmoid(x):
        import math

        return 1.0 / (1.0 + math.exp(-x))

    rows = []
    pairs_scored = 0
    scored = []  # (answerable, min_cross, min_bi)

    for case in cases:
        answer = generator.json(
            system=SOFT_INFERENCE.format(context=case["context"]),
            user=case["question"],
            schema=SCHEMA,
            max_tokens=800,
        )["answer"]

        claims = sentences(answer)
        chunks = passages(case["context"])
        if not claims or not chunks:
            continue

        with bench.stage("cross-encoder"):
            cross_scores = []
            for claim in claims:
                raw = cross.predict([(claim, chunk) for chunk in chunks])
                pairs_scored += len(chunks)
                cross_scores.append(max(sigmoid(float(v)) for v in raw))

        with bench.stage("bi-encoder"):
            claim_vecs = bi.encode(claims, convert_to_tensor=True, show_progress_bar=False)
            chunk_vecs = bi.encode(chunks, convert_to_tensor=True, show_progress_bar=False)
            sim = cos_sim(claim_vecs, chunk_vecs)
            bi_scores = [float(sim[i].max()) for i in range(len(claims))]

        worst_cross, worst_bi = min(cross_scores), min(bi_scores)
        scored.append((case["answerable"], worst_cross, worst_bi))

        rows.append(
            [
                case["drug"][:18],
                case["needed_section"][:20],
                "in ctx" if case["answerable"] else "NOT in ctx",
                len(claims),
                f"{worst_cross:.2f}",
                f"{worst_bi:.2f}",
            ]
        )

    rule("Per answer — lowest-scoring claim in it")
    table(
        ["drug", "section needed", "available?", "claims", "cross-enc", "bi-enc cos"],
        rows,
    )

    rule("Threshold sweep — flag an answer if any claim scores below T")
    sweep = []
    for threshold in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
        for name, index in (("cross-encoder", 1), ("bi-encoder cosine", 2)):
            caught = sum(1 for a, c, b in scored if not a and (c, b)[index - 1] < threshold)
            ungrounded = sum(1 for a, _, _ in scored if not a)
            false_alarm = sum(1 for a, c, b in scored if a and (c, b)[index - 1] < threshold)
            grounded = sum(1 for a, _, _ in scored if a)
            sweep.append([name, threshold, pct(caught, ungrounded), pct(false_alarm, grounded)])
    table(["scorer", "threshold", "caught (ungrounded)", "false alarms (grounded)"], sweep)

    headline(
        "The book's threshold, applied to the model the book names",
        "not defined",
        f"{CROSS_ENCODER} returns an unbounded relevance logit, not a cosine. "
        "The 0.4 in the chapter belongs to a bi-encoder. Both are in the sweep above.",
    )

    print()
    generator.report("generator")
    bench.report(
        f"{pairs_scored:,} cross-encoder pairs"
        f"  ·  weights on disk {bench.dir_size_mb(HF_CACHE):.0f} MB"
    )
    print(
        "  [note] no API cost — this fix is CPU and disk. It scales with "
        "claims x passages, so chunking is the cost lever.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
