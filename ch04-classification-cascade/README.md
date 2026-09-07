# Chapter 4 — Classification cascade errors

> Every stage did its job correctly on the wrong task.

**Read this first: the failure barely reproduces on this corpus.** Classification
accuracy is 91–99% depending on which part of a document the passage comes from,
so the cascade fires on 3–9 of 96 passages rather than on a meaningful share of
them. What the chapter says happens *when* a label is wrong holds up well. What
it implies about how often labels are wrong does not hold here, on structured
documents with a clean 10-way taxonomy. See [Null and negative
results](#null-and-negative-results) before quoting any number in this README.

## What this measures

A passage of an FDA drug label is handed to a classifier with the section header
removed. The classifier assigns it to one of ten categories. That label then
selects a downstream extraction stage — `contraindications` sends the passage to
the contraindication extractor, `how_supplied` sends it to the packaging
extractor — and the extractor runs.

Two things are measured, and they are different questions:

**Classification accuracy.** How often the label is right.

**Cascade rate.** Of the labels that were *wrong*, how often the downstream stage
produced a confident answer for the wrong category instead of noticing. The
downstream prompt is given an explicit escape hatch — *"if the passage does not
contain that information, return null"* — so declining is available to it.
Without that, the cascade rate would be 100% by construction and would measure
nothing.

The counter-metric is the same stage's answer rate when the label was **right**,
85–86%. That number is what makes the cascade rate mean something: this extractor
declines on roughly one correctly-labelled passage in seven, so it is not a stage
that answers everything put in front of it.

## How ground truth is derived

An FDA label is already partitioned into named sections by the people who wrote
it. Take a passage out of ADVERSE REACTIONS and its category is
`adverse_reactions`. Nobody labelled anything, no model was asked to produce an
answer key, and there is nothing to argue with — the same property Chapter 9 uses
when it treats a missing section as the correct answer being nothing.

Ten categories, 96 passages, 12 documents, and a distribution nobody chose: 12
dosage passages, 7 contraindication passages, and no geriatric section at all in
four of the labels.

Two details that matter more than they look:

**The header has to come off.** Every section in this corpus opens by restating
its own name — `4 CONTRAINDICATIONS Metformin hydrochloride tablets are
contraindicated in patients with:`. Left in, the task is a string match and
measures nothing. `strip_header()` removes the leading number and title.

**Some passages still name their own section.** Cross-references survive header
stripping (`[see Warnings and Precautions (5.1)]`), and some point at the section
the passage is already in. That is real text and it stays, but the scripts print
how many passages it affects — **29% of opening passages, 25% of body passages**
— so the accuracy figures can be read against it.

**Which passage of a section?** Both. `--chunk first` takes each section's
opening; `--chunk middle` takes a passage from its body. A section's opening
sentences restate its purpose, so openings are the friendly case and body
passages are the honest one. The default runs both, and the gap between them is
the most useful thing in the chapter: accuracy falls from 97% to 91% on the same
sections, same model, same prompt, purely on where in the section the passage
was cut.

## Run it

```bash
python broken.py     # two ungated classifiers, then the cascade
python fixed.py      # the four engineering fixes, as router policies
```

Both replay from `fixtures/` and cost nothing. To re-record:

```bash
python broken.py --live && python fixed.py --live   # in that order
```

`fixed.py` reuses the calls `broken.py` owns rather than re-sampling them — see
[Sampling noise](#sampling-noise-is-larger-than-two-of-the-four-fixes) for why
that is not an optimisation.

## Results

Claude Haiku 4.5, 96 passages, single run.

### Classification and cascade

| | opening passages | body passages |
|---|---|---|
| naive prompt — *"assign the passage to one category"* | **99%** (95/96) | **97%** (93/96) |
| Chapter 4's prompt template | 97% (93/96) | 91% (87/96) |
| heading prompt, options reversed | 99% (95/96) | 99% (95/96) |
| **cascade rate** — wrong label, confident downstream output | **100%** (3/3) | **56%** (5/9) |
| counter-metric — downstream answer rate when the label was right | 85% (79/93) | 86% (75/87) |

Combined, **8 of the 12 misclassifications produced confident downstream output
for the wrong category**. The four that did not were mostly packaging extraction
run on chemistry text, where there is nothing packaging-shaped to return.

The chapter's central mechanism is intact. When the label is wrong, the pipeline
does not notice — and it does not notice despite having been handed a way to say
so, and despite using that way out on 14% of the passages it was labelled
correctly for.

### The four engineering fixes

Every row scored against the label that router would actually have shipped, on
the same recorded votes.

**Opening passages**

| router policy | sent to review | accuracy of what shipped | wrong labels shipped | correct labels sent to review |
|---|---|---|---|---|
| book prompt alone (`broken.py`) | 0% | 97% (93/96) | 3 | 0 |
| naive prompt alone | 0% | 99% (95/96) | 1 | 0 |
| **fix 1** — confidence HIGH only | 1% | 98% (93/95) | 2 | 0 |
| **fix 2** — ensemble majority | 1% | **100%** (95/95) | **0** | 0 |
| fix 1 + fix 2 | 1% | **100%** (95/95) | **0** | 0 |
| strict — unanimous ensemble | 4% | 100% (92/92) | 0 | 3 |

**Body passages**

| router policy | sent to review | accuracy of what shipped | wrong labels shipped | correct labels sent to review |
|---|---|---|---|---|
| book prompt alone (`broken.py`) | 0% | 91% (87/96) | 9 | 0 |
| naive prompt alone | 0% | 97% (93/96) | 3 | 0 |
| **fix 1** — confidence HIGH only | 5% | 92% (84/91) | **7** | 3 |
| **fix 2** — ensemble majority | 1% | 99% (94/95) | 1 | **0** |
| fix 1 + fix 2 | 5% | **100%** (91/91) | **0** | 3 |
| strict — unanimous ensemble | 10% | 100% (86/86) | 0 | 8 |

| fix | verdict |
|---|---|
| 1 — confidence-gated routing | **Close to useless here.** Flagged 33% (1/3) and 22% (2/9) of errors. On body passages it left 7 wrong labels in the pipeline and put 3 already-correct ones in the review queue: **60% of the queue it created was wasted human time.** |
| 2 — ensemble with majority vote | **The fix that works.** Removed 3 of 3 and 8 of 9 errors, for a 1% review rate and **zero correct labels held**. Read the caveat below before adopting it. |
| 3 — per-category F1 gate | **Works exactly as the chapter says.** On body passages aggregate accuracy is 91% and looks fine; `description` scores F1 **0.74** and `pediatric_use` **0.77**. A gate on aggregate accuracy ships both. |
| 4 — classification audit trail | **Worth the column.** `alternative_considered` was the true category on 100% (3/3) and 89% (8/9) of errors. That is the ceiling on what the chapter's weekly query can recover, and it is high. |

## Null and negative results

### The failure does not reproduce at a rate worth calling a failure

97% and 91%. On opening passages the naive one-line classifier missed **one
passage in ninety-six**. A chapter whose case studies are a keyword match on
*"officer"* and an unemployment system that was wrong 85% of the time is
describing something this corpus does not contain. Drug labels are structured,
professionally edited, and their sections are semantically distinct; the ten
categories rarely overlap. That is the good case, and the chapter's argument
should be read as *what a misclassification costs*, not *how often you get one*.

The cascade result is small-sample by construction: 3 and 9 errors. Every
percentage on the cascade line has a denominator under ten. Read the per-case
tables the scripts print, not the rates.

### Self-reported confidence is nearly constant, so it cannot discriminate

**99% of opening-passage classifications and 95% of body-passage classifications
came back HIGH.** The distribution has almost no variance, and a signal with no
variance cannot separate anything:

| self-reported confidence | share | accuracy |
|---|---|---|
| HIGH (opening) | 99% (95/96) | 98% (93/95) |
| MEDIUM (opening) | 1% (1/96) | 0% (0/1) |
| HIGH (body) | 95% (91/96) | 92% (84/91) |
| MEDIUM (body) | 5% (5/96) | 60% (3/5) |

LOW was never used, on any passage, in either configuration.

The grade is not *noise* — MEDIUM really is less accurate than HIGH, 60% against
92% — it is simply almost never issued. **78% of body-passage errors and 67% of
opening-passage errors arrived stamped HIGH**, and a gate on `confidence !=
"HIGH"` waves every one of them through.

This is the fourth time this repo has measured self-reported confidence and found
it does not carry the weight a fix puts on it. Chapter 4's fix 1 is the fix that
depends on it most directly.

One part of the self-report *is* reliable: `requires_human_review` matched the
model's own stated rule on **100% of 192 classifications**. The model applies the
rule it was given perfectly. The input to the rule is what is worthless.

### The book's own prompt template is the worst classifier tested

This is the uncomfortable one.

| prompt | opening | body |
|---|---|---|
| naive — *"assign the passage to exactly one category"* | 99% | 97% |
| **Chapter 4's template** — chain of thought, confidence, runner-up | **97%** | **91%** |
| heading — *"which heading was this printed under"*, options reversed | 99% | 99% |

The chapter's template cost **2 points on opening passages and 6 points on body
passages** against a one-line prompt on the same passages. It was the weakest of
the three members in both configurations.

This also undercuts the ensemble result. Fix 2 works here, but it works because
the book's prompt is the outlier and the other two members outvote it — not
because three classifiers made uncorrelated errors and the errors cancelled. All
three agreed on 96% of opening passages and 90% of body passages. Swap the book
prompt for the naive one and most of the ensemble's headroom disappears, because
there is much less left to fix.

### Sampling noise is larger than two of the four fixes

The same prompt over the same 96 passages, run twice: **94/96 then 93/96** on
opening passages, **86/96 then 87/96** on body passages. One case of drift per
run, at default temperature.

Fix 1 changes the shipped-label count by 1 and 2 on the opening-passage run.
That is inside the noise. It is reported because it is what happened, not because
one run can distinguish it from zero.

This is also why `fixed.py` replays `broken.py`'s recorded calls rather than
re-running them. Two of its three ensemble members are calls `broken.py` owns; if
`fixed.py` re-sampled them, the two scripts would report different numbers for
the same call and the difference between broken and fixed would partly be the
sampler. The `Reuse` class in `fixed.py` tries the fixture first and pays for the
API only when nothing is recorded.

## A bug in this chapter's own scoring, and how it surfaced

The first version of the router-policy table scored **every** policy against the
ensemble majority label — including the row labelled *"no gate (baseline)"*. That
row therefore reported the accuracy of an ungated ensemble while claiming to be
the ungated baseline, which made fix 2 look like it did nothing: the baseline
already had fix 2 folded into it.

It surfaced because two numbers in the same run could not both be true. The
member table said the book prompt was wrong on 9 of 96 body passages; the
"no gate (baseline)" row said 2 wrong labels shipped. Same passages, same call.
The fix is `POLICIES` carrying an explicit *which label would this router ship*
key — `book_label`, `naive_label`, `majority_label` — instead of reading one
shared field.

The same mistake had a second instance: `report_self_report_gap()` originally
scored the confidence grade against the ensemble label too, which credited the
confidence gate with errors the ensemble had already removed and printed *"errors
the router caught: 100%"*. It now scores against `book_label`, because that is
the label the confidence grade describes. That change is what turned fix 1 from
looking effective into being measured at 22%.

Both are the same error: **scoring a component against a label some other
component produced.** Worth naming, because in a real pipeline it is how a
useless gate keeps its funding.

## What the book should change

### 1. Fix 1 should not be listed first, and should not stand alone

Confidence-gated routing is the chapter's lead fix and the only one its prompt
template supports. Measured here it caught 22% of errors on the harder
configuration while filling 60% of its review queue with cases that were already
right. The chapter's own sentence — *"a classifier cannot be trusted to police
its own confidence"* — is the finding, and the fix immediately underneath it asks
the classifier to police its own confidence.

**Change:** keep the fix, and say what it is worth. Self-reported confidence
bands from an LLM are near-constant: 95–99% HIGH here, LOW never issued. A
threshold on them is not a threshold on anything. Either calibrate the bands
against a holdout set before gating on them, or gate on **disagreement between
classifiers**, which is an external signal the model cannot flatten. Chow's
error-reject tradeoff and Geifman and El-Yaniv's selective classification, both
cited in the chapter, assume a calibrated score. A three-level self-report is not
one, and the chapter does not say so.

### 2. The prompt template needs a warning, and probably a rewrite

Chain-of-thought plus a confidence grade plus a runner-up scored **below a
one-line classifier** on the same 96 passages, in both configurations, by 2 and 6
points. A reader who adopts the template as printed may make their classifier
worse.

**Change:** say that the template buys the `alternative_considered` field (fix
4's input, and worth having) at a possible cost in accuracy, and that the cost
should be measured against a plain prompt on the reader's own data before it
ships. One run on one corpus is not enough to say the template is harmful in
general; it is enough to say the chapter should not present it as free.

### 3. Fix 3 is the strongest fix in the chapter and is ranked third

The per-category F1 gate did exactly what the chapter promises, on the first
corpus it was pointed at. Aggregate accuracy 91%, `description` at F1 0.74 and
`pediatric_use` at 0.77, both invisible in the aggregate, both caught by the
gate. It needs no extra model calls and it is ordinary counting.

**Change:** promote it. It is also the only one of the four fixes that would have
caught this chapter's own failure mode — `description` passages being routed to
`how_supplied` on 4 of 11 body passages — before anybody complained.

### 4. "200+ documents per category" is not the threshold that matters

Fix 3 asks for a labelled holdout set of 200+ documents per category. This
chapter used **7 to 12 per category** and the gate still fired on the two broken
ones. What made it work was not volume; it was that ground truth came from the
documents' own structure, so building the set cost nothing.

**Change:** lead with *where the labels come from*, not how many there are. Many
document pipelines have a derivable ground truth sitting in the source —
section headers, form fields, file paths, folder names, subject lines — and a
50-document set derived from structure beats a 200-document set nobody has time
to annotate. Say the size is a function of your smallest category, and that a
category with 7 examples still tells you when it breaks.

## Honest limits

- **One model, one run, 96 passages.** Sampling drift is about one case per run,
  and several results here are two or three cases wide.
- **Ten categories that rarely overlap.** The chapter's failures are ambiguous
  inputs — a visit that is both acute and chronic, a message that is both a
  billing query and a cancellation. This corpus has near-neighbours
  (`pediatric_use`/`geriatric_use`, `description`/`how_supplied`) but no
  genuinely two-category passages. **The chapter's hardest case is not tested
  here.**
- **The ensemble is three prompts, not three models.** The chapter specifies a
  fine-tuned BERT, zero-shot `bart-large-mnli`, and the primary LLM — three
  systems that fail differently. Three prompts against one model is a weaker
  thing, and the 90–96% agreement rate says how much weaker. The result that fix
  2 works is real; the mechanism is not the one the chapter describes.
- **`--chunk last` exists and has no fixtures.** It runs live only.

## Corpus

`data/labels.json` — FDA drug labels from the openFDA API (public domain). Run
`python ../fetch_data.py --show` to see which sections each label carries. Those
sections are the categories, and their contents are the ground truth.
