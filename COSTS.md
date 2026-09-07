# Cost and compute for every prompt and engineering fix

What each fix costs to run, and what it scales with. The scaling column is the
one that matters — a fix that is free on 12 documents can be the largest line in
a budget at 12 million.

**Measured on:** Apple M-series laptop, CPU only, no GPU. Claude Haiku 4.5
unless noted. 12 FDA drug labels. Prices are the published rates at time of
writing: Haiku 4.5 $1/$5 per MTok, Sonnet 5 $3/$15, Opus 5 $5/$25.

Treat every timing as an order of magnitude, not a benchmark.

---

## Two kinds of cost, and they do not trade off the same way

| | API-cost fixes | Local-compute fixes |
|---|---|---|
| Examples | LLM-as-judge, the generation prompt itself | Cross-encoder similarity, embedding provenance, vector-store filter |
| Setup cost | none | dependency install, model download (80–370 MB), index build |
| Marginal cost | **money, forever, per call** | CPU-seconds; no per-call fee |
| Scales badly with | request volume | document size × claim count |
| Fails at scale by | budget | latency and RAM |

A team that dismisses the local fixes as "heavy" has usually only priced the
setup. A team that dismisses the API fixes as "cheap" has usually only priced
one call.

---

## Measured — chapter runs

Full corpus, one pass. Latency is derived from timed calls (see the note below
the table).

| Script | Model calls | Tokens (in/out) | Cost | Est. wall-clock |
|---|---|---|---|---|
| ch03 `broken.py` (2 baselines + judge classifier) | 288 | 474k / 30k | **$0.63** | ~10 min |
| ch03 `fixed.py` | 72 | 231k / 14k | **$0.30** | ~4.5 min |
| ch05 `broken.py` | 12 | 15k / 4.8k | **$0.04** | ~1.5 min |
| ch05 `fixed.py` | 12 | 17k / 4.9k | **$0.04** | ~1.5 min |
| ch09 `broken.py` | 12 | 24k / 7.8k | **$0.06** | ~2.5 min |
| ch09 `fixed.py` | 12 | 33k / 8.9k | **$0.08** | ~3 min |
| **Full re-record** | 408 | 795k / 70k | **$1.15** | ~25 min |

**Measured throughput**, from calls with recorded latency:

| Model | Timed calls | s/call | Output tokens/s |
|---|---|---|---|
| Haiku 4.5 | 15 | 1.57 | 51 |
| Sonnet 5 | 72 | 4.12 | 64 |

Wall-clock above is derived from output tokens at those rates, sequentially. It
is the number to quote for a naive loop; batching or concurrency changes it and
cost does not move.

Replaying costs nothing and takes seconds — `python run_all.py`.

---

## Chapter 3 — per fix

| Fix | Cost per 1,000 answers | Added latency per answer | Setup | Scales with |
|---|---|---|---|---|
| **Grounding prompt** (`fixed.py`) | ~$4.20 | none — replaces the call | none | context length. Longer sources → linear input cost. |
| **Structured schema** (citations + unverified_claims) | included above | +output tokens for citations, ~20% here | none | number of claims per answer |
| **Citation enforcement in code** | $0 | <1 ms | none | nothing. It is an `if`. |
| **Fuzzy quote verification** (`shared/scoring.py`) | $0 | <1 ms per quote with RapidFuzz | `pip install rapidfuzz`, 2 MB | quote length × document length. Bounded by `VERIFY_WINDOW`. |
| **LLM-as-judge** (`fix_judge.py`, Sonnet 5) | **$41** | **+4.1 s** | none | every answer, forever. The most expensive fix in the book. |
| **Cross-encoder similarity** (`fix_similarity.py`) | $0 API | +0.23 s | 367 MB weights, 10.3 s model load | **claims × passages.** 6,752 pairs for 72 answers. |
| **Bi-encoder cosine** (`fix_similarity.py`) | $0 API | +0.05 s | shares the same weights | claims + passages (not the product) |
| **Version-locked retrieval** (`fix_retrieval.py`) | $0 | **0 ms** — one `where` clause | 79 MB embedding model, 0.9 s index build, 2 MB index for 48 docs | index size at ingest, not at query |

### The judge is 10× the generation it audits

Generating an answer with Haiku costs ~$0.0042. Auditing it with Sonnet 5 costs
**$0.0412** — and adds 4.1 seconds. Run as a pre-delivery gate on every answer,
as Chapter 3 specifies, the audit dominates the bill and the latency budget.

Three levers, in the order worth trying:

1. **Sample.** 10% of traffic turns $41 into $4.10 per 1,000. You lose the gate
   and keep the monitor — which for many systems is the honest trade.
2. **Cheaper judge.** Haiku judging Haiku costs ~$8 per 1,000, but violates the
   chapter's own rule about self-verification. Judge with a *different* cheap
   model, not the same one.
3. **Gate on the cheap check first.** Run the bi-encoder (+0.05 s, $0) and send
   only the low-scoring answers to the judge. On this corpus that would route
   about a third of answers, cutting the judge bill by two thirds.

Chapter 9's prevention table already argues for exactly this ordering —
cheapest check first, expensive checks only on what the cheap ones could not
explain. Chapter 3 does not carry the same advice, and should.

### The cross-encoder cost is the pair count, not the model

16.5 seconds for 72 answers sounds cheap. It is 6,752 scored pairs — every
claim against every passage. At 10 passages and 5 claims that is 50 pairs per
answer; at 200 passages and 20 claims it is 4,000, and the same fix takes
minutes per answer on CPU.

The lever is chunking, not hardware. Retrieve fewer, larger passages and the
product collapses. A GPU moves the constant; it does not change the shape.

---

## Chapter 5 — per fix

| Fix | Cost per 1,000 documents | Added latency | Setup | Scales with |
|---|---|---|---|---|
| **Capture-verbatim prompt** | ~$3.50 | none — replaces the call | none | document length |
| **`normalise.py`** (deterministic conversion + discard log) | **$0** | <1 ms per field | none | fields per document. Pure regex. |
| **Storing `raw_text` beside the value** | $0 compute | none | none | **storage** — roughly doubles the column width for that field. The only cost, and it is the cheapest insurance in the book. |
| **Unit tests on the normaliser** | $0 | none (CI only) | none | nothing at runtime |
| **Golden-set regression tests** (untested) | $0 API if the golden set is fixed | none at runtime | building the 50+ example set — hours of human time | re-running on every deploy |

Chapter 5's fixes are the cheapest in the book by a wide margin, because the
expensive work was moved out of the model and into code. That is the argument,
priced: **the fix that costs nothing to run is the one you can test.**

---

## Chapter 9 — per fix

| Fix | Cost per 1,000 documents | Added latency | Setup | Scales with |
|---|---|---|---|---|
| **Nullable schema, no defaults** | $0 | none | none | nothing |
| **Sparse-field prompt** | ~$6.50 | none — replaces the call | none | fields requested per document |
| **Quote verification** (RapidFuzz) | $0 | <1 ms per field | 2 MB | quote × document length, bounded by the window |
| **Field-to-section provenance check** | $0 | <1 ms | none — a dict | number of fields. **The fix that worked, and it is free.** |
| **Null-rate monitoring** | $0 | none — runs on the warehouse | a dashboard and a baseline period | rows written |
| **Embedding provenance** (`fix_provenance.py`) | $0 API | +0.03 s per document | 367 MB weights, ~2 s model load | values × chunks |

### The free fix outperformed the expensive one

Field-to-section provenance is a Python dict and an `if`. It took fabrication
from 29% to 0% with no recall cost.

Embedding provenance downloads 367 MB, loads a model, and cannot separate the
two classes at any threshold (best fabrication 0.85, worst real extraction
0.55). At the threshold that catches 86% of fabrications it destroys 61% of
real extractions.

Cost is not the reason to skip it. **It does not work on this failure**, and
knowing which failure you have is what decides.

---

## What to tell a reader deciding what to run

**Always, regardless of scale — all free:**
nullable schemas with no defaults; normalisation in code with a discard log;
storing the raw value; the `status == ACTIVE` retrieval filter; field-to-section
provenance; unit tests.

**Cheap enough not to think about:** the prompt changes. They replace a call you
were making anyway; the only delta is a longer system prompt and a few hundred
extra output tokens.

**Price before you commit:**
- *LLM-as-judge* — the one fix that can cost more than the product it protects.
  Sample it, or gate it behind a cheap check.
- *Cross-encoder scoring* — free per call, but the pair count is quadratic in
  what you feed it. Fix your chunking first.
- *Any embedding fix* — 80–370 MB of weights, a cold-start load, and RAM per
  worker. Fine on one box, an infrastructure decision across fifty.

**The pattern across all three chapters:** the fixes that worked best were the
free ones. Not because cheap is better, but because a check you can write in
code is a check you can test, and a check you can test is a check that still
works after the model changes.
