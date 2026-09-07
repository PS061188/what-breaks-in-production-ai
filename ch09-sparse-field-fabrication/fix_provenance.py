"""Chapter 9, engineering fix: embedding-based provenance checking.

The book: *"Guardrails AI's ProvenanceEmbeddings rail compares each extracted
value's embedding against the source document embedding and rejects values with
low semantic overlap. This is specifically designed for the 'plausible but
ungrounded' fabrication pattern."*

This implements that mechanism directly — embed the value, embed the source
chunks, take the best cosine, reject below a threshold — rather than installing
`guardrails-ai` and its validator hub. Same computation, no extra dependency,
and the threshold is swept instead of assumed.

It scores the **baseline** extractions from broken.py, so the question it
answers is precise: of the 14 fabrications that broken.py produced, how many
would this rail have stopped, and what would it have cost in real extractions?

There is a reason to doubt it in advance. Every one of those fabrications is
real text lifted from the wrong section of the same document. Its embedding
overlaps with the source because it *is* the source. A check built on semantic
overlap with the document as a whole has nothing to grip.

    python fix_provenance.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broken import SYSTEM, schema  # noqa: E402
from common import FIELD_LIST, FIELDS, build_cases, is_absent_answer  # noqa: E402
from shared import bench  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

BI_ENCODER = "sentence-transformers/all-MiniLM-L6-v2"
HF_CACHE = Path.home() / ".cache" / "huggingface"


def chunks(context: str) -> list:
    out = []
    for block in re.split(r"\n\s*\n", context):
        block = block.strip()
        for i in range(0, len(block), 600):
            piece = block[i : i + 600].strip()
            if len(piece) > 40:
                out.append(piece)
    return out


def main() -> int:
    args = base_args(__doc__).parse_args()
    # Always replayed: this rail is scored against the exact extractions
    # broken.py measured.
    llm = LLM(Path(__file__).parent, model=args.model, live=False)
    cases = build_cases(limit=args.limit)

    with bench.stage("load model"):
        from shared.deps import require

        require("sentence_transformers", "sentence-transformers",
                "embedding each extracted value against the source document")
        from sentence_transformers import SentenceTransformer
        from sentence_transformers.util import cos_sim

        model = SentenceTransformer(BI_ENCODER)

    rows = []
    scored = []  # (is_fabrication, is_real_extraction, score)
    values_embedded = 0

    for case in cases:
        result = llm.json(
            system=SYSTEM.format(context=case["context"]),
            user=f"Extract these fields: {FIELD_LIST}",
            schema=schema(),
            max_tokens=2000,
        )
        source_chunks = chunks(case["context"])

        with bench.stage("embed"):
            chunk_vecs = model.encode(source_chunks, convert_to_tensor=True, show_progress_bar=False)
            values = [result[name]["value"] for name, _ in FIELDS]
            value_vecs = model.encode(values, convert_to_tensor=True, show_progress_bar=False)
            values_embedded += len(values)
            sims = cos_sim(value_vecs, chunk_vecs)

        for i, (name, _) in enumerate(FIELDS):
            value = result[name]["value"]
            score = float(sims[i].max())
            declined = is_absent_answer(value)

            fabrication = (not case["present"][name]) and (not declined)
            real = case["present"][name] and (not declined)
            scored.append((fabrication, real, score))

            if fabrication:
                rows.append(
                    [case["drug"][:18], name, f"{score:.2f}", str(value)[:46].replace("\n", " ")]
                )

    rule("The 14 fabrications, and how well each one matches the source")
    table(["drug", "field", "best cosine", "fabricated value (first 46)"], rows)

    rule("Threshold sweep — reject a value scoring below T")
    sweep = []
    fabrications = [s for f, _, s in scored if f]
    real_values = [s for _, r, s in scored if r]
    for threshold in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        caught = sum(1 for s in fabrications if s < threshold)
        lost = sum(1 for s in real_values if s < threshold)
        sweep.append(
            [threshold, pct(caught, len(fabrications)), pct(lost, len(real_values))]
        )
    table(["threshold", "fabrications rejected", "real extractions destroyed"], sweep)

    best = max(fabrications) if fabrications else 0
    worst_real = min(real_values) if real_values else 0
    headline(
        "Highest-scoring fabrication vs lowest-scoring real extraction",
        f"{best:.2f} vs {worst_real:.2f}",
        "If the first number is not below the second, no threshold separates them "
        "and the rail cannot work on this failure — whatever value you pick.",
    )
    headline(
        "Why",
        "the fabricated text is really in the document",
        "Chapter 9's fabrications are pediatric dosing lifted out of the "
        "indications section. Semantic overlap with the document is high because "
        "the text came from the document. This rail is built for invented "
        "content, and misattributed content is not invented.",
    )

    print()
    llm.report("extractions replayed")
    bench.report(
        f"{values_embedded} values embedded  ·  weights on disk {bench.dir_size_mb(HF_CACHE):.0f} MB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
