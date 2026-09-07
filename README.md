# What Breaks in Production AI — runnable chapters

Companion code for *[What Breaks in Production AI](https://gumroad.com/)* by
Prachi Sharma. Each chapter here is a failure the book describes, reproduced
against real documents, with the book's fix applied and the difference measured.

Three chapters are implemented so far:

| chapter | the number it moves | broken | fixed |
|---|---|---|---|
| [3 — Hallucinations and confident fabrication](ch03-hallucination/) | fabrication rate on questions the sources cannot answer | 90% | **23%** |
| [5 — Extraction and normalisation quality loss](ch05-extraction-normalisation/) | stored values still findable in the source | 64% | **94%** |
| [9 — Sparse field fabrication](ch09-sparse-field-fabrication/) | fabrication rate on fields the document does not cover | 29% | **0%** |

Claude Haiku 4.5, 12 FDA drug labels. Each chapter reports more than one metric
— including the ones that did not move — and [FINDINGS.md](FINDINGS.md) records
four places where running the book's own code showed the book needs a change.

## Run it without an API key

Every run in this repo is recorded. **Replaying costs nothing and needs no API
key.** Most of it needs nothing but the standard library.

Four scripts do real local work and need one package each: the three vector-store
scripts want `chromadb`, and the two embedding scripts want
`sentence-transformers`. If either is missing, that script says so in one line and
`run_all.py` carries on without it — the other results still print. `pip install
-r requirements.txt` gets you everything.

```bash
git clone <this repo> && cd what-breaks-in-production-ai
python3 run_all.py
```

Or one chapter at a time:

```bash
python3 ch09-sparse-field-fabrication/broken.py
python3 ch09-sparse-field-fabrication/fixed.py
```

Each script prints a per-document table and the metric. `broken.py` reproduces
the failure; `fixed.py` applies the chapter's fix to the same inputs.

## Run it live

```bash
pip install -r requirements.txt
cp .env.example .env        # add your Anthropic API key
python3 run_all.py --live    # re-records every fixture
```

A full live re-record of every experiment costs about **$6** at the time of
writing. Each script prints its own token usage and estimated cost when it
finishes, so you can see what a run costs before you scale it up.

## Measure it twice

```bash
python3 repeat.py ch02-input-integrity/broken.py --runs 3
```

`repeat.py` runs a script N times live and prints every headline across runs,
flagging any that moved. **Use it before believing a difference.**

This is not optional advice. Nothing in this repo was measured twice until
August 2026. When it was, four published numbers turned out to be wrong:

- a result reported as "no effect" was a real, consistent 5-point effect that
  one underpowered run could not see
- a fix reported as improving qualifier retention improves nothing once compared
  against a fair baseline
- a fix instructed to preserve dose ranges preserves *fewer* of them than saying
  nothing at all — in all five runs
- an LLM-judge false-alarm rate published at 38% came back 17-25% across four
  fresh runs of an identical configuration

The measured noise floor is roughly **±1-2 cases per 40 samples**, which is wide
enough to swallow several single-run findings. A number without a spread beside
it is a claim about one run.

To try a different model:

```bash
python3 ch03-hallucination/broken.py --live --model claude-opus-5
```

That is worth doing. Some of these failures are much weaker on a stronger
model, and finding out which is more useful than assuming.

## What the data is

`data/labels.json` — FDA drug labels retrieved from the
[openFDA API](https://open.fda.gov/apis/drug/label/). Public domain, real
documents, and sparse in ways nobody arranged: Prednisone's label has no
pediatric-use section, Sertraline's has no pregnancy section. Those gaps are
the ground truth every chapter scores against, which is why there is no
hand-labelled answer key anywhere in this repo.

Refresh or change the corpus:

```bash
python3 fetch_data.py            # re-download
python3 fetch_data.py --show     # which sections each label is missing
```

Labels change over time. Refreshing may change the numbers — the fixtures
record what happened against the corpus you had.

## How the experiments are built

Three rules, applied to all three chapters:

**The broken and fixed scripts return the same JSON schema.** The measured
difference is attributable to the prompt and to the code around the call, not
to one script having somewhere to put a value and the other not.

**Ground truth comes from the corpus, never from annotation.** A question is
unanswerable because the section that would answer it was not supplied. A field
is unsupported because the label does not have that section. There is nothing
to argue with.

**Scoring is deterministic wherever it can be.** String matching, fuzzy quote
verification against the source, unit-tested parsers. The one exception is
Chapter 3, where the baseline returns free text and a second model call
classifies whether an assertion was made — that is a classifier, not a verifier,
and every judgement it made is in `fixtures/` for you to read.

## Layout

```
FINDINGS.md         where running the book contradicted the book
shared/llm.py       model client, fixture cache, cost meter
shared/scoring.py   quote verification and the result tables — no model calls
data/labels.json    the corpus
fetch_data.py       re-download the corpus
run_all.py          every chapter, both variants
repeat.py           run an experiment N times and print the spread
prune_fixtures.py   delete fixtures no script asks for any more
chNN-*/README.md    what that chapter measures and how
chNN-*/broken.py    the failure
chNN-*/fixed.py     the book's fix, applied to the same inputs
chNN-*/fixtures/    recorded responses — every number in this repo is auditable
```

Fixtures are content-addressed on the request, so editing a prompt orphans the
old recording rather than overwriting it. `python3 prune_fixtures.py --dry-run`
lists the strays.

## Honest limits

- **Three chapters, not nine.** The rest are coming.
- **One model family.** Everything is recorded against Claude Haiku 4.5.
  `--model` and `--live` are there so you can check whether the results hold
  elsewhere; nobody has run that sweep for you.
- **One domain.** Drug labels are structured, English, and professionally
  edited. A failure that reproduces here may be worse on messier input, not
  better.
- **Small samples.** Twelve documents. Enough to show a pattern, not enough to
  put a confidence interval on it.
- **The book's snippets are not copied verbatim.** Chapter 3's fix is written
  in the book with `instructor` + `openai`; here it uses the Anthropic SDK's
  native structured outputs, which enforces the same contract. Each chapter
  README notes where it diverges and why.

## Licence

Code: MIT. Data: public domain (US FDA). The book is not.
