# What Breaks in Production AI — the experiments

Companion code for [*What Breaks in Production AI*](https://ps0611.gumroad.com/l/what-breaks-in-production-ai)
by Prachi Sharma ([read Chapter 3 free](https://ps0611.gumroad.com/l/what-breaks-in-production-ai-sample)).

The book gives nine failure patterns and, for each, a prompt and a set of
engineering fixes. **This repository runs every one of them against real
documents and measures what happens.** Several did not survive it. Those are
marked here and corrected in the book, because a fix that sounds right and does
not work is worth more to you than one more piece of untested advice.

**Replaying costs nothing and needs no API key.** All 12,903 model responses
behind the figures are recorded and committed, one file per call, and so are
the 2,125 first recordings of the re-recorded experiments (the `_cli_defaults`
folders).

```bash
git clone https://github.com/PS061188/what-breaks-in-production-ai
cd what-breaks-in-production-ai
python3 run_all.py
```

## Five results worth your next two minutes

**The empty-field failure did not reproduce on drug labels.** Given two sections
of each label and asked to fill six fields, the model filled 1 of the 33 fields
counted as not covered by the supplied text, and it is a correct reading of that
text: **no fabrication in 33**. On the other 32 it wrote "N/A". What the run could
measure is cost: checked over the whole quote, the book's quote-verification rule
kept only **48%** of correct extractions (11 of 23), against all 23 over the first 80 characters.
→ [`ch09-sparse-field-fabrication/`](ch09-sparse-field-fabrication/)

**The stronger model is worse at silent corruption.** Feed a damaged document to
a weaker model and it garbles the answer visibly. Feed it to a better one and it
reconstructs the damage fluently, producing a confident, clean, wrong answer.
Silent corruption rose **39% → 68% → 88%** from Claude Haiku 4.5 to Opus 5 to
GPT-5-mini. Upgrading the model made this failure harder to see, not rarer.
→ [`ch02-input-integrity/`](ch02-input-integrity/)

**A model cannot grade its own confidence.** Across 192 classifications it
returned `LOW` **zero times**, and stamped 10 of its 11 errors `HIGH`. Any
guardrail of the form "route anything below HIGH to review" has nothing to act
on.
→ [`ch04-classification-cascade/`](ch04-classification-cascade/)

**One clause caused almost the whole prompt effect.** The book blamed soft words
— *relevant, typical, appropriate*. On the 32 questions the supplied text does not
cover, those words took fabrication from 1 question to 2. The clause *"drawing on
standard pharmacology where the excerpt is thin"* took it from 2 to **29 of 32**
(6% to 91%). The dangerous prompt is the one that grants permission.
→ [`ch03-hallucination/`](ch03-hallucination/)

**Six of fourteen published figures fell outside the range their own code
reproduces, and two more may have.** Nothing here was measured twice until late in the project. When it
was, a result reported as "no effect" pointed the same way in four runs of five,
and a fix's headline benefit disappeared against a fair baseline. That is why [`repeat.py`](repeat.py) exists.
→ [`report/`](report/)

Findings that contradict the book are in **[FINDINGS.md](FINDINGS.md)** rather
than quietly fixed in one place. **[FIX_STATUS.md](FIX_STATUS.md)** rates every
prompt and every fix. **[REVIEW.md](REVIEW.md)** is an adversarial read of the
whole thing. **[report/](report/)** is a 149-page write-up with the corpus,
settings, worked input/output samples, costs and limits for every experiment.

## What actually goes in a prompt

Every prompt template in the book was run against the same documents. Sorted by
**what they ask the model to do**, the results separate completely.

| The instruction asks for | Outcome |
|---|---|
| **A restriction on what may be asserted** — *only from the sources* · *the document must be marked ACTIVE* · *scan for these four specific signals* | Every large gain here: **at least −91 pts** fabrication, **67% → 17%**, **95% flagged** |
| **A self-assessment** — *rate your confidence* · *set requires_review if unsure* · *count the items then check yourself* | **Little, in four chapters.** Lowest grade returned **0 times in 400+ assessments** of damaged or mislabelled inputs; it appeared only when Chapter 2 made the damage extreme. On role-played clinical notes, **7 in 10 misplaced sentences graded HIGH**. A self-count was **its own list's length in 54 of 54** calls |

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
| [3 — Hallucination](ch03-hallucination/) | fabrication on questions the sources cannot answer | **at least −91 pts** from the grounding prompt, across 4 models |
| [4 — Classification cascade](ch04-classification-cascade/) | wrong label, and what the pipeline does with it | failure is **rare** (10 of 96 on body text); 10 of the 11 errors graded `HIGH` |
| [5 — Extraction quality loss](ch05-extraction-normalisation/) | specificity surviving into storage | auditability **64% → 93%**; qualifiers unchanged; ranges level |
| [6 — State mismatch](ch06-state-mismatch/) | superseded documents reaching the model | status check alone does better than the book's six-rule protocol, **17% vs 30%** |
| [7 — Edge input](ch07-edge-input/) | injection, out-of-scope, out-of-distribution | **no injection obeyed**, even with no defence; the OOD fix rejects Hindi at cosine 0.995 |
| [8 — Routing and placement](ch08-routing-placement/) | content filed under the wrong field | **did not reproduce on drug labels** (0 real errors in 33); 18% of sentences misfiled on role-played clinical notes |
| [9 — Sparse field fabrication](ch09-sparse-field-fabrication/) | fields the document does not cover | **did not reproduce** — 0 of 33; the section check rejected 5 correct children's doses |
| [10 — Silent omissions](ch10-silent-omissions/) | items dropped without a signal | rare on numeric lists, **absent** on a 185-item prose enumeration |

Claude Haiku 4.5 is the default; Opus 5, Sonnet 5, GPT-5-mini and GPT-4.1-mini
appear in the cross-model comparisons.

## Run it without an API key

Every run in this repo is recorded. **Replaying costs nothing and needs no API
key.** Most of it needs nothing but the standard library.

A few scripts do real local work and need one package: the vector-store scripts
want `chromadb`, the embedding scripts want `sentence-transformers`, and Chapter
2's `book_checks.py` wants `langdetect` and `tiktoken`. Four probes in Chapters 9
and 10 need their own environments (spaCy taggers and the Guardrails validator);
the install notes are at the top of each script. If anything is missing, the
script says what in one line, `run_all.py` prints it as skipped, and the other
results still print.

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
August 2026. When it was, three published numbers turned out to be wrong:

- a result reported as "no effect" pointed the same way in 4 of 5 runs (about 5
  points, on 48 questions before the ground-truth audit), which one underpowered
  run could not see
- a fix reported as improving qualifier retention improves nothing once compared
  against a fair baseline
- an LLM-judge false-alarm rate published at 38% came back 17-25% across four
  fresh runs of an identical configuration

The measured noise floor is roughly **±1-2 cases per 40 samples**, which is
large enough that several single-run findings fall inside it. A number without a
spread beside it is a claim about one run.

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
pediatric-use section, Sertraline's has no pregnancy section. Chapters 3 and 9
do not score against those gaps. They give the model two sections of each label,
and a question counts as unanswerable when the section that would answer it was
not supplied. Most labels do carry the withheld sections (pediatric use in 8 of
12, pregnancy in 7 of 12), so these two chapters measure answers that go beyond
the supplied text, and a model that answers may be recalling the real label.
Either way the ground truth comes from the labels themselves, which is why there
is no hand-labelled answer key anywhere in this repo.

`data/aci_bench_notes.json` — 60 reference visit notes from
[ACI-Bench](https://github.com/wyim/aci-bench) (Yim et al., *Nature Scientific
Data*, 2023; CC BY 4.0), twenty from each of its three subsets. Role-played or
constructed encounters, not real patients; the notes were checked and rewritten
by medical scribes or physicians. Used by Chapter 8's Experiment 8.6, the only
experiment in the book on a document whose sections are decided by convention
rather than by wording. The file records the selection rule.

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
data/aci_bench_notes.json   60 ACI-Bench clinical notes (Chapter 8, Experiment 8.6)
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

- **One recorded answer per request.** Where a figure is a spread across live runs
  made with `repeat.py` (Chapter 2, 6.1, Chapter 7, 8.1–8.2, the Chapter 3 judge's
  four runs, C.1 and R.1), only the last run replays; spreads drawn with a sample
  index, and every subscription-CLI experiment, replay in full. LLM Guard's timings
  depend on the machine (`probe_llmguard.py --timings`, last run in
  `llmguard_timings_log.txt`). Experiments 9.5 (the Guardrails validator,
  `guardrails_sweep_log.txt`) and 10.4 (spaCy `en_core_web_trf`), and the Instructor
  run in 8.7 (`probe_instructor.py`, which replays without a key), need their own
  environments, described at the top of their scripts.
- **Every model at its API default.** Experiments that call Claude through the Claude Code CLI on a subscription set the model's API default ([`shared/cli_defaults.py`](shared/cli_defaults.py)): Claude Haiku 4.5 without thinking, Claude Sonnet 5 with its default adaptive thinking at effort high. The CLI's own default lets Haiku think first; the first recordings of 2.7, 9.4–9.7 and Chapter 10's conversation and audit experiments were made that way, found on 14 Nov 2026 (FINDINGS.md), and re-recorded the same day. The first recordings are kept in the `*_cli_defaults/` folders and replay with `CLI_SETTINGS=cli`, so the effect of thinking on these tasks can be read side by side.
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

### Experiment 2.6

**Does cutting at a sentence or heading boundary prevent truncation damage?**  
A cut at a fixed character count asserted a dose the excerpt did not contain in 2 of 39 answers; a cut that backed off to the last sentence or heading boundary did so in 0 of 39 (36 distinct excerpts; several budgets land on the same boundary). Every measured failure was a cut inside a numeric range or a table row. A mechanism, not an established rate (FINDINGS 13)  
Code: [`ch06-state-mismatch/common.py`](ch06-state-mismatch/common.py) (`naive_cut` / `boundary_cut`; kept beside Chapter 6's context tooling, taught in Chapter 2's prompt section)

### Experiment 2.7

**Prompt 2-1 exactly as printed: report the damage, never abort**
The printed report-only prompt (prompt_2_1.txt) on the same 53 documents, three runs on Claude Haiku 4.5 through the subscription CLI at the API's default setting (no thinking): graded 39 of the 41 damaged documents not CLEAN in every run (the misses the truncated Atorvastatin and Omeprazole copies each time), 12 of 12 OCR-damaged in every run. It flagged 2 of the 12 clean controls in every run, each a real defect in the label text (Amoxicillin's zero-width spaces, Gabapentin's "ADMlNlSTRATION"), passed a third (Metformin's "1.73 m 2") and raised no false alarm in 36 clean readings. SEVERELY_CORRUPTED issued 1, 2 and 1 times, each on a truncated copy cut off inside the dosing passage (Metformin every run, Furosemide once)
Code: [`ch02-input-integrity/probe_prompt21.py`](ch02-input-integrity/probe_prompt21.py) · 159 calls through the subscription CLI, recorded in `fixtures_prompt21/`

### Experiment 3.1

**Does prompt wording change the fabrication rate?**  
3% plain (1 of 32), 6% soft words (2 of 32), 91% with a permission clause (29 of 32)  
Code: [`ch03-hallucination/`](ch03-hallucination/)

### Experiment 3.2

**Does the grounding template reduce it?**  
at least -91 points, across four models and two providers; 0 of 32 fabricated on every model  
Code: [`ch03-hallucination/`](ch03-hallucination/)

### Experiment 3.3

**The four engineering fixes**  
cross-encoder at 0.3: 29 of 29 caught, 3 of 24 false alarms; the judge, in its kept run: 29 of 29 caught, 6 of 24 false alarms  
Code: [`ch03-hallucination/`](ch03-hallucination/)

### Experiment 3.4

**Does asking the same question five times expose fabrication?**
flags the 2 of 32 unanswerable questions a single draw called safe; none fabricated on every draw (the one counted before, Sertraline, is a correct reading)
Code: [`ch03-hallucination/probe_selfconsistency.py`](ch03-hallucination/probe_selfconsistency.py)

### Experiment 3.5

**Do the model's own token probabilities separate invented answers from real ones?**
fabricated −0.40 / −0.34 vs correct −0.10 / −0.08 on GPT-4.1-mini, in runs 3 and 4 (the answers of runs 1 and 2 were overwritten); a cut at −0.20 / −0.18 catches 11 of 11 and 7 of 7 fabrications, flags 3 of 24 correct answers each time — and 16 of 21 and 17 of 25 correct refusals. Not measurable on Claude: the API returns no token probabilities
Code: [`ch03-hallucination/probe_logprobs.py`](ch03-hallucination/probe_logprobs.py)

### Experiment 4.1

**One wrong label, and every step after it**  
LOW never issued in 192 classifications; 10 of the 11 errors graded `HIGH`  
Code: [`ch04-classification-cascade/`](ch04-classification-cascade/)

### Experiment 4.2

**Three different systems voting, not three prompts**  
Haiku 4.5 (shipped template), GPT-4.1-mini (one-line prompt) and bart-large-mnli zero-shot, majority vote: matched the best member (99/99/98 of 96 opening, 96/96/94 of 96 body) and all-three-disagree sent 1-2 of 96 to review (bart scores the category descriptions, the script's default; `ZS_LABELS=names` scores bare section names instead, 41%)  
Code: [`ch04-classification-cascade/model_ensemble.py`](ch04-classification-cascade/model_ensemble.py)

### Experiment 5.1

**What does 'extract into clean values' cost?**  
auditability 64%->93%; qualifiers unchanged; ranges level at 5 of 8  
Code: [`ch05-extraction-normalisation/`](ch05-extraction-normalisation/)

### Experiment 5.2

**Normalisation in code, and what it records**  
40 recorded losses, each naming a specific dropped value  
Code: [`ch05-extraction-normalisation/`](ch05-extraction-normalisation/)

### Experiment 5.3

**Retries, and a model swap, on the captured values**  
117 of 376 values unparseable, retries fixed 8; Sonnet 5 and GPT-4.1-mini store Haiku's value on 54% and 65% of fields  
Code: [`ch05-extraction-normalisation/`](ch05-extraction-normalisation/)

### Experiment 6.1

**The answer is right about something no longer true**  
status rule alone 17%, the book's six-rule protocol 30%  
Code: [`ch06-state-mismatch/`](ch06-state-mismatch/)

### Experiment 6.2

**Does the context-integrity block do anything?**  
wrong-drug dose used 0/30 with or without it; conflict reported 30/30 either way (the schema has a field for it); the block turns "both doses" into "no dose" in 22/30; correction in conversation used 27/30 → 30/30  
Code: [`ch06-state-mismatch/fix_integrity.py`](ch06-state-mismatch/fix_integrity.py)

### Experiment 6.3

**Can a prompt cope with no status field at all?**  
"newest wins" rule vs neutral, headers carry a date only: superseded label used 20/30 in both arms (4,4,4,4,4); 15/15 where the current label was not retrieved; the one retrieved-and-wrong drug's newest label has no starting dose, so the model used the older one that did; "relied on newest" 9/30 → 25/30 changed what it reported, not what it answered  
Code: [`ch06-state-mismatch/fix_nostatus.py`](ch06-state-mismatch/fix_nostatus.py)

### Experiment 6.4

**The freshness monitor the book recommends instead of top-k overlap**  
newest last_verified among top-3: catches 32/40 new-label weeks (overlap monitor: 20/40), 0/1,381 false alarms; but as a stall alarm it fires 35, 24, 19 and 6 times in healthy operation at 4-, 13-, 26- and 52-week windows — healthy gaps between advances run 1 to 274 weeks, median 24  
Code: [`ch06-state-mismatch/fix_monitoring_date.py`](ch06-state-mismatch/fix_monitoring_date.py)

### Experiment 6.5

**Scenario 3: the world moved inside the model**  
memory alone disagreed with the current label for 2 of 6 drugs every run (Prednisone, Sertraline); with the current label in context, 0/30 answers stated a dose the label does not; with a label whose doses had been changed by code, the document won 18/30, memory won 0/30, 6 withheld, 6 undecidable (doubled dose equals a real one)  
Code: [`ch06-state-mismatch/fix_memory.py`](ch06-state-mismatch/fix_memory.py)

### Experiment 6.6

**Scenario 2, the model's half: reconciling a draft with a record that changed**  
draft from the original label, finalised against a label with every dose doubled: told of the change, new dose only 28/30, stale 0/30; not told, 25/30, stale 0/30, 3 withheld; "noted a change" 30/30 either way (schema field). Everything depends on the re-read having happened  
Code: [`ch06-state-mismatch/fix_reconcile.py`](ch06-state-mismatch/fix_reconcile.py)

### Experiment 6.7

**Retrieval fetched the wrong document: BM25 over the twelve labels' 123 sections**  
72 named queries (Chapter 3's six questions x 12 drugs): top-1 chunk from the wrong drug's label 9/72 on section chunks, 25/72 on 800-character fixed chunks (all 25 winning chunks lack the asked drug's name); drug name replaced by "this medicine" (the follow-up-turn form): 66/72 wrong, right label in the top 3 only 16/72. Deterministic, no model call, no fixtures.  
Code: [`ch06-state-mismatch/probe_retrieval.py`](ch06-state-mismatch/probe_retrieval.py)

### Experiment 7.1

**The failure that did not happen, and the fix that harmed**  
Hindi rejected at cosine 0.995; 24 legitimate queries destroyed  
Code: [`ch07-edge-input/`](ch07-edge-input/)

### Experiment 7.2

**Does a ready-made scanner model beat eight lines of regex?**  
LLM Guard: 37/48 attempts flagged in default mode, 48/48 in chunk mode, incl. all 12 Spanish the regex missed — and all 12 Hindi questions flagged as attacks at risk 1.00  
Code: [`ch07-edge-input/probe_llmguard.py`](ch07-edge-input/probe_llmguard.py)

### Experiment 8.1

**Does content end up in the wrong box?**  
0 real placement errors in 33  
Code: [`ch08-routing-placement/`](ch08-routing-placement/)

### Experiment 8.2

**The model's account of its own placement**  
97% of fields graded HIGH in every run, LOW never issued, `requires_review` set on 0 of 11 records; an earlier "wrong section named 3–15%" figure came from abbreviated section names and the 80-character locator, and is withdrawn  
Code: [`ch08-routing-placement/`](ch08-routing-placement/)

### Experiment 8.3

**Does the placement check catch misplacement when it is planted?**  
65 of 66 planted swaps caught as shipped, 1 false rejection of 33 untouched boxes; 66/66 at a 200-char locator, 4 false  
Code: [`ch08-routing-placement/probe_planted.py`](ch08-routing-placement/probe_planted.py)

### Experiment 8.4

**Does the failure appear when the headings are removed and the sentences shuffled?**  
No: 0 real misplacements of 33, three draws each, plain prompt and Prompt 8-1 alike; the scorer's flags are the boilerplate artefact and joined quotes it cannot find  
Code: [`ch08-routing-placement/probe_hardcorpus.py`](ch08-routing-placement/probe_hardcorpus.py) · demonstration of the record: [`demo_provenance.py`](ch08-routing-placement/demo_provenance.py)

### Experiment 8.5

**Generated shipping documents: does the prompt prevent misplacement when the labels vary, then vanish?**  
With any label or an order line, 0 misplaced of 108 fields a level for every prompt (an earlier "empty fields" claim was a company-only scorer artefact, withdrawn); with no labels and no line, both prompts assumed sender-first and swapped origin and destination on every reversed document — plain 12, 12, 12 of 36 a run, Prompt 8-1 12, 15, 11 with null on only 4, 2, 5; the graded prompt marked 104 of 108 unlabelled fields MEDIUM or LOW and flagged all 36 records; asked per field whether the document states the role, the model said "not stated" on all 108 unlabelled fields (and on 29 others, all correct, 26 of them on documents where only an order line named the roles) while still filling them  
Code: [`ch08-routing-placement/probe_convention.py`](ch08-routing-placement/probe_convention.py)

### Experiment 8.6

**Placement on role-played clinical notes (ACI-Bench): does the failure appear when sections are decided by convention?**  
Yes — of 2,070 sentences from 60 ACI-Bench notes, headings removed and shuffled, 375 / 366 / 381 filed under a different heading from the author's by words alone (18%), 286 / 268 / 256 with section definitions, 1 / 0 / 1 with each sentence's section tag kept; the rate ran 8.8% to 27.7% across the benchmark's three note styles; the confidence grade carried signal (error rate 10% HIGH → 39% MEDIUM → 63% LOW) but 7 in 10 misplaced sentences were graded HIGH  
Code: [`ch08-routing-placement/probe_clinical.py`](ch08-routing-placement/probe_clinical.py) · corpus: [`data/aci_bench_notes.json`](data/aci_bench_notes.json)

### Experiment 8.7

**What does a strict output schema actually guarantee?**  
On 60 clinical notes with the plain prompt: no schema — 0 invented keys, 0 unknown IDs, 2 duplicates, 8 sentences dropped; schema enforced — 0, 0, 3, 33; schema plus a Pydantic validator (every sentence exactly once) with one re-ask — 0, 0, 0, 0, at 13 re-asks in 60; misplacement unchanged at 376 / 375 / 383 of 2,070  
Instructor 1.17 itself, the same validator, first ten notes, subscription CLI (schema written into the prompt, not enforced): 9 of 10 valid after 16 calls; the tenth wrote each sentence's text after its ID in all three replies, and its filing was complete once that text was removed  
Code: [`ch08-routing-placement/probe_schema.py`](ch08-routing-placement/probe_schema.py), [`probe_instructor.py`](ch08-routing-placement/probe_instructor.py)

### Experiment 9.1

**How often does an empty box get filled?**  
0 of 33 — the one filled field was a correct reading of the supplied text; the failure did not reproduce  
Code: [`ch09-sparse-field-fabrication/`](ch09-sparse-field-fabrication/)

### Experiment 9.2

**The fix, and the mistake in how it was tested**  
the first check was the answer key: its 0% was arithmetic  
Code: [`ch09-sparse-field-fabrication/`](ch09-sparse-field-fabrication/)

### Experiment 9.3

**The same check with four sections supplied**  
fabrication still forced to zero; the rule rejected 5 correct children's doses  
Code: [`ch09-sparse-field-fabrication/`](ch09-sparse-field-fabrication/)

### Experiment 9.4

**A note written from a conversation: does a heading template invent what nobody said?**  
On 60 ACI-Bench conversations, Claude Haiku 4.5 via the subscription CLI at the API's default setting (no thinking), three runs: a template prompt filled 9, 3 and 1 of the 201 entries per run whose topic the conversation never raised — "No known drug allergies" in 2, 1 and 1 of 58 notes (the conversations raised only seasonal allergies), tobacco denials in 4, 1, 0 of 53 and alcohol denials in 3, 1, 0 of 49 ("Denies tobacco, alcohol, and illicit drug use"); with the rule "write 'Not discussed.'" 0, 0, 0; family history (41) never filled under either prompt; every counted case read against its conversation. The first recording, with Claude Code's default thinking on, gave 4, 3, 4 allergy claims and 0, 1, 0 tobacco denials (fixtures_conversation_cli_defaults/)  
Code: [`ch09-sparse-field-fabrication/probe_conversation.py`](ch09-sparse-field-fabrication/probe_conversation.py) · corpus: [`data/aci_bench_dialogues.json`](data/aci_bench_dialogues.json)

### Experiment 9.5

**Do the chapter's checks catch real invented entries?**  
On Experiment 9.4's notes at the API's default setting, 13 invented entries and 83 on discussed topics: a keyword topic search caught 9 of 13 (3 false flags, the steroid-reaction entries); an embedding check 9 of 13 at similarity 0.3 with 0 flagged (the four misses the four "No known drug allergies"), 13 of 13 only at 0.6 with 46 flagged; Claude Sonnet 5 shown the conversation 13 of 13 (11 flags on discussed entries, 7 of them real errors, read one by one), and Claude Haiku 4.5, the model that wrote the notes, also 13 of 13 (1 flag, a real error); Sonnet 5 shown only the note caught 9 of 13 and flagged 55 of 83. Extended to Experiment 9.6's record values (`--source schema`, 20 invented, 55 discussed): Sonnet 5 and the writer each caught 18 of 20, each passing two different D2N088 seasonal-denial records — combined over 33 invented entries, 31 for each model: on this test the checking model made no difference. The packaged Guardrails ProvenanceEmbeddings validator over the identical entries: as shipped (distance 0.8, five-sentence source windows) it caught 7 of 13 and flagged 15 of 83, every one of the 15 from a transcript the sentence splitter could not divide (19 of 60 have no full stops to split at); no threshold separated the groups (the loosest that caught all 13 still flagged 60 of 83 with one-sentence windows); it also crashes on single-chunk sources, needs punkt_tab its setup does not fetch, and phones telemetry home unless switched off (the probe switches it off). First recording, thinking on (12 and 7 invented): Sonnet 17 of 19, the writer 14 of 19, approving 5 of its 8 generalisations; Guardrails 2 of 12 as shipped, 72 of 89 at the loosest catch-all  
Code: [`ch09-sparse-field-fabrication/probe_checks.py`](ch09-sparse-field-fabrication/probe_checks.py) · [`probe_guardrails.py`](ch09-sparse-field-fabrication/probe_guardrails.py) (runs in its own environment; install line in the docstring)

### Experiment 9.6

**Do the schema fix and the quote check work where the model invents?**  
Four optional topics as a JSON record over Experiment 9.4's 60 conversations, two conditions × three runs (360 CLI replies at the API's default setting, no thinking): with every value required, the model stored a silence filler in 565 of 603 no-source fields and invented in 19, most a negative such as "No tobacco use reported" whose own quote said only that the topic never came up; allowed null, 0 fillers and 1 invention. The quote check caught 16 of the 20 inventions (the meta-quotes appear nowhere in the conversation), passed 4 whose real quotes are about something else (three the seasonal-allergy denial), nulled 584 of 595 required-mode fillers, and rejected 18 of 106 and 10 of 94 values that state something: read one by one, 19 correct values wrongly rejected (most a question and its answer joined into one quote), 7 values the conversation does not support, 2 a sick sister filed as family history. First recording, thinking on: 577 fillers, 5 and 2 inventions, 1 of 7 caught, 7 of 97 and 3 of 92 rejected  
Code: [`ch09-sparse-field-fabrication/probe_schema.py`](ch09-sparse-field-fabrication/probe_schema.py)

### Experiment 9.7

**Does a list of quotes fix the quote check's false alarms?**  
Same sixty ACI-Bench conversations, fields optional, `source_quotes` a list with one item per place in the conversation, three runs at the API's default setting: rejections of discussed-topic values fell from 7 of 75 with 9.6's single quote (six of them correct values) to 1 of 80 (a question and its answer put in one item); no invented value in 603 no-source fields; 47 of 102 non-null values carried two or more quotes, and the steroid value 9.6 rejected passes in every run. Counted with the same filter, the list did not make the model hold back (80 values on discussed topics against 75); the first recording's "92 against 75" compared different filters (same filter: 76 against 75). Existence is still not support: a correct value backed by "yeah i think so" passes in every run  
Code: [`ch09-sparse-field-fabrication/probe_schema_list.py`](ch09-sparse-field-fabrication/probe_schema_list.py)

### Experiment 10.1

**Does the model drop items from a long list?**  
185 of 185 returned in one call; long lists are not where this fails  
Code: [`ch10-silent-omissions/`](ch10-silent-omissions/)

### Experiment 10.2

**Do the chapter's fixes help?**  
the independent count caught the one real gap (Amoxicillin's 200 mg and 400 mg); the model's own count of the source is not a count of the source (Experiment 10.3)  
Code: [`ch10-silent-omissions/`](ch10-silent-omissions/)

### Experiment 10.3

**Can the model count its own source, and does the inventory protocol help?**  
Claude Haiku 4.5 at its API default (thinking off) via the subscription CLI, six labels, three runs of each instruction: asked to count the dose amounts and check its list against the count, the model's count equalled the number of items it listed in 46 of 54 calls (one-line instruction as printed 15 of 18, the same with the count defined as distinct amounts 18 of 18, the chapter's inventory protocol 13 of 18); the other 8 differed by 1 to 7 items and none sat on a list that had lost a dose of its own drug, so the check still cannot find a gap; figures returned 93%, 93%, 81% with the protocol against 100% in every run for the one-line instruction; the protocol's self-check flagged none of the short lists and 4 of 12 complete ones, each warning about items it judged were not doses or its own miscount. The reference count skips a lab value (serum creatinine 3 mg/dL). The first recording, made with Claude Code's default thinking, replays with `CLI_SETTINGS=cli` (54 of 54; 83%, 83%, 100% against 98% × 3)  
Code: [`ch10-silent-omissions/probe_count.py`](ch10-silent-omissions/probe_count.py) · [`probe_protocol.py`](ch10-silent-omissions/probe_protocol.py)

### Experiment 10.4

**Can a general named-entity model supply the independent count?**  
en_core_web_trf (the model the chapter names) has no dose type: used as printed, against the 60 recorded extractions of Experiment 10.3 at the API default (9 really short, 4 short only by another drug's dose, 47 complete), it flags 4 of the 9 real drops, all on Amoxicillin, the one document where its entity count equals a complete list, and 10 of the 47 complete runs, all one lab value (Lisinopril's serum creatinine 3 mg/dL); it finds no doses in either dosing table, so the Gabapentin, Levothyroxine and Warfarin drops go unflagged; the small model flags nothing; the repo's pattern count, same rule, flags 4 of 9 with no false flag, 5 of 9 compared figure by figure. Run 15 Nov 2026 with spaCy 3.8.7 and en_core_web_trf 3.8.0 on CPU; output in [`ner_trf_out.txt`](ch10-silent-omissions/ner_trf_out.txt). First recording: 4 of 4 real drops, 10 of 50 complete runs flagged  
Code: [`ch10-silent-omissions/probe_ner.py`](ch10-silent-omissions/probe_ner.py) · needs its own spaCy environment (install line in the docstring)

### Experiment 10.5

**Does a long conversation's dose survive into the note?**  
On Experiment 9.4's 360 recorded ACI-Bench notes, 63 of the 64 unique dose facts stated across 39 conversations reached every one of their notes, attached to the right drug; the 64th, a vitamin D dose the doctor corrected mid-sentence, rightly reached none, because every note carries the corrected dose (396 proximity checks, 7 failures: that dose in all six notes, and one a correct attachment whose drug name sits a sentence away: "dose increase to 175 milligrams"); uncertain doses were flagged, not invented. A null at this length and fact type; the chapter's real-world rate rests on the outside studies  
Code: [`ch10-silent-omissions/exp105_dialogue_doses/`](ch10-silent-omissions/exp105_dialogue_doses/) · no model calls, replays Experiment 9.4's notes

### Experiment 10.6

**Does a "what is missing?" audit in a second call catch known omissions?**  
The chapter's completeness-audit fix, run once over all 60 recorded extractions of Experiment 10.3 (11 short by a known set of figures, 49 complete), Claude Haiku 4.5 at its API default (thinking off). It named 27 of 31 known-missing figures and every figure in 8 of the 11 short extractions, including all 9 on the extraction that dropped the most; it missed the methylene-blue dose in 2 of the 3 extractions that dropped it, and 2 tablet strengths in one. It raised alarms on 17 of 49 complete extractions: real source content outside the dose task (water volumes, weight bands, INR targets, intervals) or doses the extraction already carried in other words, plus one real drop the pattern count cannot see (Gabapentin's 1,400 mg/day); no invented figure. On the 6 API extractions, whose input did not change, the first recording (Claude Code's default thinking, `CLI_SETTINGS=cli`) named 2 of 11 missing figures; this one names 11 of 11 (first recording overall: 10 of 41)  
Code: [`ch10-silent-omissions/probe_audit.py`](ch10-silent-omissions/probe_audit.py) · 60 Haiku 4.5 calls through the subscription CLI, $0.41 notional (first recording: $2.04) · every case in [`audit_log.txt`](ch10-silent-omissions/audit_log.txt)

### Experiment 10.7

**What does the `not_extracted` field hold on text whose items are not delimited?**  
Prompt 10-1 as printed, item type "medication dose amount", three runs over the 60 ACI-Bench conversations, Claude Haiku 4.5 at its API default (thinking off). The extraction returned 63 of the 64 stated doses in every run; the one left out is a dose the doctor retracted mid-sentence. But the extracted list also carried 72, 77 and 74 medicine names with no amount and 16, 23 and 19 frequency-only items per run. The field filled on 56, 57 and 59 of 60 conversations (19, 19 and 20 of the 21 with no dose) with 177, 190 and 169 entries: 93, 111 and 91 numbers that are not doses (lab values, vitals, weights, durations), 59, 48 and 51 medicines named without an amount, the rest frequencies and amounts the ruler cannot see. No entry held back a dose the extraction should have carried. One added line ("Do not list items that simply have no amount. List only values that could be mistaken for a medication dose amount."), run three more times (`--condition narrowed`), made the field longer: 210, 226 and 203 entries on 53, 57 and 55 conversations, every number in the conversation listed, medicine names without an amount still 52, 48 and 46. The first recording, made with Claude Code's default thinking (`CLI_SETTINGS=cli`), had 137 to 149 entries and the line cut them to 57 to 62: the line's effect depends on the model setting  
Code: [`ch10-silent-omissions/probe_field_conversation.py`](ch10-silent-omissions/probe_field_conversation.py) · 360 Haiku 4.5 calls through the subscription CLI, $8.12 notional · every entry in [`field_conversation_log.txt`](ch10-silent-omissions/field_conversation_log.txt) and [`field_conversation_narrowed_log.txt`](ch10-silent-omissions/field_conversation_narrowed_log.txt)

### Experiment 10.8

**Does a tagger with a dose label remove the domain work?**  
Med7 (`en_core_med7_lg`, STRENGTH/DOSAGE) and `blaze999/Medical-NER` (DeBERTa, DOSAGE) over the same six dosing sections and 60 recorded extractions as 10.4 (9 really short, 4 short only by another drug's dose, 47 complete): 0 false alarms on the 47 complete for each, but neither labels doses written per kg, per day or as paired suspension strengths (Med7 saw 1 of Levothyroxine's 11 doses, DeBERTa 3 of 11 and 2 of Warfarin's 6), so Med7 caught 3 of the 9 real drops and DeBERTa 1, each only where an Amoxicillin list fell below its small count. The repo's pattern count, same rule, caught 4 of 9; compared figure by figure instead of by count, 5 of 9; the 4 Gabapentin drops are a table cell no counter here can see. A tagger's count flags only the loss of what it counts. Amazon Comprehend Medical not run: no AWS account  
Code: [`ch10-silent-omissions/probe_ner_dose.py`](ch10-silent-omissions/probe_ner_dose.py) · own environment `.venv-med` (spaCy 3.4 + transformers; install lines in the docstring) · no model calls · outputs in `ner_dose_med7_out.txt`, `ner_dose_deberta_out.txt`

### Experiment 10.9

**What do the fixes do on output that cannot be counted?**  
The four fixes against Experiment 9.4's 360 recorded clinic notes (prose output from the 60 ACI-Bench conversations), notes and audit recorded at the API's default setting (no thinking). Fix 1 (Med7 drug-name count, dialogue vs note): 208 of 360 notes flagged, every flag read, none a medicine in use left out of the note: 110 flags are the tagger misreading conversation (first names and filler words tagged as drugs), 68 name drugs the note carries (24 renamed, Tylenol to acetaminophen), the rest are medicines declined, only asked about or not taken, past treatments and alternatives, and one note that leaves out a list change (clindamycin removed) the other five record. Fix 2: does not run (no list, no length). Fix 3 (audit, 60 CLI calls, $0.48 notional): 223 claims across 57 of 60 notes, 2 replies unparsable; read one by one, 84 name content the note already carries, 30 content the conversation never states (sections nobody discussed, vital signs read off a screen, medicines never named), 99 editorial or trivial content; 3 are real omissions that matter (oxybutynin, a medicine in use, missing from the note, invisible to the drug-name count because the transcript spells it "oxyglutinine"; the patient's negative suicide/homicide screen; a gynecomastia concern the doctor named) and 7 point at errors written into the note (wrong hand, a sleep habit reversed, an ointment strength nobody stated, an age of 18 for a 7th-grader, "right flank bilaterally", 80% of glucose checks recorded as 80% of readings in range, Eliquis beside "denies blood thinners"). Fix 4: no answer schema to hold the field. On prose only the audit still runs: a reading feed, worth sampling because a few claims find real omissions and errors. First recording, Claude Code's default thinking on (fixtures_note_audit_cli_defaults/): 188 flags; 91 audit claims across 45 notes, among them the same oxybutynin and gynecomastia omissions, filed then as editorial  
Code: [`ch10-silent-omissions/probe_note_count.py`](ch10-silent-omissions/probe_note_count.py) (local, `.venv-med`) · [`ch10-silent-omissions/probe_note_audit.py`](ch10-silent-omissions/probe_note_audit.py) · logs [`note_count_out.txt`](ch10-silent-omissions/note_count_out.txt), [`note_audit_log.txt`](ch10-silent-omissions/note_audit_log.txt)

### Experiment 10.10

**Do the field's entries trace back to the source?**  
Fix 4's deterministic half: code verification of every string in Experiment 10.7's 360 recorded replies (2,285 extracted items + field entries) against their dialogues, with the matcher that knows the transcripts' spoken numbers. 2,228 traced; the 57 alarms, all read, are the checker's blindness: 36 items written as data objects instead of strings, 10 values with a note in brackets, 4 blood pressures spoken in words, 4 entries describing an ambiguity, 3 "aspirin" where the transcript spells "asprin". Zero invented values and, at this setting, no corrupted value to catch. The first recording (`CLI_SETTINGS=cli`): 1,188 of 1,192 traced, one real catch, a corrupted drug name  
Code: [`ch10-silent-omissions/probe_field_codecheck.py`](ch10-silent-omissions/probe_field_codecheck.py) · replay only, no model calls · output in [`field_codecheck_out.txt`](ch10-silent-omissions/field_codecheck_out.txt)

### Experiment 10.11

**Does enforcing the field through the answer schema change its content?**  
Engineering enforcement (validate against the strict schema in code, correct until it conforms) over Experiment 10.7's 360 recorded replies: 348 conform as generated; the 12 failures all wrote extracted items as objects, and one live correction call each made them conform. In 7 the corrected reply held the same items as strings; in 5 the correction also moved a medicine with no dose out of the extracted list, into the field or out of the reply; no dose was lost. Format 12 times in 360; content moved in 5, always toward what the prompt asked for. Decoder-level enforcement (API structured outputs) not run: no API on this stack  
Code: [`ch10-silent-omissions/probe_field_enforce.py`](ch10-silent-omissions/probe_field_enforce.py) · 12 CLI calls · output in [`field_enforce_out.txt`](ch10-silent-omissions/field_enforce_out.txt)

### Experiment 10.12

**Does a different, stronger auditor catch what the same-model audit missed?**  
Experiment 10.6 rerun with Claude Sonnet 5 as the auditor at its API default (adaptive thinking, effort high; `probe_audit.py --auditor claude-sonnet-5`), same 60 recorded extractions: all 31 known-missing figures named, every short extraction fully caught, and Gabapentin's 1,400 mg/day, a table figure the pattern count cannot see, named in 3 of the 4 lists that lost it. Twenty-two of 49 complete extractions drew alarms: restatements, real off-task source content (water volumes, INR targets, intervals), Levothyroxine's starting dose written as a fraction of the full dose, and the three real catches; nothing invented. $2.42 notional, about six times the same-model audit. The auditor sets the audit's price and its alarm volume. First recording: 39 of 41 named, 12 of 48 complete extractions alarmed  
Code: [`ch10-silent-omissions/probe_audit.py`](ch10-silent-omissions/probe_audit.py) · 60 Sonnet 5 calls through the subscription CLI · every case in [`audit_sonnet_log.txt`](ch10-silent-omissions/audit_sonnet_log.txt)

### Experiment C.1

**The same failures over deliberately damaged input**  
three of four chapters unchanged; silent omission 0/6 -> 4/7, though three of the four drops are figures the OCR invented (only Gabapentin 400 mg is a real dose)  
Code: [`ch10-silent-omissions/`](ch10-silent-omissions/)

### Experiment R.1

**Every experiment run three times**  
8 of 14 published figures outside their own reproducible range as first counted; 2 of the 8 (Chapter 7's baseline) are unsettled, because the scorer that counted them misread refusals as answers  
Write-up: [`report/`](report/)

### Experiment P.1

**Every prompt in the book, audited and run**  
restrictions produced every gain; self-assessments produced none  
Write-up: [`report/`](report/)

### Experiment X.1

**The same experiments on four models, two providers**  
silent corruption 39% -> 88% as the model gets stronger  
Write-up: [`report/`](report/)

### Experiment G.1

**Is the ground truth actually true?**
16 of 48 "unanswerable" questions were answerable; 4 published rates were too high
Code: [`shared/contamination.py`](shared/contamination.py)

Chapters 3 and 9 derive their ground truth the same way: supply two sections of a
label, ask about six, treat the four withheld sections as unanswerable. That holds
only if the supplied sections say nothing about the withheld topics. On real FDA
labels they sometimes do — Levothyroxine's `dosage_and_administration` section
carries a full paediatric dosing table under its own heading, and the paediatric
question was being scored as unanswerable.

The test is structural: an explicit subsection heading naming the withheld topic,
found inside the supplied text — plus three narrow patterns: a dosing line
addressed to children by age and ending in a colon, a "Use of X With …:"
co-administration heading, and an over-the-counter "children under N years of
age:" line. No model, no reading for meaning. It is
deliberately narrow, so the contaminated set is a floor and the corrections below
are conservative.

Four of the sixteen were not found by the test at first. Two were found by the
model: in Experiment 3.5 the two "fabrications" with the highest token probability
in the whole set — higher than the average correct answer — were Metformin and
Albuterol pediatric dosing. Both are answered in the supplied text: one under a
heading that reads "Pediatric Dosage" rather than "Pediatric Use", one in a
labelled dosing line. Two more were found by reading the answers: Sertraline's
interactions, which its dosing section covers under two headings about MAOIs, and
Omeprazole's over-the-counter line "children under 18 years of age: ask a doctor".
The detector now catches all four; the rates in the table that follows are recounted on
the remaining thirty-two.

| figure | published | corrected |
|---|---|---|
| 3.1 fabrication, plain prompt | 30% (14/48) | **3%** (1/32) |
| 3.1 fabrication, soft vocabulary | 35% | **6%** (2/32) |
| 3.1 fabrication, permission clause | 92% | **91%** (29/32) |
| 3.2 grounding template | −69 pts | **at least −91 pts**, all four models |
| 9.1 fields filled with no source | 29% (14/48) | **0 of 33** — the 1 filled field is a correct reading |

Every Chapter 3 correction moves in the same direction: the *baselines* were
inflated, so the gaps the book attributes to prompt design are wider than
published. Chapter 9's corrected baseline holds no fabrication, so it leaves no
gap for a prompt or a check to close.

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
