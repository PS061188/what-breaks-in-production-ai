# What Breaks in Production AI — the experiments

Companion code for *What Breaks in Production AI* by Prachi Sharma.

The book gives nine failure patterns and, for each, a prompt and a set of
engineering fixes. **This repository runs every one of them against real
documents and measures what happens.** Several did not survive it. Those are
marked here and corrected in the book, because a fix that sounds right and does
not work is worth more to you than one more piece of untested advice.

**Replaying costs nothing and needs no API key.** All 5,137 model responses are
recorded and committed.

```bash
git clone https://github.com/PS061188/what-breaks-in-production-ai
cd what-breaks-in-production-ai
python3 run_all.py
```

## Five results worth your next two minutes

**Requiring a source quote does not catch fabrication.** Asked to fill fields
the document does not cover, the model invented values on 11% of them — and
attached a genuine quote to every single fabrication. **4 of 4 passed a
quote-existence check.** It does not invent quotations. It attaches real ones,
lifted from elsewhere in the document, to values it made up.
→ [`ch09-sparse-field-fabrication/`](ch09-sparse-field-fabrication/)

**The stronger model is worse at silent corruption.** Feed a damaged document to
a weaker model and it garbles the answer visibly. Feed it to a better one and it
reconstructs the damage fluently, producing a confident, clean, wrong answer.
Silent corruption rose **39% → 68% → 80%** from Claude Haiku 4.5 to Opus 5 to
GPT-5-mini. Upgrading the model made this failure harder to see, not rarer.
→ [`ch02-input-integrity/`](ch02-input-integrity/)

**A model cannot grade its own confidence.** Across 192 classifications it
returned `LOW` **zero times**, and stamped 80% to 100% of its errors `HIGH`. Any
guardrail of the form "route anything below HIGH to review" has nothing to act
on.
→ [`ch04-classification-cascade/`](ch04-classification-cascade/)

**One clause caused almost the whole prompt effect.** The book blamed soft words
— *relevant, typical, appropriate*. Measured, those are worth about 5 points and
are not statistically significant. The clause *"drawing on standard pharmacology
where the excerpt is thin"* is worth **75**, taking fabrication from 11% to 89%.
The dangerous prompt is not the vague one; it is the one that grants permission.
→ [`ch03-hallucination/`](ch03-hallucination/)

**Eight of fourteen published figures fell outside the range their own code
reproduces.** Nothing here was measured twice until late in the project. When it
was, a reported null turned out to be a real effect, a fix's headline benefit
disappeared against a fair baseline, and one fix turned out to make its target
metric *worse*. That is why [`repeat.py`](repeat.py) exists.
→ [`report/`](report/)

Findings that contradict the book are in **[FINDINGS.md](FINDINGS.md)** rather
than quietly fixed in one place. **[FIX_STATUS.md](FIX_STATUS.md)** rates every
prompt and every fix. **[REVIEW.md](REVIEW.md)** is an adversarial read of the
whole thing. **[report/](report/)** is a 108-page write-up with the corpus,
settings, worked input/output samples, costs and limits for every experiment.

## What actually goes in a prompt

Every prompt template in the book was run against the same documents. Sorted by
**what they ask the model to do**, the results separate completely.

| The instruction asks for | Outcome |
|---|---|
| **A restriction on what may be asserted** — *only from the sources* · *null is a correct answer* · *the document must be marked ACTIVE* · *scan for these four specific signals* | Every large gain here: **at least −81 pts** fabrication, **11% → 0%**, **67% → 17%**, **95% flagged** |
| **A self-assessment** — *rate your confidence* · *set requires_review if unsure* · *count the items then check yourself* | **Nothing, in four chapters.** Lowest grade returned **0 times in 400+ assessments**. 97% of fields graded HIGH, including wrong ones. Self-count wrong **18 of 18** |

A restriction changes what the model may output, and the code reading the response
can enforce it. A self-assessment adds a field and changes nothing else — it is a
claim about a claim, no more reliable than the inner one.

**A prompt can tell you reliably what it noticed. It cannot tell you reliably what
to do about it.** Chapter 2's protocol flagged 95% of damaged documents and refused
to stop on a single one, because the step that stops was conditioned on a
confidence grade the model never issued.

**Let the prompt report. Let your code decide.** Branch on the grade returned as
data; never on the confidence the model assigns itself.

Full template, with the numbers behind each line, in
[`report/`](report/) under *Every prompt in the book, checked*.

## The nine chapters

| chapter | what it measures | result |
|---|---|---|
| [2 — Input integrity](ch02-input-integrity/) | damaged documents stopped before the model runs | **85%** stopped, 37 model calls avoided — but the four checks the book *prescribed* catch **37%** |
| [3 — Hallucination](ch03-hallucination/) | fabrication on questions the sources cannot answer | **at least −81 pts** from the grounding prompt, across 4 models |
| [4 — Classification cascade](ch04-classification-cascade/) | wrong label, and what the pipeline does with it | failure is **rare** (8–9 of 96); the ensemble is *stable*, not just accurate |
| [5 — Extraction quality loss](ch05-extraction-normalisation/) | specificity surviving into storage | auditability **66% → 93%**; qualifiers unchanged; ranges level |
| [6 — State mismatch](ch06-state-mismatch/) | superseded documents reaching the model | status check alone beats the book's six-rule protocol, **17% vs 33%** |
| [7 — Edge input](ch07-edge-input/) | injection, out-of-scope, out-of-distribution | failure is rare but **never zero**; the OOD fix rejects Hindi at cosine 0.995 |
| [8 — Routing and placement](ch08-routing-placement/) | content filed under the wrong field | **did not reproduce** — 0 real errors in 33 |
| [9 — Sparse field fabrication](ch09-sparse-field-fabrication/) | fields the document does not cover | **11% → 0%** with a section constraint |
| [10 — Silent omissions](ch10-silent-omissions/) | items dropped without a signal | rare on numeric lists, **absent** on a 185-item prose enumeration |

Claude Haiku 4.5 is the default; Opus 5, Sonnet 5, GPT-5-mini and GPT-4.1-mini
appear in the cross-model comparisons.

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

Three rules, applied to all nine chapters:

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
lists the strays. It deliberately keeps any recording made under a non-default
model: replaying with default arguments never touches those, so the cross-model
evidence looks orphaned and would otherwise be deleted.

## Honest limits

- **One model family for most of it.** Claude Haiku 4.5 is the default, and the
  cross-model comparisons cover Opus 5, Sonnet 5, GPT-5-mini and GPT-4.1-mini.
  Where a result is single-model, the chapter says so.
- **One domain.** Drug labels are structured, English, and professionally
  edited. A failure that reproduces here may be worse on messier input, not
  better.
- **Small samples.** Usually twelve documents. Enough to show a pattern, not enough to
  put a confidence interval on it.
- **The book's snippets are not copied verbatim.** Chapter 3's fix is written
  in the book with `instructor` + `openai`; here it uses the Anthropic SDK's
  native structured outputs, which enforces the same contract. Each chapter
  README notes where it diverges and why.

## Where the numbers come from

Every figure quoted in the book has an experiment ID. Each one below names what
was measured, what it found, and where the code lives. **IDs are stable; page
numbers are not**, which is why the book cites these rather than a page.

### Experiment 2.1

**Does damaged input change the answer, silently?**  
39% of damaged documents changed the answer with no error raised  
Code: [`ch02-input-integrity/`](ch02-input-integrity/)

### Experiment 2.2

**Does a pure-code gate before the model help?**  
85% of damaged documents stopped, 37 model calls avoided  
Code: [`ch02-input-integrity/`](ch02-input-integrity/)

### Experiment 2.3

**The four pre-flight checks the book prescribes**  
langdetect 0/41, entropy 0/41, token bounds 37%  
Code: [`ch02-input-integrity/`](ch02-input-integrity/)

### Experiment 2.4

**The chapter's prompt template, run**  
flags 95%, aborts 0 of 41, LOW returned 0 of 159  
Code: [`ch02-input-integrity/`](ch02-input-integrity/)

### Experiment 2.5

**Real OCR, and the confidence scores it emits**  
85.5% word accuracy; 0 of 840 lines below confidence 1.000  
Code: [`ch02-input-integrity/`](ch02-input-integrity/)

### Experiment 3.1

**Does prompt wording change the fabrication rate?**  
11% plain, 14% soft words, 89% with a permission clause  
Code: [`ch03-hallucination/`](ch03-hallucination/)

### Experiment 3.2

**Does the grounding template reduce it?**  
at least -81 points, across four models and two providers  
Code: [`ch03-hallucination/`](ch03-hallucination/)

### Experiment 3.3

**The four engineering fixes**  
cross-encoder at 0.3: 85% caught, 12% false alarms  
Code: [`ch03-hallucination/`](ch03-hallucination/)

### Experiment 4.1

**One wrong label, and every step after it**  
LOW never issued in 192 classifications; ensemble is stable, not just accurate  
Code: [`ch04-classification-cascade/`](ch04-classification-cascade/)

### Experiment 5.1

**What does 'extract into clean values' cost?**  
auditability 66%->93%; qualifiers unchanged; ranges level at 5 of 8  
Code: [`ch05-extraction-normalisation/`](ch05-extraction-normalisation/)

### Experiment 5.2

**Normalisation in code, and what it records**  
40 recorded losses, each naming a specific dropped value  
Code: [`ch05-extraction-normalisation/`](ch05-extraction-normalisation/)

### Experiment 6.1

**The answer is right about something no longer true**  
status rule alone 17%, the book's six-rule protocol 33%  
Code: [`ch06-state-mismatch/`](ch06-state-mismatch/)

### Experiment 7.1

**The failure that did not happen, and the fix that harmed**  
Hindi rejected at cosine 0.995; 24 legitimate queries destroyed  
Code: [`ch07-edge-input/`](ch07-edge-input/)

### Experiment 8.1

**Does content end up in the wrong box?**  
0 real placement errors in 33  
Code: [`ch08-routing-placement/`](ch08-routing-placement/)

### Experiment 8.2

**The model's account of its own sourcing**  
wrong section named 3-15% across runs; 97% graded HIGH  
Code: [`ch08-routing-placement/`](ch08-routing-placement/)

### Experiment 9.1

**How often does an empty box get filled?**  
11% of unsupported fields filled anyway  
Code: [`ch09-sparse-field-fabrication/`](ch09-sparse-field-fabrication/)

### Experiment 9.2

**The fix, and the mistake in how it was tested**  
all 4 fabrications carried a real quote  
Code: [`ch09-sparse-field-fabrication/`](ch09-sparse-field-fabrication/)

### Experiment 9.3

**The same fix on a corpus where it can fail**  
0% fabrication, 76% recall  
Code: [`ch09-sparse-field-fabrication/`](ch09-sparse-field-fabrication/)

### Experiment 10.1

**Does the model drop items from a long list?**  
185 of 185 returned in one call; long lists are not where this fails  
Code: [`ch10-silent-omissions/`](ch10-silent-omissions/)

### Experiment 10.2

**Do the chapter's fixes help?**  
independent count works; self-count wrong on 6 of 6  
Code: [`ch10-silent-omissions/`](ch10-silent-omissions/)

### Experiment C.1

**The same failures over deliberately damaged input**  
three of four chapters unchanged; silent omission 0/6 -> 4/7  
Code: [`ch10-silent-omissions/`](ch10-silent-omissions/)

### Experiment R.1

**Every experiment run three times**  
8 of 14 published figures outside their own reproducible range  
Write-up: [`report/`](report/)

### Experiment P.1

**Every prompt in the book, audited and run**  
restrictions produced every gain; self-assessments produced none  
Write-up: [`report/`](report/)

### Experiment X.1

**The same experiments on four models, two providers**  
silent corruption 39% -> 80% as the model gets stronger  
Write-up: [`report/`](report/)

### Experiment G.1

**Is the ground truth actually true?**
12 of 48 "unanswerable" questions were answerable; 4 published rates were too high
Code: [`shared/contamination.py`](shared/contamination.py)

Chapters 3 and 9 derive their ground truth the same way: supply two sections of a
label, ask about six, treat the four withheld sections as unanswerable. That holds
only if the supplied sections say nothing about the withheld topics. On real FDA
labels they sometimes do — Levothyroxine's `dosage_and_administration` section
carries a full paediatric dosing table under its own heading, and the paediatric
question was being scored as unanswerable.

The test is structural: an explicit subsection heading naming the withheld topic,
found inside the supplied text. No model, no reading for meaning. It is
deliberately narrow, so the contaminated set is a floor and the corrections below
are conservative.

| figure | published | corrected |
|---|---|---|
| 3.1 fabrication, plain prompt | 30% (14/48) | **11%** (4/36) |
| 3.1 fabrication, soft vocabulary | 35% | **14%** (5/36) |
| 3.1 fabrication, permission clause | 92% | **89%** (32/36) |
| 3.2 grounding template | −69 pts | **at least −81 pts**, all four models |
| 9.1 fields filled with no source | 29% (14/48) | **11%** (4/37) |

Every correction moves in the same direction: the *baselines* were inflated, so the
gaps the book attributes to prompt design are wider than published, not narrower.

Two chapters were audited and cleared. Chapter 4's `precautions` section nests
`pediatric_use`, `geriatric_use` and `drug_interactions`, so seven passages sit
under two headings at once — but `precautions` is not one of the ten selectable
categories, so it can never be given as an answer. Chapters 8 and 10 have one
ambiguous case each, neither of which could have produced the result reported.

Chapter 5 was a separate defect with the same shape: `RANGE_RE` counted INR target
bands, dosing intervals and time-to-effect as dose ranges, so three of twelve
documents were recorded as containing a dose range they do not contain. On the
corrected denominator the published "the capture prompt preserves fewer ranges"
result disappears — plain and capture prompt both preserve 5 of 8. This one is a
single run and should be re-run before it is relied on.

## Licence

Code: MIT. Data: public domain (US FDA). The book is not.
