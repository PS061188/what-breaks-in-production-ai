# Findings — what running the book's code turned up

Each entry: what the manuscript claims, what happened when it was run, what
should change.

Recorded against **Claude Haiku 4.5**, 12 FDA drug labels, August 2026.
`--model` and `--live` are there so anyone can check whether these hold
elsewhere. Small samples — 12 documents — so read the per-document tables, not
just the rates.

**Read this before quoting any number below.** `shared/llm.py` does not expose
`temperature`, so every recorded call was sampled at the provider default of
1.0. Nothing here is greedy-decoded and no metric has been measured twice, with
one exception: four chapters were re-sampled three times during the 23 August
review, and the spread is **±1–2 cases per ~40 samples**. Any row whose effect is
three cases or fewer is inside that spread. Those rows are marked *[noise]* and
are reported because they are what happened, not because one run can distinguish
them from zero. Full detail in [REVIEW.md](REVIEW.md).

## Results

All nine pattern chapters are built. Numbers are what the committed fixtures
print today.

| chapter | metric | broken | fixed | |
|---|---|---|---|---|
| **2** | silent corruption rate | 59% (24/41) | 10% (4/41) | definitions differ between arms — §9 |
| **2** | damaged inputs stopped at the gate | — | **85%** (35/41) | model-free, stable across three models |
| **2** | clean inputs wrongly rejected | — | 17% (2/12) | *[noise]* — both are artefacts |
| **2** | model calls avoided | 0 | **37** | |
| **3** | fabrication rate, soft-inference prompt | **88%** (30/34) | **3%** (1/34) | the repo's strongest result — see §G |
| **3** | fabrication rate, neutral prompt | 6% (2/34) | — | baseline — see §G |
| **3** | fabrication rate, **soft words only** (no permission clause) | **38%** (18/48) | — | **p = 0.52 vs neutral — the chapter's named adjectives had no measurable effect** |
| **3** | answered when the sources did cover it | 96% (23/24) neutral · 100% (24/24) soft | 88% (21/24) | the fix costs 3 answerable questions |
| **4** | classification accuracy, opening passages | 97% (93/96) | 100% (95/**95**) | denominator changes — §9 |
| **4** | classification accuracy, body passages | 91% (87/96) | 100% (91/**91**) | as above |
| **4** | errors that arrived stamped HIGH | 67% (2/3) · 78% (7/9) | — | LOW was never issued, on any passage |
| **5** | stored values still findable in the source | 64% (45/**70**) | 94% (62/**66**) | model chooses the denominator — §9 |
| **5** | qualifier retention in the stored value | 29% (11/38) | 45% (17/38) | *[noise]* — half is the prompt reciting the scored words |
| **5** | dose ranges preserved | 64% (7/11) | 64% (7/11) | *[noise]* and not a measurement — §8 |
| **5** | losses recorded by the normaliser | 0 | **52** | the 0 is a definition, not a measurement — §10 |
| **6** | MIDFACT: asserted a dose not in the excerpt | 10% (4/39) | 0% (0/39) | *[noise]*, and 2 of the 4 are a regex bug — §8 |
| **6** | monitor recall on a new current label | — | **50%** (20/40) | 0% false alarms (0/1381). Deterministic |
| **6** | drugs where the book's filter returns nothing | — | **33%** (2/6) | *[noise]* at n=6 |
| **7** | prompt injections obeyed | **0%** (0/48) | 0% (0/48) | the failure does not reproduce — §2 |
| **7** | aggregate correctness across every subclass | **100%** (144/144 on the recorded run) | **83%** (120/144) | the fix is a regression |
| **7** | legitimate queries answered | 100% (48/48) | **50%** (24/48) | |
| **8** | placement error rate | 3% (1/33) | 3% (1/33) | *[noise]*, and the 1 is a checker bug — §3 |
| **8** | model named the wrong section for its own quote | 9% (3/33 on the recorded run; 18% (6/33) when first published) | 3% (1/33) | **0/33 real** — §3 |
| **9** | fabrication on fields with no source content | ~~6% (2/35)~~ **0 of 35** | 0% (0/35) | both "fabrications" are correct readings; the fixed side is forced — see *Chapter 9 re-read (29 Sep)* |
| **9** | recall on fields the document does cover | 96% (23/24) | 92% (22/24) | *[noise]* — but it did move |
| **9** | fabrications whose quote IS in the document | ~~100% (14/14)~~ withdrawn | — | no fabrication left to carry a quote — *Chapter 9 re-read (29 Sep)* |
| **10** | dose figures returned | 100% (55/55) | 96% (53/55) | *[noise]*; the failure does not reproduce |
| **10** | model's own count vs the independent count | — | 0% (0/6) | measures a prompt ambiguity — §16 |

**Nine chapters' claims do not all hold.** Three failures do not reproduce at all
(7, 8, 10). Two headline fixes are true by construction rather than by
measurement (9, and Chapter 6's stale-index result). Sixteen manuscript changes
follow.

---

## 1. Chapter 9's provenance check is the ground-truth answer key

**Needs a manuscript fix, and a correction to what this repo previously claimed.
This is the most serious item.**

An earlier version of this file said the field-to-section provenance check *"takes
fabrication from 29% to 0% with no loss of recall"* and called it the most
interesting finding in the repo. Both halves are wrong.

`ch09/fixed.py` maps each field to the section allowed to support it, then locates
the quote among the sections that were **supplied** — which are only
`indications_and_usage` and `dosage_and_administration`. Ground truth
(`ch09/common.py:131`) is `present = (section in CONTEXT_SECTIONS)`. Those are the
same predicate:

| field | allowed section | can ever be located? | ground-truth `present` |
|---|---|---|---|
| `indications` | `indications_and_usage` | yes | True |
| `adult_dosage` | `dosage_and_administration` | yes | True |
| `pediatric_dosage` | `pediatric_use` | **never — not supplied** | False |
| `pregnancy_guidance` | `pregnancy` | **never** | False |
| `overdose_management` | `overdosage` | **never** | False |
| `drug_interactions` | `drug_interactions` | **never** | False |

All 48 unsupported fields are nulled unconditionally. **`0% (0/48)` is
arithmetic.** It could not have come out otherwise on any corpus, with any model,
at any temperature.

And recall did move: **96% (23/24) → 92% (22/24)**, with 2 legitimate
`adult_dosage` fields nulled (null rate 17%, 2/12). That false-positive rate is
the one thing `enforce()` genuinely measures.

**Change:** the engineering advice is still right — a field-to-section map is a
design decision the model cannot argue with, and it is free. But the book must
not cite 29%→0% as evidence for it, and the repo must build a case where a
supporting section *is* supplied so misattribution is possible and the check can
fail. Chapter 9's null-rate monitoring signal ("0% vs 100%, separates cleanly")
is produced by the same tautology and is not evidence either.

---

## 2. Three of the nine failures do not reproduce on a current model

**Needs a manuscript addition, and it is the most useful thing the repo found.**

| chapter | the failure | what happened |
|---|---|---|
| **7** — edge input | injection, OOD, out-of-scope | **144/144 correct.** Zero injections obeyed, zero out-of-scope answered, every legitimate query answered |
| **8** — routing and placement | content filed under the wrong field | **0 real placement errors in 33** at any verification window except the one the code uses |
| **10** — silent omissions | items dropped from a list | **55/55 dose figures returned**, including from an 11,700-character document |

Chapter 7's fix then makes things worse: aggregate correctness 144/144 → 120/144,
legitimate queries answered 100% → 50% (recorded run, replayed 14 Nov 2026; first published as 118/144 and 46%). And 96 of its 118 correct answers involve
**no model call at all** — `ch07/common.py:387` scores any gate-blocked input as
correct for the decline and no-canary arms, so two `0% (0/48)` rows printed side
by side are, on the left, 48 real responses and, on the right, arithmetic over an
empty set.

Chapter 10's fix nulls two figures the baseline returned, while `fixed.py:139`
prints the hardcoded note *"Unchanged from the baseline"* directly beneath
`>> Dose figures returned: 96% (53/55)`.

**Change:** these are publishable null results and they are more credible than
another chapter that worked. The book should say which failures a 2026 frontier
model has largely closed on clean, structured, English input — and should not
imply a fix improved something it regressed. Chapter 7's OOD fix in particular
rejects **every Hindi query and every padded query**, which is a fix that
discriminates against exactly the users the chapter's own case study is about.

---

## 3. Chapter 8's self-report finding is a string-normalisation bug

**Needs a manuscript fix. This one has spread.**

`>> Cases where the model named the wrong section for its own quote: 18% (6/33)`
is cited as "about one time in five" in `ch09/common.py:107`, in
`ch09/fixed.py:110` as the reason the fix locates quotes independently, and in
Chapter 7 as a prior measurement.

All six named the **right** section. `canonical_section` (`ch08/common.py:72-81`)
strips punctuation but not the section number the document itself prints:

```
claimed=1_indications_and_usage   actual=indications_and_usage
claimed=4_contraindications       actual=contraindications
claimed=indications_usage         actual=indications_and_usage
```

The model wrote the header as printed, which is what the prompt asked for. The
sixth case is a checker bug (below). Cross-model the number is 18% / 64% / 12% —
a 52-point spread that tracks how verbosely each model writes a header. Three
fresh Haiku runs give **2/33, 3/33, 2/33 (6–9%)**, so 6/33 is also a high outlier.

The chapter's single placement error is also not one. `locate()` compares the
first **80 characters** of the quote (`VERIFY_WINDOW`), and those characters are
the drug name and strength, which every section of an FDA label repeats:

| window | indications | contraindications | adverse | verdict |
|---|---|---|---|---|
| 80 | **100.0** | 100.0 | 100.0 | indications (first match wins) |
| 200 | 69.0 | **100.0** | 65.0 | contraindications |
| whole quote | 54.8 | **92.2** | 49.8 | contraindications |

At any window but 80, **misplaced = 0/33 on both sides**. The rules engine fires
exactly once in the chapter — to reject that correctly-extracted contraindication.
The review queue's only row is a false rejection.

`VERIFY_WINDOW = 80` was tuned in Chapter 9 to protect **recall on long
paraphrased quotes**. Chapter 8 needs **precision on section attribution**. One
shared constant, two incompatible jobs.

**Change:** the design principle survives — do not trust a model's account of
where content came from, locate it yourself. But the evidence offered for it is
an artefact, "about one time in five" must come out of Chapter 9's code comments
and Chapter 7's README, and Chapter 8 should be published as a null result.

---

## 4. Chapter 3's code snippet targets `gpt-4` via `instructor` + `openai`

**Needs a manuscript fix.**

The citation-enforcement snippet reads `model="gpt-4"` inside
`instructor.patch(openai.OpenAI())`. Two problems, one cosmetic and one not:

- `gpt-4` is a long-superseded model id. In a 2026 practitioner's guide it dates
  the book badly, and it is the first line of code a reader will run.
- The chapter's argument is that the *validated schema plus the post-call check*
  is the fix. Pinning it to one vendor's client and one third-party library
  makes it read as an OpenAI recipe rather than a structural principle.

**Change:** drop the pinned model id, and add a sentence saying the mechanism is
the schema and the code check — every major SDK now has a native form of it.
The repo implements the same contract with Anthropic's structured outputs.

---

## 5. Chapter 9's verification rule does not work as written

**Needs a manuscript fix. Unchanged and still the cleanest mechanical finding.**

The chapter gives the check as `rapidfuzz.fuzz.partial_ratio > 85` and says
nothing about quote length. Run literally, on the whole quote, it fails — and
the reason is not visible from reading it.

`partial_ratio` compares the needle against the best-matching window of the
haystack *of the needle's own length*, so its tolerance for small differences
shrinks as the quote grows. The model returns quotes of 240–720 characters that
are near-verbatim with a few words elided. Those score in the 60s and 70s and
get rejected as fabrications.

Measured, sweeping how much of the quote is verified:

| verified | recall (fields with source) | fabrication (fields without) |
|---|---|---|
| whole quote — the rule as printed | **54%** | 14% |
| first 80 chars | **95%** | 22% |
| first 150 chars | 83% | 22% |
| first 200 chars | 66% | 18% |

The rule as printed buys 8 points of fabrication for 42 points of recall.

*Replayed 29 Sep 2026 on the committed fixtures, one run each, correct values on
the fields the supplied sections cover (of 23):* plain prompt — whole quote 9,
first 80 characters 23, 150 → 19, 200 → 14; Prompt 9-1 — 11, 23, 20, 15. The
sweep above came from recordings since overwritten, and its fabrication column
counted correct readings (see "Chapter 9 re-read"). The book prints the replayed
figures.
A reader who implements it exactly will null nearly half their legitimate
extractions and have no idea why.

**Change:** state that the quote must be verified over a bounded prefix (the
repo uses 80 characters), and say why — otherwise the check silently degrades
as quotes get longer. **Add the warning the repo learned the hard way**: the
right window depends on the job. 80 characters protects recall on paraphrased
extraction and destroys precision on section attribution, which is what broke
Chapter 8 (§3).

---

## 6. Verifying that a quote exists does not catch misattribution

**Needs a manuscript addition. Still the most interesting finding.**

With the window corrected, the quote check stopped rejecting anything at all,
and the fabrication rate barely moved. The rows explain why.

Asked for `pediatric_dosage` on a label with no pediatric section supplied, the
model returns pediatric text lifted from the **indications** section — *"Acute
leukemia of childhood..."* — and attaches a quote that is genuinely in the
document. Quote-existence verification passes it, because the quote is real.

**100% of the baseline's fabrications carried a quote that is really in the
document (14/14).** Not one was an invented quote. This finding is structural,
not marginal, and it survives everything in §1 — what does *not* survive is the
claim that the repo's provenance check demonstrably fixes it.

That is Chapter 3's source-tracking failure appearing inside Chapter 9's fix.
The chapter's own prevention table already distinguishes *"does this content
point at a passage?"* from *"is the content actually supported by that
passage?"* — but the code fix implements only the first, and the text does not
warn that the first is the weaker one.

The repo adds the second check: the model names the section its quote came
from, and a `SUPPORTING_SECTIONS` map in code says which sections can support
which field. Pediatric dosing sourced from the indications section is nulled
whatever the quote says. **On this corpus that map is the answer key — see §1
before citing it.**

**Change:** Chapter 9's engineering-fixes section should carry the
field-to-section provenance check, not just quote-existence — and should say
that quote-existence on its own is defeated by exactly the failure Chapter 3
describes. It is a good cross-reference and the book is currently missing it.

---

## 7. A plain grounded prompt already declines on a current model

**The chapter is right, and can be sharper.**

Chapter 3 attributes fabrication partly to prompt language that permits soft
inference. The repo tests that directly, running the same 48 unanswerable
questions through two prompts:

| prompt | fabrication rate | answered when answerable |
|---|---|---|
| neutral — *"answer using the label excerpt below"* | **29%** (14/48) | 96% (23/24) |
| soft-inference — *"be helpful and complete… drawing on standard pharmacology where the excerpt is thin"* | **92%** (44/48) | 100% (24/24) |

A 63-point, 30-case gap. This is the largest and best-supported effect in the
repo, and the only one comfortably outside the noise floor by an order of
magnitude.

Worth putting in the book, because the alternative reading — *models hallucinate
on grounded questions, full stop* — is what a sceptical staff engineer will push
back on, and the data does not support it as stated.

The failure shape is also worth naming: not a bare invention, but **a caveat
followed by an assertion** — *"the excerpt does not contain information about
drug interactions. However, [general knowledge]."* The caveat is what carries
it through review.

**One caveat the book must carry.** The outcome variable here — did the model
assert or decline? — is produced by a **second model call** (a pinned Sonnet 5
classifier, `ch03/common.py:98-112`). Every judgement is in `fixtures/`, but the
judge's own accuracy has never been checked against a human. A repo whose
recurring thesis is that model self-assessment is unreliable should not leave its
flagship number resting on an unvalidated model classifier.

---

## 8. Reference regexes that manufacture findings

**Needs a footnote in three chapters, and it is the same bug three times.**

Chapter 10's reference count originally read the gene identifier
`VKORC1−1639G` as a 1,639-gram dose and invented an omission that never happened.
That was patched. **The class was not.**

- **Chapter 10.** `DOSE` matches a number beside a unit, so `15 mg/kg/day` scores as a 15 mg dose. **17 of the 55 reference figures (31%) appear only as per-kilogram or per-square-metre rate coefficients** — 8 of Levothyroxine's 11, 6 of Gabapentin's 13, 2 of Amoxicillin's 10, 1 of Sertraline's 7.
- **Chapter 6.** `DOSE` includes `mL` under `IGNORECASE`, so `15 mL/min` creatinine clearance reads as a dose. Both "novel dose values" that admitted Gabapentin's renal subsection to the corpus are eGFR thresholds. Worse, `dose_values()` returns `[]` for the flattened FDA renal table the model was shown — *"≥60 900 to 3600 300 TID 400 TID…"* — because no unit sits next to any number. **The model read the table correctly, re-attached the units, and was scored as seven fabrications.** All 16 flagged values in all four MIDFACT failures are bare numbers already in the excerpt, so `ch06/common.py:446`'s *"provably not in the text the model was handed"* is false for every measured case. The residual real finding is **2/39, not 4/39**: on Furosemide and Levothyroxine the model closed a severed range (`20 to` → `20 mg`).
- **Chapter 5.** `RANGE_RE` makes the unit optional, so it matches `ages 6-12`, `every 4 to 6 hours`, `INR of 2 to 3`, `for 10-14 days` — and, tested directly, `VKORC1-1639G` → `1-1639`. **5 of the 11 documents in the "dose ranges preserved" denominator contain no dose range at all.** Warfarin's "range kept = yes" on both sides is the INR check interval.

**Change:** the manuscript's advice — that a second, independent count is what
catches omission — is right and should stay. What must be added is that **the
independent instrument is itself code that can be wrong, and it fails in the
direction that manufactures findings rather than missing them.** That is the
lesson of the `VKORC1` bug, and it is worth a box.

---

## 9. Denominators that move between the broken and fixed arms

**Needs a manuscript note about how to run this comparison.**

- **Chapter 4.** `broken.py` scores 96 passages; `fixed.py` scores the **95** and **91** that survived the confidence gate. "97% (93/96) → 100% (95/95)" excludes exactly the cases the fix withheld. The per-category F1 gate has the same defect: computed on post-router survivors it structurally cannot fire, and `fixed.py` duly reports all ten categories at F1 1.00 — the README's 0.74 and 0.77 come from the **broken** arm.
- **Chapter 5.** The `fields` array is unbounded, so the model chooses the denominator: 70 items broken, 66 fixed, with per-document swings of 11→4 (Metformin) and 9→12 (Gabapentin). Three fresh runs of the *same broken prompt* gave denominators of **65, 69 and 77**. On a common denominator (first four fields per document) the effect is **52% (25/48) → 91% (43/47)** — real, but not 64%→94%. And 37 of broken's 70 "findable" values are ≤6 characters (`'1'`, `'2'`, `'10'`), which match anywhere in 3,500 characters; in the fixed arm that count is 1 of 66.
- **Chapter 2.** `fixed.py` skips gate-blocked cases in the numerator and counts all 41 in the denominator, so only **6 slots can fire**. Among documents the gate passed, **4 of 6 (67%) were still silently corrupted — higher than the 59% baseline.** And the two arms use different definitions: `broken.py:73` requires `changed AND confident`, `fixed.py:61` requires `changed` alone.

**Change:** the book already argues for counter-metrics. It should add the
narrower rule that makes them work: **fix the denominator before you compare, and
say what happens to the cases the fix removes.** A fix that improves a rate by
deleting rows has not improved anything.

---

## 10. Two "improvements" that are definitions, not measurements

- **Chapter 5's "52 losses vs 0 in the baseline."** `broken.py` never imports `normalise`. The 0 is not a measurement; the baseline was never instrumented. Running the identical `normalise.py` over broken's own extracted values yields **53 discard rows — one more than the fix.** The argument is still sound: the fix *records* what the baseline swallows, and that is the whole point of moving normalisation into code. The number is not.
- **Chapter 6's stale-index result.** `STALE_INDEX_DATE = "20260101"` sits eight days before the earliest ACTIVE label in the corpus, so the stale index arithmetically cannot return an ACTIVE document. "100% (6/6)" is a tautology. At `20260109` it reads 83%; at `20260602`, 50%. And *"Every one of these passes a status check"* is false — the stale query has no status clause, and for Furosemide (the drug producing the 579-day headline) the served document would have been SUPERSEDED even inside the stale index.
- **Chapter 8's "placement errors that survived into storage: 0% (0/33)."** Hardcoded. Both branches of the conditional at `ch08/fixed.py:138-143` return the literal `0`.
- **Chapter 6's "characters discarded: 0 vs 123."** `naive_cut` returns `text[:budget]`, so `discarded` is 0 by definition on the left.

**Change:** none to the arguments, all four of which are correct. But no number
in this list should appear in the book as a measured result.

---

## 11. Chapter 6 — the freshness filter as printed can empty the result set

**Needs a manuscript fix. Confirmed.**

The chapter specifies `status == "ACTIVE" AND last_verified > now() - 90d`. A
document can be the newest label in existence and still be older than 90 days —
Furosemide's current label is **225** days old, Sertraline's **214** (measured
against the corpus's pinned retrieval date of 2026-08-22; the README's 226/215
were computed by hand against a wall clock a day later) — so the conjunction
returns **nothing for 2 of 6 drugs**, with no error and no empty-result branch.
Chapter 3 gives the same fix without the second clause. The two chapters should
agree, and Chapter 3 is the one that is right.

Fragile: Lisinopril's ACTIVE label is 81 days old, **nine days** from flipping
the headline from 2/6 to 3/6. The date is hardcoded so it will not drift on its
own, but a corpus refetch moves it.

**One correction to what Chapter 6's README implies.** It suggests Chapter 3
handles the top-k instability Chapter 6 documents. It does not: Chapter 6 uses
`stable_top_k` (over-fetch to 64, deterministic sort); Chapter 3 sorts the
*prompt* by id but never over-fetches, so it remains exposed. That is a live
defect in Chapter 3 presented as fixed.

---

## 12. Chapter 6 — top-k overlap monitoring detects ranking churn, not staleness

**Needs a manuscript fix, and this is Chapter 6's best result.**

Run for real over 398 weeks of real filing dates: when a new current label
arrived, the monitor alerted **50% of the time (20/40)**, with **0% false alarms
(0/1381)**. The misses are weeks where the new document did not enter the top 3,
so overlap stayed at 100% while the index went stale. The chapter's sentence
*"a drop signals that fresh documents are not being ingested"* is not supported.
Tracking the maximum `last_verified` per canonical query would be.

This is the only Chapter 6 result with no model call, no regex in its ground
truth, and a denominator in the thousands. It is worth more space in the book
than it currently gets.

---

## 13. Chapter 6 — boundary-aware truncation only matters mid-clause

All measured failures were cuts inside a numeric range or a table row — *"the
usual initial dose of furosemide tablets is 20 to"* answered as *"20 mg"*. Cuts
landing on a subsection heading produced **zero** bad answers in either arm: the
model recognises the shape and says the text is incomplete.

Reported as 10% (4/39) → 0% (0/39), Fisher p = 0.12. **Three corrections:**

- Two of the four failures are the `mL` regex bug (§8). The real effect is **2/39**.
- The Fisher figure is **hand-written prose**, not computed by any script. Nothing regenerates it if the counts move. Recomputed on `[[4,35],[0,39]]` it is 0.115, so the number is right — but it should be produced in code.
- The fixed arm's 39 rows contain only **36 unique samples**: `boundary_cut` collapses several budgets in the same subsection onto the same boundary. The test is computed on a denominator the fixed arm does not have.

A mechanism, not an established rate — which the chapter README already says.

---

## 14. Chapter 6 — the `status` flag is itself a snapshot

An index last ingested seven months ago served a superseded label for **100%** of
drugs through a filter that passed, and **100%** of answers changed. Chapter 6's
own thesis applies to Chapter 6's own fix and the text does not close that loop.

**Two caveats on the numbers.** The "100% of answers changed" test is
`normalise_ws(a) != normalise_ws(b)` over two independently sampled free-text
answers at temperature 1.0. There is no same-context control anywhere in the
repo, so it is not established that this measures retrieval rather than the
sampler. Chapter 3's version of the same test (`fix_retrieval.py:141`) has the
identical construction and the identical 6/6.

And the version corpus is not a version chain. `data/label_versions.json` holds
48 records with **48 distinct `set_id`s across 39 distinct labelers** — eight
different repackagers' labels for the same generic, not eight revisions of one
document. No ACTIVE label shares a labeler with anything called SUPERSEDED
against it. Everything downstream inherits this, including Chapter 3's *"83% of
unfiltered retrievals were superseded"* and *"oldest 7.5 years stale."*

Session isolation (fix 4) is infrastructure and is **not implemented** — a mock
would only prove the mock was written correctly. Marked as such in the chapter
README rather than faked.

---

## 15. The ground truth is "not supplied", not "not in the document"

**Needs a fix in three places, including this repo's own README.**

The root README says *"Prednisone's label has no pediatric-use section,
Sertraline's has no pregnancy section. Those gaps are the ground truth every
chapter scores against."* That is not what Chapters 3 and 9 do. Both derive it as
*"is this section among the two we supplied?"* The corpus mostly **has** these
sections:

| section | labels that have it |
|---|---|
| `pediatric_use` | **8 of 12** |
| `pregnancy` | **7 of 12** |
| `overdosage` | **10 of 12** |
| `drug_interactions` | **10 of 12** |

For most of the 48 "unsupported" fields the document does cover it — the context
window does not. The metric is still meaningful and still needs no annotation,
but it measures **ungrounded-in-context generation**, not fabrication about a gap
in a document, and the model may be recalling genuine label content from
training. That is a different claim and the book should make the narrower one.

---

## 16. Model self-assessment — the count is wrong and two of the legs do not hold

**Needs a manuscript fix.** The repo cannot agree on how many times it has
measured this:

| location | claim |
|---|---|
| `report/parts/07-ch10.html` | *"arriving a **third** time from a third direction"* |
| `ch04/README.md:180` | *"This is the **fourth** time this repo has measured self-reported confidence"* |
| `ch07/README.md:156` | *"**Three earlier** measurements … this is the **fourth**"* |

Two chapters both claim to be fourth. And two of the instances do not measure
what they claim:

- **Chapter 2's 83% (34/41) confident-on-damaged has no control.** Re-derived: `confident=False` on damaged is **17.1% (7/41)**; on clean it is **16.7% (2/12)**. The flag separates clean from damaged by **0.4 points** — zero discriminative power, which is a *stronger* version of the chapter's claim and is sitting unused in the fixtures. All nine non-confident answers come from two drugs, Levothyroxine and Warfarin, both of whose labels say the dose must be individualised. **The flag tracks the drug, not the damage.**
- **Chapter 8's 18% (6/33) is 0/33 real** (§3).
- **Chapter 10's "0% (0/6) self-count agreement" measures a prompt ambiguity.** The independent count is of **distinct** dose figures; the prompt says *"count the dose amounts in the source"*, which reads as occurrences. Every one of the six model counts sits between the distinct count and the occurrence count, and much nearer the latter — Gabapentin: distinct **13**, model **41**, occurrences **57**. The model is not failing to count; it is counting a different thing.
- **"Confidence never issued LOW" is a Chapter 4 finding, not a Chapter 2 one.** Chapter 2's schema has a boolean `confident` and no bands at all. If the manuscript files it under Chapter 2, it is misfiled.

**Change:** the thesis is right and Chapter 9's *"100% of fabrications carried a
real quote"* (14/14) is excellent evidence for it. Settle the count, drop the two
instances that measure nothing, and add Chapter 2's clean-vs-damaged control —
12 extra calls, about a cent, and it turns a weak number into the chapter's best.

---

## Two null results, kept

**Chapter 5's dose-range preservation did not move.** 64% both ways — but see §8:
5 of the 11 documents contain no dose range, three fresh baseline runs give
9/11, 8/11 and 8/11, and on `claude-opus-5` the same metric reads 9/11 → 10/11.
This is not a null result. It is an unmeasured quantity, and it should be either
fixed or withdrawn.

**Chapter 3's citation check never fired.** Zero answers rejected by code; the
whole improvement came from the prompt and the `answerable` flag. The check
costs nothing and is the half that survives a model swap, but on this corpus it
did no work, and the README says so rather than implying it earned its place.

---

## Not a book problem, but worth a footnote

The first version of `normalise.py`'s frequency parser reported every *twice
daily* dose as *once daily* — `\bdaily\b` matched before the twice-daily
pattern. Its unit test caught it in seconds.

That is Chapter 5's case for moving normalisation out of the prompt, in one
sentence: the same bug inside a prompt produces the same wrong answer, and
there is no test you can run against it.

The same argument cuts the other way, and the book should say so. `normalise.py`
has unit tests and is right. The **reference regexes in Chapters 5, 6 and 10 have
none**, and all three are wrong (§8) — in the direction that produces findings.
A deterministic check is only better than a prompt if somebody tests it.

## Correction — Chapter 3, the "63-point gap" (Aug 2026)

Found by Prachi reading the prompts, not by a test.

The `soft-inference` baseline did not only add the soft vocabulary the chapter
warns about. It also added **"drawing on the label excerpt below and on standard
pharmacology where the excerpt is thin"** — explicit permission to leave the
source. A model that leaves the source is obeying that instruction.

A third arm (`soft-words`) keeps every soft adjective and deletes the permission
clause:

| arm | fabricated | vs. row above |
|---|---|---|
| neutral | 29% (14/48) | — |
| **soft-words** | **38% (18/48)** | **p = 0.52 — no effect** |
| soft-inference | 92% (44/48) | p = 3e-08 |

**Updated with 5 runs per arm** (neutral 15,14,15,14,15 = 30.4%; soft-words
17,20,16,17,15 = 35.4%). The soft-words arm was higher in 4 of 5 paired runs and
never lower — sign test p = 0.125. So the first single-run read ("p = 0.52, no
effect") was underpowered and wrong.

**About 5 of the 63 points belong to the chapter's thesis — small, consistent in
direction, not statistically established. About 57 belong to a clause the chapter
never discusses.** The chapter must be rewritten to
blame explicit permission rather than soft vocabulary — see Task 3.2.

The grounding-template result across four models is unaffected in direction and larger once §G is applied: at least −85 points on every model.

Limits: n=48 detects only large effects, so this is no evidence of a difference,
not evidence of none. One model, one run.

## Correction — Chapter 2, the "17% false positive" rate (Aug 2026)

The gate rejected the **clean** Amoxicillin control. Recorded as a false positive.
It was not: the document contains **14 zero-width spaces (U+200B)**, two clusters
of seven, one immediately before `600 mg/42.9 mg per 5 mL`. Real, unplanted
corruption in a real FDA label, invisible to a human reader, fatal to exact-match
lookup.

Corrected rate: **1 of 12, not 2**. The remaining one is an OTC label whose dosage
section is genuinely 739 characters against a 900-character threshold — a real
false positive, and a good illustration that a cheap check measures distance from
the documents its author had in mind.

## Prompt audit — every baseline in the repo (Aug 2026)

Triggered by the Chapter 3 finding. Every broken/fixed prompt pair re-read for the
same defect: a baseline that *instructs* the behaviour it is then scored as
failing at.

| Ch | Baseline | Verdict |
|---|---|---|
| 2 | neutral extraction request | clean |
| 3 | soft-inference | **confounded — corrected** |
| 4 | heading classification | clean |
| 5 | "standardise as you go" | **confounded, worse than ch3 — corrected** |
| 6 | neutral | clean baseline, but the *treatment* bundles 6 rules and cannot be attributed |
| 7 | neutral | clean |
| 8 | neutral | clean |
| 9 | neutral; "use N/A" | clean — and the scorer credits N/A as declining in **both** arms, which biases *against* the fix. Conservative. |
| 10 | neutral | clean |

## Correction — Chapter 5, all three headline measures (Aug 2026)

The baseline prompt named every scored failure as an instruction: *"Doses as a
number in milligrams"* (findability), *"One canonical value per field"* (range
collapse), *"Keep it tidy and consistent"* (qualifiers). A plain arm was added and
all arms run 5x live.

| measure | plain | fix | fix ahead in | sign p |
|---|---|---|---|---|
| values findable in source | 66% | **93%** | 5 of 5 | 0.062 |
| qualifier retention | 38% | 39% | 4 of 5 | 0.375 |
| **dose ranges preserved** | **85%** | **65%** | **0 of 5** | 0.062 |

- **Auditability holds.** 66 → 93%, every run. Keep it.
- **Qualifier retention is nothing.** The published 29% → 45% was the fix undoing
  damage the baseline prompt caused. Against a plain prompt: 38 vs 39.
- **Ranges got worse.** The capture prompt says *"Never collapse a range to a
  single number"* and preserved fewer ranges than a prompt that said nothing —
  behind in all 5 runs, spreads do not overlap (plain 9-10/11, fix 6-8/11).

**Denominator warning.** Values-findable has a denominator the model chooses; it
swung 54–77 across identical runs (43%). Qualifiers (38) and ranges (11) are
source-derived and fixed. **The two stable measures show no benefit and one harm;
the one unstable measure carries the entire published result.**

## Correction — Chapter 6, the staleness protocol is six rules, not one (Aug 2026)

The prompt audit flagged the treatment, not the baseline: the chapter's protocol
bundles six rules and was scored as one block. Split into arms, 5 live runs each,
6 drugs. Measured on "answered with a dose only a superseded label states":

| arm | mean | run by run |
|---|---|---|
| neutral | 67% | 4,4,4,4,4 |
| **status only** | **17%** | 1,1,1,1,1 |
| **90-day only** | **67%** | 4,4,4,4,4 |
| status+date+version | 33% | 2,2,2,2,2 |
| full protocol (book's) | 30% | 2,2,1,2,2 |

- **The 90-day rule is inert** — identical to no rule at all, every run.
- **The book's full protocol is beaten by one of its own six rules**, 30% vs 17%.
  Adding the date rule to the status rule doubles failures.
- Status-only got **5 of 6 drugs exactly right**, and its 3 refusals are precisely
  the 3 drugs where retrieval returned no ACTIVE document. Refusal is correct there.

## Correction — Chapter 3 fix 2, the false-alarm rate was a badly chosen row (Aug 2026)

Reported as "85% caught / 29% false alarms". That is one row of a threshold sweep
presented as an operating point. The sweep:

| threshold | cross-encoder caught / false | bi-encoder caught / false |
|---|---|---|
| 0.2 | 83% / 12% | 23% / 0% |
| **0.3** | **85% / 12%** | 44% / 0% |
| 0.4 (book's) | 85% / 21% | 71% / 17% |
| 0.5 | 85% / 21% | 88% / **38%** |
| 0.7 | 85% / 21% | 98% / **83%** |

**Ship the cross-encoder at 0.3**: 85% caught, 3 false alarms of 24. Loosening past
0.3 buys no extra detection and doubles false alarms. The book's 0.4 is strictly
worse. The 38% belongs to the bi-encoder, not the recommended configuration.

Fix 3 (LLM judge) has **no threshold to tune** — verdict, not score. Run it behind
fix 2: ~a third of traffic routes through, ~$14/1,000 instead of $41.

A "false alarm" = a grounded answer flagged as ungrounded. Denominator is the 24
answerable questions.

## Correction — Chapter 3 fix 3, both published numbers wrong (Aug 2026)

The judge's fixture was invalidated by the Chapter 3 repeat runs and had to be
re-recorded. The new numbers did not match, so it was run four times fresh
(claude-sonnet-5 judging claude-haiku-4-5 answers):

| run | caught /48 | false alarms /24 | $/1000 |
|---|---|---|---|
| 1 | 92% (44) | 17% (4) | $22 |
| 2 | 90% (43) | 21% (5) | $22 |
| 3 | 92% (44) | 17% (4) | $22 |
| 4 | 90% (43) | 25% (6) | $22 |
| **mean** | **90%** | **25%** | **$22** |
| *published* | *85%* | *38%* | *$41* |

The published 38% is outside the fresh spread and does not reproduce. The $41 was
a costlier judge model.

**The finding worth publishing is the instability**: the false-alarm rate moved
17→25% across four runs of an identical configuration. And unlike a similarity
score, an LLM judge returns a verdict, not a number — **no threshold to tune**.

Recommendation: run it behind fix 2 (cross-encoder @ 0.3, free, 85% catch). About
a third of traffic routes through, ~$7/1,000.

## The reproducibility sweep (Aug 2026) — the most important result in the repo

`repeat.py` built. 14 scripts x 3 live runs across chapters 2, 6, 7, 8, 9, 10.
$3.38. **20 of 53 measures moved; 33 held.**

**8 of 14 published headline figures fall outside their own 3-run range** (14 Nov 2026: 2 of the 8, the Chapter 7 baseline rows, are unsettled; the scorer that counted them missed the refusal "unable to interpret", so 6 of 14 stand):

| ch | measure | published | 3-run range | |
|---|---|---|---|---|
| 2 | silent corruption rate | 59% | 34-56% | **OUTSIDE** |
| 2 | corruptions surviving the fix | 10% | 5-7% | **OUTSIDE** |
| 6 | asserted a dose not in the excerpt | 10% | 3-5% | **OUTSIDE** |
| 6 | answers changed with stale index | 100% | 83-100% | inside |
| 7 | **out-of-scope / noise answered** | **0%** | **2-4%** | **OUTSIDE** |
| 7 | aggregate correctness, baseline | 100% | 99% | **OUTSIDE** |
| 7 | aggregate correctness, fixed | 82% | 83% | **OUTSIDE** |
| 7 | legitimate queries answered, fixed | 46% | 48-50% | **OUTSIDE** |
| 8 | wrong section named for own quote | 18% | 3-15% | **OUTSIDE** |
| 8 | placement error rate | 3% | 0-3% | inside |
| 9 | recall on fields the doc covers | 92% | 92-96% | inside |
| 10 | dose figures returned | 96% | 96-100% | inside |
| 10 | documents where something was dropped | 0% | 0-17% | inside |
| 10 | model's count vs independent count | 0% | 0-17% | inside |

Caveat: "outside" is not always sampling noise — several experiments had genuine
bugs fixed between the published run and this sweep (ch8's 18% was a known checker
artefact; ch2 excluded no-op mojibake). Corrected code and variance cannot be
separated after the fact, **which is the argument**.

### Three consequences

1. **Chapter 7's failure DOES reproduce.** Published 0/48; observed 1, 1, 2 of 48
   — non-zero every run. Remove it from the "four of nine did not reproduce"
   tally. See Task 7.0.
   **Weakened 14 Nov 2026.** These counts were scored by `_declines()`, which then
   missed the refusal "unable to interpret". The only one of these cases whose reply
   is still recorded (Warfarin ood_numeric) was such a refusal; the other runs' replies
   were overwritten, so the 1, 1, 2 cannot be re-scored offline. Whether Chapter 7's
   failure reproduces is unsettled until a fresh three-run, recorded check.
2. **Chapter 2's headline (59%) is above everything it reproduces** (34-56%).
   Publish a range, not a two-digit figure.
3. **Chapter 4 was run afterwards** under a hard $3.76 ceiling, and it **holds**:
   baseline accuracy 92% and 91% vs published 91%; errors 8 and 9 of 96 vs a
   published 9. Its "did not reproduce" verdict survives repetition.
   **But the fixed arm's published 100% (91/91) came back 98% (92/94) on all three
   fresh runs** — the denominator moved 91 -> 94 because the ensemble discards
   member disagreements before scoring. Part of "100%" was a denominator choice.

4. **NEW — the ensemble does not move at all.** Three live runs returned
   bit-identical numbers on all ten measures, while the single classifier moved on
   every measure it reports (accuracy 92/91, errors-stamped-HIGH 75/89, cascade
   50/44). The chapter sells the ensemble on accuracy (modest: 98% vs 91-92%).
   **Its real advantage is stability** — it absorbs the variance that broke 8 of
   14 published figures here. A metric that moves on its own cannot be alerted on.
   Caveat: the identical runs include identical *errors*. Stable is not correct.

### What held

All 33 stable measures are the ones with **no model call**: the byte-level gate,
the quote verifier, the freshness monitor, the rules engine. Every measure that
moved involved a model call. That is a cleaner statement of the book's thesis than
any percentage in it.

### The harness's own bug, kept on the record

`HEADLINE` was compiled without `re.MULTILINE`, so it matched zero lines and
reported "nothing moved" for 42 live runs. $3.40 spent on a clean bill of health
that was an empty result set. A check that cannot fire is indistinguishable from a
check that passed. `repeat.py` now aborts rather than reporting agreement when it
parses no headlines.

### Budget guard

`repeat.py --max-cost N` stops *before* a run that would breach the ceiling,
estimating from the most expensive run so far. On Chapter 4 it spent $2.78 and
declined the run that would have hit $3.80 against a $3.76 limit. A ceiling
checked after the money is spent is not a ceiling.

### Running total spent on repeatability

| | |
|---|---|
| ch3 + ch5 + ch6 arm splits and repeats | ~$12 |
| six-chapter sweep, wasted to the regex bug | $3.40 |
| six-chapter sweep, real | $3.38 |
| ch4 under ceiling | $2.78 |
| ch4 fixed arm, 2 extra runs | $2.04 |
| **total** | **~$23.60** |

It overturned or qualified 12 published figures.

## Task 10.1 RUN — the prose enumeration test (Aug 2026). Prediction failed.

This report predicted in print that omission would get *worse* on long prose. It
does not.

Sertraline ADVERSE REACTIONS, 18,791 chars, **185 distinct reactions**, ground
truth from the label's own delimiters (`Body System - Frequent: a, b; Infrequent:
c, d; Rare: e, f.`), no model involved. Only the size of the ask changed; the
source text was byte-identical in all arms. 4 live runs, **$1.39**.

| arm | items per ask | recall, 4 runs |
|---|---|---|
| **all at once** | **185** | **99%, 100%, 100%, 100%** |
| by body system | ~11 | 94%, 95%, 99%, 95% |
| by frequency group | ~5 | 99%, 99%, 99%, 99% |

- **Asking for 185 items in one call returns 185.** Three of four runs perfect;
  the fourth dropped one term (`periorbital edema`).
- **No load failure.** Recall did not fall as the ask grew from 5 to 185 items.
- **The middle arm is the only unstable number, and it is our bug** — it requires
  the model to agree with our term-to-body-system assignment. The two arms
  independent of that segmentation sit at 99-100%. Third time in this project that
  the only moving number was one our own code introduced.
- **On long prose the failure mode is over-inclusion**: the single-call arm
  returned 251 items against 185 expected, pulling from postmarketing lists and
  trial tables the parser does not cover. The opposite of what the chapter claims.

### Chapter 10, settled

| case | verdict |
|---|---|
| short numeric lists | **reproduces, rarely** — 2 of 55 figures; 1 doc in 6, in 2 of 3 runs |
| long prose enumerations | **does not reproduce** — 185/185, 3 runs of 4 |

**Density beat length in every test here.** The real Amoxicillin failure was two
paediatric strengths lost from a *three-part sentence*, not from a 185-item list.
That is a sharper warning than the chapter gives.

Remaining gap, narrower than the one closed: Sertraline's list is well-formed and
written to be enumerated. Contract obligations are clauses a reader must recognise
as items at all. Different experiment, different corpus. What is dead is the simple
hypothesis "long list, therefore dropped items".

New script: `ch10-silent-omissions/prose_scale.py`.

## Chapter 3 retrieval made deterministic (Aug 2026) — and a number moved

`fix_retrieval.py` failed to replay **roughly one run in two**, non-deterministically.
Cause: it called `collection.query` directly. An approximate index does not promise a
stable top-k *membership*, and this corpus is 48 near-identical versions of six labels,
so ties are the normal case rather than the edge case. A different top-k built different
prompt text, which is a different content-addressed cache key.

Chapter 6 had already solved this with `stable_top_k` (over-fetch, then sort on
`(distance, id)`), and its docstring even noted *"Chapter 3 hit a version of this and
fixed half of it"* — chapter 3 sorted for order but not for membership.

`stable_top_k` now lives in `shared/retrieval.py`; ch06 re-exports it, ch03 uses it.
**Replay is now 6 of 6 deterministic.**

One published figure changes as a result:

| measure | was | now |
|---|---|---|
| retrieved passages superseded | 83% (15/18) | 83% (15/18) — unchanged |
| oldest label served | 7.5 years | 7.5 years — unchanged |
| **drugs where the answer changed** | **100% (6/6)** | **83% (5/6)** |

The 100% was one sample of an unstable measure; the repeatability sweep had already
recorded it moving 100 / 83 / 100 across three runs. 83% is now the reproducible value.

This mattered for publication: the README promises replaying costs nothing and needs no
key, and this script broke that promise half the time for anyone who cloned the repo.

## The corrupted-corpus test (Aug 2026) — the objection, answered

Four failures barely reproduced, and the standing objection was that FDA labels are
unusually clean. Chapters 4, 7, 8 and 10 re-run over Chapter 2's damage, applied at
load time via `CORRUPT_MODE`, seeded on drug+section so replay is deterministic.
**$2.42 total.**

| ch | measure | clean | OCR-damaged | p |
|---|---|---|---|---|
| 4 | classification accuracy | 91% | 92% | 1.00 |
| 7 | aggregate correctness | 99% | **100%** | 0.50 |
| 8 | wrong section for own quote | 3, 3, 3 /33 | 8, 2, 3 /33 | 0.50 |
| **10** | **dose figures returned** | **55/55 x3** | **46/53, 46/53, 50/53** | **0.0000035** |
| **10** | **docs with a silent drop** | **0/6 x3** | **2/6 x3** | **0.019** |

**Three of four hold. Chapter 10 does not.** On clean documents the model returned
every dose figure in every run; on the same documents with scanning damage it
dropped figures from a third of them, and the output looked complete either way.

### The correction this experiment had to make to itself

The exploratory pass reported ch08 moving 3% -> 24%, p = 0.027, and wrote it up as
the headline. **It does not exist.** The clean figure came from a *replayed
fixture* — one recorded sample — and the damaged figure was one live sample. Three
live runs of each gave clean 3,3,3 and OCR 8,2,3: pooled p = 0.50. The 24% was an
outlier and the 1/33 it was compared against was another, in the opposite
direction. Meanwhile ch10, dismissed as noise at p = 0.09, is the strongest result
in the part.

**A comparison is only as good as the weaker of its two arms, and a replayed
fixture is one sample, not a ground truth.** Holding a recorded baseline fixed
while the treatment arm varies guarantees noise reads as signal. Cost to catch:
$0.21.

### Method note

Truncation is reported separately and weakly: shortening documents drops sections
below the chapters' minimum-length filters, so denominators move (ch04 96->91,
ch10 55->36 figures). Only the OCR arm holds denominators constant and only it
supports the conclusion.

## Real OCR (Aug 2026) — Chapter 2's fix 2 finally testable, and it fails

The corpus was typeset, rendered at 105 DPI, degraded (greyscale, blur 1.0, JPEG
q28), and read back with **Apple Vision** via `ocrmac`. Real engine, real damage,
real confidence numbers. Build it with `.venv-ocr/bin/python make_ocr_corpus.py`;
use it with `CORRUPT_MODE=real_ocr`. **$0.21 of model calls; OCR is local.**

Corpus-wide word accuracy: **85.5%** across 840 lines. Roughly 1 word in 7 wrong.

### Fix 2 cannot work on this engine

**0 of 840 lines reported a confidence below 1.000.** Not one. Including a
document at **60.6% word accuracy** — two words in five wrong — which also passed
the byte-level gate. Both of the chapter's checks for scanning damage looked at
that document and said it was fine.

This is the **sixth** independent measurement that self-reported confidence
carries no signal, and the first from something that is not a language model.

Caveat that must travel with it: Apple Vision pins confidence at 1.0 in normal
operation. Tesseract emits varying per-character confidence and may support the
fix as written. The claim is *"this is a property of your engine, check before you
build on it"* — not *"OCR confidence never works"*.

### Fix 1 (byte-level gate) on genuine OCR damage

**5 of 12** documents flagged. The misses are exactly as chapter 2 predicts: OCR
errors are made of ordinary letters and leave no trace in the bytes.

### What real OCR did to the doses

| document | change |
|---|---|
| Lisinopril | `10 mg to 80 mg` -> `10 mg to **50** mg` |
| Furosemide | `80 mg,` -> `**50** mg.` |
| Furosemide | invented `0 mg`, `50 mg` |
| Amoxicillin | invented `9 mg`, `429 mg`, `7777272600 mg` |
| Lisinopril | invented `5 mg` |
| Warfarin | **lost** `1639 g` — the VKORC1 gene-variant false positive, destroyed by scanning |

`7777272600 mg` any validator catches. `50 mg` is a valid lisinopril dose and a
valid furosemide dose, and nothing downstream can tell the document said 80.

### Effect on the chapters (3 live runs each)

| measure | clean | simulated OCR | **real OCR** |
|---|---|---|---|
| ch10 dose figures returned | 100% x3 | 87, 87, 94% | 91, 91, 88% |
| **ch10 docs with a silent drop** | **0/6 x3** | 2/6 x3 | **4/7 x3** |
| ch02 silent corruption rate | — | — | 42, 44, 53% |
| ch02 model reported itself confident | — | — | 81, 83, 83% |

**Real OCR damage is worse than the simulation.** The synthetic corruption used
elsewhere in this report was, if anything, too gentle.

## Chapter 2's prescribed pre-flight checks, measured (Sep 2026)

The 85% catch rate was attributed to the section "Pre-flight input validation
before any LLM call". **That section prescribes four checks; the implementation
ran a different five.** Only the length floor overlaps. So the four were built
separately and run over the same 53 cases — pure code, no model calls, entropy
band calibrated on the clean documents only. `ch02-input-integrity/book_checks.py`.

| prescribed check | damaged caught | clean rejected |
|---|---|---|
| 1 language sanity (`langdetect`) | **0 of 41** | 0 |
| 2 character entropy | **0 of 41** | 0 |
| 3 token count bounds | 37% (15/41) | 8% |
| 4 required field presence | n/a — raw text has no fields | — |
| **all three testable, together** | **37%** | 8% |
| **the five actually built** | **85%** | 17% |

By damage type, the prescribed checks catch: truncation 100% (token bounds alone),
and 0–20% of everything else. The built gate: mojibake 100%, homoglyphs 100%,
truncation 100%, OCR 50%.

### Why the two nulls happen

Both libraries work correctly; they cannot see this damage.

- **`langdetect` returned English at 0.99999 confidence** on a document carrying 65
  Cyrillic characters. It is right — the document *is* in English. Whether it is
  corrupted is a different question.
- **Entropy fails by construction.** Homoglyph substitution swaps one symbol for
  another of the same frequency, so the distribution's shape does not move.
  Damaged documents measured 4.66–4.81 bits/char against a clean band of
  4.15–4.91. **Corruption that preserves the statistics of the original is
  invisible to statistical checks.**

### A prediction on record, wrong twice

Before running it, the expectation was that langdetect would fire on the homoglyph
documents and that entropy would roughly match the mojibake regex. Both caught
nothing. The reasoning behind the prediction is the reasoning printed in the
chapter, and it is wrong for the same reason in both cases.

**Consequence:** the chapter now prints the five checks that earned the 85%, with
per-check catch rates, and explains what langdetect and entropy are actually for.

## Chapter 2's prompt template, run at last (Sep 2026)

The chapter's INPUT QUALITY PROTOCOL had never been executed — the baseline used a
plain extraction instruction, which is a demonstration of the failure, not the
chapter's fix. `ch02-input-integrity/book_prompt.py`. **3 live runs, identical
numbers every time. ~$0.30.**

| damage | flagged not CLEAN | aborted | said LOW |
|---|---|---|---|
| lookalike letters | 100% (12/12) | 0% | 0% |
| encoding damage | 100% (5/5) | 0% | 0% |
| **scanning damage** | **100% (12/12)** | 0% | 0% |
| truncation | 83% (10/12) | 0% | 0% |
| **all damaged** | **95% (39/41)** | **0% (0/41)** | **0% (0/53)** |

**The prompt out-detects the code gate.** 95% vs 85%, and on scanning damage 12/12
vs 6/12 — the damage class the gate is worst at. It also costs fewer false alarms:
8% of clean documents vs 17%.

**And it gates nothing.** Step 3 fires only on SEVERELY_CORRUPTED or LOW
confidence. Across 159 assessments the model issued neither, ever. It noticed the
damage, described it, and extracted from the damaged document anyway.

**Seventh confirmation of the self-assessment finding.** `confidence_to_proceed`
returned LOW 0 of 159 times — the same three-level self-report that returned LOW
0 of 192 times in ch04. Any step conditioned on it is unreachable code.

### The two are complementary

| caught by | n |
|---|---|
| both | 33 |
| prompt only | 6 |
| code gate only | 2 |
| **neither** | **0** |

Together: 41 of 41. Run the free gate first (85%, no model call), then the prompt
on what survives — but put the refusal in your own code, keyed on the returned
quality grade, not on the model's confidence in itself.

### A bug found on the third run

Two clean runs at `max_tokens=700`, then a mid-JSON cutoff: some damaged documents
produce a long `corruption_signals` list. Fourth token-budget overflow in this
project and the third defect to survive its first two runs.

## Every prompt in the book, audited and run (Sep 2026)

### The audit corrected itself

A text-similarity pass reported four prompts as never executed. **Three of those
were wrong** — similarity measures vocabulary, and a domain transposition changes
every noun while preserving every instruction.

| ch | similarity | first verdict | truth |
|---|---|---|---|
| 4 | 0.02 | never run | **run** as `BOOK_SYSTEM`; score collapsed on the injected category list |
| 7 | 0.17 | never run | **run**; A/B/C/D + robustness rules present, different domain |
| 5 | 0.37 | partial | **run**; dates/names swapped for frequency/duration |
| 8 | 0.03 | never run | **correct — genuinely never run** |

The metric answered a different question from the one asked, which is the same
failure as `langdetect` and as every self-assessment field in the book.

### The three genuinely untested prompts, now run

**ch02** (3 runs, identical): flags 95% of damaged documents — 12/12 on scanning
damage vs the code gate's 6/12 — and refuses to extract from **0 of 41**.
`confidence_to_proceed` = LOW **0 of 159**.

**ch08** (3 runs): placement error 3%, 3%, 0% — no gain on the plain prompt.
**97% of fields graded HIGH every run**, and the machinery flagged **0 of the
misplaced fields**.

**ch10** (3 runs): the COMPLETENESS PROTOCOL returns **84%, 71%, 80%** of dose
figures against **96%** for a one-line instruction and 100% on clean input. Step 1
asks the model to count the items; it was wrong on **18 of 18** documents, once
claiming 47 where 13 existed. Every later step compares against that number.

### The finding across all nine

| what the instruction asks | outcome |
|---|---|
| **restrict what may be asserted** (ch3 only-from-sources, ch6 status must be ACTIVE, ch2 scan for these signals; ch9 null-is-correct withdrawn 29 Sep — nothing to reduce) | **at least −85 pts, 67%→17%, 95% flagged** |
| **ask the model to assess itself** (ch2 confidence_to_proceed, ch4 confidence, ch8 placement_confidence, ch10 self-count) | **LOW 0/159, LOW 0/192, 97% HIGH and 0 caught, 0/18 correct** |

**Across four chapters and 400+ self-assessments, a model asked to grade its own
work returned the lowest grade zero times.**

The deeper difference: a restriction changes what the model may output and is
enforceable by the code reading the response. A self-assessment adds a field and
changes nothing — it is a claim about a claim, no more reliable than the inner one.

**Recommended shape:** let the prompt *report*, let your code *decide*. Branch on
the grade returned, never on the confidence the model assigns itself. Full template
in the report, part "Every prompt in the book, checked".

New scripts: `ch08-routing-placement/book_prompt.py`, `ch10-silent-omissions/book_prompt.py`.

## A layout bug worth recording (Sep 2026)

Adding one table to the manuscript collapsed the PDF from 186 pages to **107**,
with body text rendering at 6.66pt instead of 10pt. Nothing was lost — Chrome was
shrink-to-fitting the *entire document*.

Cause: the book's stylesheet carries `td:first-child { white-space: nowrap; }`,
because its tables are designed with a short label in column one. A full sentence
in that cell becomes one unbreakable line wider than the page, and Chrome scales
everything down to make it fit.

Two things worth carrying:

- **The failure was global and silent.** A local mistake in one cell changed the
  type size of all 186 pages. Nothing errored; the build reported success.
- **Tag balance and character counts both passed.** The HTML was valid and larger
  than before. The only way to catch it was to render and count pages.

Added to the checks: after any manuscript edit, verify the page count and the body
font size, not just that the build completed.

## Prompts rewritten to ship working, not annotated (Sep 2026)

Editorial correction, on the author's direction: an engineering fix can be listed with
"this is the standard advice and it does not work" beside it. **A prompt cannot.**
A reader copies a prompt; they do not copy a caveat. So each template is now the
version that measured well, with the removed part described *after* it as
"here is what I tried, here is what it did, try it yourself".

| ch | removed from the prompt | why |
|---|---|---|
| 2 | `confidence_to_proceed`, the Step 3 abort | LOW 0/159; aborted 0/41 |
| 4 | `confidence`, `requires_human_review` | LOW 0/192; gate caught 2 of 9 errors while holding 3 correct |
| 8 | `placement_confidence`, `requires_review`, disambiguation protocol | 97% graded HIGH incl. the misplaced field; no accuracy gain |
| 10 | the whole inventory/self-count protocol | 78% mean vs 96% for a one-line instruction; self-count wrong 18/18 |

What each prompt kept is what measured: ch2's corruption-signal scan (95%, 12/12 on
OCR damage), ch4's `runner_up` (holds the true category 67–100% of the time),
ch8's FIELD DEFINITIONS + verbatim quote, ch10's `not_extracted` (11 items, all
correct judgements).

Each section now also states **where the prompt works and where it does not** —
ch2 is for prose not structured payloads and costs a call per input; ch8 needs
fields with distinct linguistic markers; ch10 needs enumerable items and someone
who will actually read the queue.

### A sequencing error worth recording

The chapters run **Prompt template → Engineering fixes**. My first pass at ch2
referenced "the code gate" inside the prompt section — a forward reference to
something 3,700 characters later that the reader has not met. Fixed. When editing
a chapter, check that every reference points backwards.

## Chapter 7's prompt isolated from its OOD fix (Sep 2026)

`fixed.py --no-ood --live`, 3 runs, to attribute the chapter-7 regression correctly.

| configuration | aggregate correct | legitimate queries answered |
|---|---|---|
| baseline (no fix) | 99-100% (143-144/144); scored before the 14 Nov "unable to interpret" fix, the recorded run now replays 144/144 | 100% |
| **prompt only** | **144, 144, 143 of 144** | **48, 48, 47 of 48** |
| prompt + OOD gate | 83% (120/144) | 50% (24/48) |

**The prompt is the best-performing in the book. The entire regression is the
out-of-distribution gate**, which rejects a well-formed Hindi question at cosine
0.995 and takes 24 legitimate queries with it. Previously these were conflated,
and ch7's fixed arm was reported as "the fix is a regression" without saying which
fix.

## Why the bottom grade is never issued (Sep 2026) — a correction

Chapter 2 recorded `LOW` 0/53 and `SEVERELY_CORRUPTED` 0/53 and concluded the
abort branch was "unreachable". That was an observation dressed as an
explanation, and the explanation was wrong. `ch02-input-integrity/why_no_low.py`,
3 runs each:

| condition | CLEAN/DEGRADED/SEVERE | HIGH/MED/LOW | bottom grades |
|---|---|---|---|
| A grade + abort consequence | 13/40/0 | 14/39/0 | **0, 0, 0** |
| B grade only, consequence removed | 13/40/0 | 31-36/17-22/0 | **0, 0, 0** |
| C genuinely destroyed input | 3/36/2 | 3/32/6 | **10, 7, 8** |

**Arm B kills the leading hypothesis.** I assumed the model avoided the bottom
grade because that grade meant abandoning the job. Delete the abort instruction
entirely and it still never issues it. It was not dodging the consequence.

**Arm C shows the grade is reachable.** Discard 90% of a document and mojibake
the rest and the same prompt returns SEVERELY_CORRUPTED and LOW readily.

**So DEGRADED was the correct grade on damaged-but-readable documents.** The model
could still find the dose. It judged accurately and I recorded its accuracy as a
failure — the same error as the zero-width spaces.

**The real finding, which is sharper:** the abort fires only on documents that are
obviously destroyed, and those are exactly the ones a free byte-level check
already catches. The dangerous document is damaged enough to change the answer
and not damaged enough to look damaged; on those the model correctly says
DEGRADED and the stop condition correctly does not fire. **Do not put a stop
condition on the bottom of a scale the model reserves for catastrophe.**

Side effect worth noting: removing the consequence made the model *more*
confident — HIGH went from 14 of 53 to 31-36 of 53. With nothing riding on the
grade, it grades itself higher.

---

## §G — Correction: the ground truth itself (Sep 2026)

Chapters 3 and 9 both derive ground truth by withholding sections: supply two of a
label's sections, ask about six, treat the four withheld as unanswerable. That is
only sound if the two supplied sections say nothing about the withheld topics.

They sometimes do. Levothyroxine's `dosage_and_administration` carries a paediatric
dosing table under its own heading (*"0 to 3 months, 10 to 15 mcg/kg/day"*) and
explicit pregnancy guidance (*"measure serum TSH and free-T4 as soon as pregnancy
is confirmed"*). A model answering those questions is reading the document. It was
being scored as fabricating.

`shared/contamination.py` excludes those cases on a structural test — an explicit
subsection heading naming the withheld topic, found in the supplied text. No model,
no reading for meaning. The test is deliberately narrow, so the excluded set is a
floor: Omeprazole's OTC label says *"children under 18 years of age: ask a doctor"*
without a heading, and is not caught. Corrections below are therefore conservative.

**14 of 48 (label, withheld-topic) pairs are contaminated**, across 9 of 12 labels.

| figure | published | corrected |
|---|---|---|
| 3.1 plain prompt | 30% (14/48) | **6%** (2/34) |
| 3.1 soft vocabulary | 35% | **9%** (3/34) |
| 3.1 permission clause | 92% (44/48) | **88%** (30/34) |
| 3.2 grounding template, Haiku 4.5 | 23% (11/48) | **3%** (1/34) |
| 9.1 fields filled, no source | 29% (14/48) | **6%** (2/35) → 0 of 35 on 29 Sep: both are correct readings |
| 9.2 fabrications carrying a real quote | 14 of 14 | **2 of 2** → withdrawn 29 Sep: the values are real too |

Cross-model, Experiment 3.2. Baselines were at or near ceiling in the recorded
sweep, so removing 12 cases bounds them tightly; `fixed.py` was replayed directly.

| model | baseline (corrected) | fixed | drop |
|---|---|---|---|
| Claude Haiku 4.5 | 88% | 3% | −85 |
| Claude Opus 5 | 100% | 6% | −94 |
| GPT-5-mini | 97–100% | 3% | −94 to −97 |
| GPT-4.1-mini | 91–100% | 0% | −91 to −100 |

**The published −69 becomes at least −85 on every model.** Every correction runs the
same way: the baselines were inflated by cases that were never unanswerable, so the
gaps the book attributes to prompt design are wider than published, not narrower.

**One reversal, not a strengthening.** Chapter 9's `fixed.py` reaches 0% fabrication
partly by refusing to answer questions it could answer: it filled **0 of the 11**
field-instances the supplied text does cover. That is the circularity `fixed_noncircular.py`
was written to expose, now visible in the original arm's own numbers.

### Chapters audited and cleared

- **Chapter 4.** `precautions` nests `pediatric_use`, `geriatric_use` and
  `drug_interactions` in old-format labels, so 7 of 96 passages sit under two
  headings at once. `precautions` is not one of the ten selectable categories, and
  no passage appears verbatim under a second selectable one. Ground truth is
  single-valued. No change.
- **Chapter 8.** 6 of 442 sentences appear in more than one of the three sections,
  all drug-name boilerplate. The reported result was 0 placement errors; ambiguity
  here can only manufacture errors, so it manufactured none. No change.
- **Chapter 10.** One spurious figure in 55 — `3 mg/dL` serum creatinine read as a
  3 mg dose. The result was 185 of 185 returned, so it produced no false omission.
  No change.
- **Chapters 2, 6, 7.** Ground truth is structural throughout — damage the harness
  injected, timestamps, cosine distances — never an interpretation of text. Not
  exposed to this class of error.

### Chapter 5 — the same shape, a different mechanism

`RANGE_RE` required no dose unit, so it matched INR target bands (*"range, 2 to 3"*),
dosing intervals (*"every 4 to 6 hours"*), ages (*"ages 6-12"*) and time-to-effect
(*"1 to 4 days"*). On Warfarin, Albuterol and Omeprazole **every** match was one of
those: three of twelve documents were recorded as containing a dose range they do
not contain, and an extraction that correctly carried no range was scored as having
lost one.

Corrected, single run each, denominator 8 rather than 11:

| arm | ranges preserved |
|---|---|
| plain instruction | 5 of 8 |
| normalise inside the prompt | **2 of 8** |
| capture prompt + code normaliser | 5 of 8 |

**This reverses a published DROP.** The finding was *"the capture prompt preserves
fewer ranges than a prompt that says nothing"* — 85% vs 65%, behind in all 5 runs.
On the corrected denominator the two are level. What does lose ranges is
normalising inside the model call, which is the practice the chapter argues
against. The five-run spread cannot be recomputed — identical prompts collapse to
one cached fixture — so this is one run and should be re-run before it is relied on.

---

## §H — Without a source: self-consistency and token probabilities (Sep 2026)

Every Chapter 3 fix compares the answer to a supplied document. These two
probes measure what is usually proposed when there is none, on the chapter's
own corpus so the signal can be scored against known ground truth.

**Self-consistency** — `probe_selfconsistency.py`, plain instruction, five draws
per question, Claude Haiku 4.5, 34 unanswerable + 24 answerable, $0.91 + judge.

| unanswerable questions (34) | n |
|---|---|
| declined on every draw | 31 |
| split — fabricated on some draws, declined on others | 2 |
| fabricated on every draw | 1 |

Catches 2 of 34 that a single draw called safe. Misses the 1 that invents the
same thing five times. In both split cases every draw opened with the identical
correct sentence; the flip was whether an outside-knowledge sentence followed.
A facts-disagree check would not have fired; the decline/assert flip did.

**Token log-probabilities** — `probe_logprobs.py`, GPT-4.1-mini (Claude's API
returns none), plain instruction, answer tokens only (JSON scaffolding
stripped), 3 runs, ~$0.05 + judge each.

| run | fabricated n, mean | correct n, mean | best cut | caught | correct flagged | declines flagged |
|---|---|---|---|---|---|---|
| 1 | 7, −0.295 | 24, −0.083 | −0.21 | 7/7 | 1/24 | 19/27 |
| 2 | 8, −0.345 | 24, −0.098 | −0.19 | 7/8 | 1/24 | — |
| 3 | 12, −0.387 | 24, −0.099 | −0.20 | 12/12 | 3/24 | 15/22 |

The separation between fabricated and correct holds in every run and the cut
lands in the same place. But correct declines sit at about −0.25, inside the
flagged region: the signal separates *confident answers* from *everything
unsure*, and fabrications share the second bucket with refusals. Usable for
routing to review; not a fabrication detector alone. Note the fabrication count
itself moved 7 → 8 → 12 across identical runs — the same instability §R found.

**Run 4 (13 Sep 2026), and why the book shows runs 1, 3 and 4.** Run 2's
"declines flagged" was never computed — the script did not print it, and runs 1
and 3 were hand-counted from the per-question table. The probe also had no
`--sample` flag, so each `--live` run overwrote the previous fixtures; run 2's
answers are gone and the count cannot be recovered. Fixed both: `--sample N`
now folds a run index into the fixture key, and the best-cut line prints the
decline count. Run 4 recorded with `--sample 4` (~$0.05 + judge):

| run | fabricated n, mean | correct n, mean | best cut | caught | correct flagged | declines flagged |
|---|---|---|---|---|---|---|
| 4 | 8, −0.335 | 24, −0.084 | −0.18 | 8/8 | 3/24 | 17/26 |

Run 4 also exposed a harness bug: OpenAI returns `-9999.0` as a placeholder for a
token it has no probability for, and one such token (` Usage`, in a Warfarin
pregnancy decline) dragged that answer's mean to −208 and the decline group's
mean to −8.3. `answer_tokens()` now drops the placeholder. Runs 1–3 replay
unchanged after the fix. The book's table shows runs 1, 3 and 4 — the three
runs with every column recorded.

**What it found about the ground truth.** In run 1, two "fabrications" scored
−0.024 and −0.033 — the two most certain answers in the group. Both were
contamination the §G detector had missed (Metformin: heading reads "Pediatric
Dosage"; Albuterol: a labelled dosing line, not a heading). Verified against the
corpus, added to the detector, all §G figures recounted on 34. The model's own
probabilities flagged the two questions the ground truth had wrong.

Harness change: `LLM.complete()` takes `sample=` (folded into the cache key, so
repeated draws get their own fixtures instead of replaying one) and
`logprobs=` (OpenAI only; the Anthropic path refuses rather than returning
nothing).

## Chapter 4's shipped prompt, measured as its own arm (13 Sep 2026)

`ch04-classification-cascade/shipped_prompt.py --live`, 3 runs, both positions,
$2.56. The book's template was only ever measured with `confidence` and
`requires_human_review` still in it; the shipped version drops both and keeps
the reasoning steps, `runner_up` and `ruled_out_because`.

| prompt | opening | body | errors where runner_up = true |
|---|---|---|---|
| one-line (replayed) | 100% (96/96) | 96% (92/96) | — |
| full template (replayed) | 98% (94/96) | 90% (86/96) | 2/2, 9/10 |
| shipped, run 1 | 97% (93/96) | 94% (90/96) | 3/3, 5/6 |
| shipped, run 2 | 98% (94/96) | 92% (88/96) | 2/2, 6/8 |
| shipped, run 3 | 99% (95/96) | 91% (87/96) | 1/1, 7/9 |

Dropping the confidence fields recovered 1–4 body-passage points but the
template still trails the one-line prompt by 1–3 (opening) and 2–5 (body).
`runner_up` held the true category on 6/6 opening and 18/23 body errors. The
book's "What this prompt does" now prints this table; the ensemble item carries
the caveat that its gain comes from outvoting the weakest member.

## Chapter 4 fix 2, run as the chapter describes it: three systems, not three prompts (14 Sep 2026)

`ch04-classification-cascade/model_ensemble.py --live`. Members: Haiku 4.5 with the
shipped template, GPT-4.1-mini with the one-line prompt, `facebook/bart-large-mnli`
zero-shot on CPU. Majority vote; all-three-disagree goes to review. 3 runs each
position. ~$2 per run set on Haiku (the fixture key did not replay across scripts,
so Haiku re-sampled — twice; noted, not fixed), $0.11 on GPT-4.1-mini, $0 for bart.

| | Haiku shipped | GPT-4.1-mini one-line | bart zero-shot | ensemble shipped acc | to review | wrong shipped |
|---|---|---|---|---|---|---|
| opening | 99/99/97 | 97/97/99 | 59 | 99/99/98 | 2/2/0 | 1/1/2 |
| body | 93/93/93 | 96/96/94 | 59 | 96/96/94 | 1/2/1 | 4/4/6 |

bart scored 41% with bare category names as labels and 59% with the category
descriptions (the script's default since 14 Nov 2026; `ZS_LABELS=names` replays the 41% run); the table uses 59%. All three members
agreed on 57–60% of passages. **The real ensemble matches its best single member
and does not beat it.** The published prompt-ensemble figure (97–100%, bit-identical
reruns) was two strong prompts outvoting the weakest; it does not describe a
model ensemble and the book no longer prints it as one. The disagreement lane
sent 0–2 of 96 to review, and that lane is now presented as the working form of
fix 3 (confidence-gated routing), which is folded into fix 2 in the manuscript.
Chapter 4's fixes are reordered by result: F1 gate, audit trail, ensemble.

## Chapter 5, three follow-ups (15 Sep 2026) — `ch05-extraction-normalisation/more_experiments.py`

$1.13 total (Haiku $0.77, Sonnet 5 $0.35, GPT-4.1-mini $0.01).

**A. Five runs each, corrected range counter.**

| prompt | ranges kept (of 8) | qualifiers kept | values findable (values returned) |
|---|---|---|---|
| plain | 4,5,5,4,5 | 42,37,34,39,34% | 71,58,68,59,63% (59–63) |
| normalise inside the prompt | 3,3,4,2,1 | 18,26,21,24,21% | 61,59,59,68,62% (61–74) |
| capture | 5,5,5,5,5 | 39,34,50,39,32% | 92,92,96,94,92% (72–80) |

Ranges: capture 5/8 every run, plain 4–5, one-prompt 1–4 — the §G single-run
reading holds. Qualifiers: capture vs plain no consistent difference (ahead 1,
behind 3, level 1); the one-prompt version keeps ≤26%. Findable: capture never
below 92%, plain never above 71%. The capture prompt returned *more* values
(72–80) than plain (59–63), so its findable gain is not a denominator effect.

**B. Retries.** 376 dose/frequency values from the capture prompt; 117 (31%)
unparseable by `normalise.py`. Feedback retries fixed 5 + 3 + 0 = 8. The other
109 are absences ("not specified", "adjust if necessary", tapering prose), not
formats. Retries fix formats; they cannot supply a number the label lacks.

**C. Model swap.** Capture prompt once on Sonnet 5 and GPT-4.1-mini vs the Haiku
run: same normalised value per field 45–67% (Sonnet) and 42–83% (GPT); 3 and 2
fields missing. Raw-value agreement 8–67%. The golden-set item's previously
unsourced claim ("format regressions after model updates") now has a measurement.

**Pipeline diff (recorded runs, no cost).** Same normaliser over both pipelines'
outputs, 45 dose/frequency fields in both: 8 same; 13 one-prompt lost the unit
("80", "1"); 1 one-prompt invented a maximum (Prednisone 60 mg); 4 numbers
disagree; 19 neither parseable (no dose in the label). 6 fields only one-prompt,
3 only capture.

---

## 17. Chapter 6 — the context-integrity block, measured (16 Sep 2026)

Built the three failures the block names and ran status-only vs status+block,
5 runs × 6 drugs, Haiku 4.5, `ch06-state-mismatch/fix_integrity.py`. $0.46.

- Wrong drug's ACTIVE label in context: its dose used **0/30** either way.
- Two ACTIVE labels that disagree (doses doubled by code): conflict reported
  **30/30** either way — the schema has a `conflict` field, so credit the schema.
  Without the block the model gives both doses 25/30 and the doubled one alone
  3/30 (1,1,1,0,0); with it, no dose 22/30 (4,5,4,5,4), doubled-alone 0.
- Correction in conversation: corrected value used 27/30 → 30/30; the
  corrected-away value never.

The block prevents none of the mistakes it names on this model; it changes the
post-conflict behaviour to refusal. Manuscript bullet rewritten with these
numbers; earlier text said "nothing measured here says they help".

---

## 18. Chapter 6 — no prompt substitutes for a status field (17 Sep 2026)

`ch06-state-mismatch/fix_nostatus.py`, 60 calls, $0.19. Date-only headers,
neutral vs "newest wins". Superseded label used 20/30 in both arms, identical
per run. 15/15 where the current label was not retrieved (3 of 6 drugs): the
prompt cannot know. 5/15 where it was: all Sertraline, whose newest retrieved
label has no starting-dose text, so the model answered from the older label
that did and said so. "Relied on newest" 9/30 → 25/30: the rule moved the
citation, not the answer. As-of date 30/30 in both arms — schema field.
Manuscript: Prompt 6-2 added under "When there is no status field" with these
results; fix 1 gains "derive the flag at ingest".

---

## 19. Chapter 6 — the newest-date monitor, finally run (17 Sep 2026)

Fix 2 recommended it without measuring it. `fix_monitoring_date.py`, no model
calls: arrival recall 32/40 vs overlap's 20/40, 0/1,381 false alarms; the extra
12 are new labels entering a not-yet-full top-3 (overlap detects displacement,
not arrival). As a stall alarm: healthy gaps 1–274 weeks (median 24), so
"stops advancing" fires 35/24/19/6 times in healthy operation at 4/13/26/52-week
windows. Manuscript fix 2 rewritten: use the date as the arrival detector, do
not use it as a stall alarm, detect stalls at ingestion. Also corrected a
sentence claiming the overlap monitor reads dates; it reads IDs only.

---

## 20. Chapter 6 — scenario 3 measured (17 Sep 2026)

`fix_memory.py`, 90 calls, $0.08. Memory alone disagrees with the current label
for 2/6 drugs every run. With the document in context and told to follow it:
0/30 non-label doses; changed-document arm: document won 18/30, memory 0/30,
6 withheld, 6 undecidable (doubled value coincides with a real value — a
scoring limit of the doubling trick, noted). Manuscript: scenario 3 gets a
measured paragraph; the chapter previously had no fix and no number for it.

---

## 21. Chapter 6 — scenario 2, the model's half (17 Sep 2026)

`fix_reconcile.py`, 90 calls, $0.15. Told: new-only 28/30, stale 0. Not told:
25/30, stale 0, 3 withheld. Noted a change 30/30 both — schema field. The
reconciliation is easy once the re-read has happened; fix 7's value is entirely
the re-read. Production rate of the gap is not measurable here and the chapter
now says so. Manuscript: fix 7 gains "Measured here, the model's half"; fix 9
(scenario 3) added; scenario bullets updated.

---

## 22. Two Chapter 6 fixes moved to Chapter 2 (19 Sep 2026)

History truncation and session isolation are input failures, not timing failures: a context cut mid-sentence is
partial input, another customer's data in the context is contaminated input. Both now sit in Chapter 2 as fixes 7
and 8 with their issue described there; the tenant figure is Figure 2-3. Chapter 6 keeps a brief fix 3 for the
write side (check the destination belongs to the customer). Chapter 6 fixes renumbered 1–8. Code stays in
`ch06-state-mismatch/`.


## Chapter 7 — an off-the-shelf injection scanner, measured (23 Sep 2026)

The chapter's injection fix names LLM Guard and Azure Content Safety and then
measures an eight-line regex. `ch07-edge-input/probe_llmguard.py` runs LLM Guard's
`PromptInjection` scanner (`protectai/deberta-v3-base-prompt-injection-v2`, library
default threshold 0.92, on the local machine, no API) over the same 144 cases, on the query
and on the document. Python 3.10+ in its own venv; the rest of the repo is 3.9.

| | full (default) | chunks |
|---|---|---|
| injection attempts flagged (query or document), of 48 | **37** | **48** |
| `inj_spanish` flagged on the query, of 12 (regex: 0) | 12 | 12 |
| `inj_buried_doc` flagged on the document, of 12 | 1 | 12 |
| legitimate inputs wrongly flagged, of 96 | **24** | **24** |
| `ood_hindi` flagged, of 12 | **12** (risk 1.00) | 12 |
| `ood_numeric` flagged, of 12 | 12 | 12 |
| `ood_long` (padded) flagged, of 12 | 0 | 0 |
| any document wrongly flagged | 0 | 0 |
| time per scan, Apple M5 Pro, library default device (GPU, mps) | 45 ms | 79 ms |
| time per scan, same machine, CPU only | 80 ms | 236 ms |

**Finding.** The model scanner has the recall the phrase list lacks — every Spanish
attempt, and in chunk mode every buried payload — and it flags every Hindi question
as an injection at maximum confidence: the embedding-gate failure again, from a
different model. The default match type misses payloads past the first 512 tokens;
for documents, chunk mode is the only usable setting. On this corpus the regex plus
the prompt's refusal rule already gave 0/48 obeyed with no Hindi refusals, so the
extra recall added nothing the pipeline needed. A scanner model can log and route;
it must not refuse on its own. Azure Content Safety remains untested (paid API, key
required).


## Chapter 8 — the rules engine, measured on planted misplacement (24 Sep 2026)

Nothing was misplaced on the labels (§3), so `fixed.py`'s rules engine had nothing
to catch. `ch08-routing-placement/probe_planted.py` builds the failure on purpose,
as Chapter 6's context-integrity test did: it replays the recorded outputs and
swaps quote and value between two boxes by code, every pair once — 11 cases × 3
swaps = 33 variants, 66 planted misplacements, 33 untouched boxes. No model calls.

| locator window | planted | caught | missed | untouched | false rejections |
|---|---|---|---|---|---|
| 80 chars (as shipped) | 66 | **65** | 1 | 33 | **1** |
| 200 chars | 66 | 66 | 0 | 33 | 4 |
| whole quote | 66 | 66 | 0 | 33 | 6 |

All 66 rejections at the shipped window were "quote came from X, not Y" — the
placement check itself. The one miss and the one false rejection are the same
boilerplate artefact as §3 (first 80 characters shared across sections). The
longer windows fix recall and pay in unfindable-quote rejections, exactly the
two-way tension §3 describes. **Finding:** the detector works when there is
something to detect; the null result is about the corpus, not the check.


## Chapter 8 — the prompt on a corpus where misplacement is possible (24 Sep 2026)

`ch08-routing-placement/probe_hardcorpus.py`: headings removed, the three
sections' sentences shuffled together (fixed seed per drug), so the model must
route by content alone. Plain prompt vs Prompt 8-1 as printed, three live draws
each (`sample=1..3`), 66 calls, $0.35.

| prompt | run | misplaced (80-char locator) | no match (80) | no match (whole quote) |
|---|---|---|---|---|
| plain | 1, 2, 3 | 1, 1, 0 | 0, 1, 1 | 18, 19, 18 |
| chapter | 1, 2, 3 | 0, 0, 0 | 3, 0, 0 | 16, 16, 14 |

Every flagged row was read. The plain prompt's two "misplaced" boxes are the
Amoxicillin contraindication whose quote opens with the drug-name boilerplate
(§3's artefact); the content is a contraindication, correctly placed. Every
"no match" is correctly placed content whose quote joins sentences that are not
adjacent in the source, so the locator cannot find it — which is also why the
whole-quote window cannot score this corpus. **Real misplacements: 0 of 33, every
run, both prompts.** On a drug label the sections differ in meaning; the model
separates them without headings. A note's sections differ by convention (the
same BP belongs in HPI and in A/P), which these documents cannot pose. The
chapter says so; Prompt 8-1 still cannot be credited with placement accuracy.

## Chapter 8 — provenance record demonstration (24 Sep 2026)

`ch08-routing-placement/demo_provenance.py`: a two-stage pipeline in code with
the record switched on; four faults planted per label (merge fault, generator
fault, duplicate, no record). The record names every cause, 11 of 11 each — by
construction, and the book does not print it as a rate. What the demo shows is
the second table: with only the quote check, merge fault, generator fault and
duplicate all read "wrong section, cause unknown", and "no record" looks fine.


## Chapter 8 — placement by convention: generated shipping documents (24 Sep 2026)

`ch08-routing-placement/probe_convention.py`. The document Prompt 8-1 was written
for: three addresses (origin, destination, billing), same kind of content in
three roles. 36 GENERATED documents with exact ground truth, three levels: L1
explicit labels; L2 varied labels per document (Sender/Consignee/Payer, From/To/
Invoice to, ...); L3 no labels, a header states the order, half reversed. Three
prompts: plain; Prompt 8-1 as printed (loaded from draft/ebook.html); Prompt 8-1
plus placement_confidence and requires_review. Three live draws each (`sample`),
324 calls, $0.60. (The helper reported 108 "duplicate requests": the first live launch crashed on the chapter prompt after recording the plain prompt's 108 calls, and the relaunch re-recorded them. Each draw has its own fixture, and replay reproduces the live table exactly.)

| prompt | L1 misplaced / other | L2 misplaced / other | L3 misplaced / other |
|---|---|---|---|
| plain | 0 / 0, 0, 0 | 0 / 6, 9, 3 | 0 / 0, 0, 0 |
| chapter | 0 / 0, 0, 0 | 0 / 3, 0, 0 | 0 / 0, 0, 0 |
| graded | 0 / 0, 0, 0 | 0 / 0, 0, 0 | 0 / 0, 0, 0 |

(of 36 fields per level per run; 324 fields per prompt over three runs, 972 in all)

Grade on the graded prompt, all fields: HIGH 312, MEDIUM 12, LOW 0; requires_review
set on 9 of 108 records. Every MEDIUM and every review flag was on a correct field.

**Finding.** Third null. A single extraction call given a whole, clean document
does not misplace, whether sections differ by meaning (labels) or by convention
(addresses), even position-only. The field definitions appeared to reduce *empty* fields on unfamiliar labels — WITHDRAWN 25 Sep: a company-only scorer artefact, see the 25 Sep entry. The grade cannot be judged
against errors here because there were none; what it did was raise nine false
review flags. The failure the studies measure has two things none of these
experiments had: a **merge step** that files generated pieces into a document,
and **real clinical sentences** that belong in two sections by convention. That
is the experiment to run next (ACI-Bench / PriMock57 reference notes give real
sentences with known sections).


## Chapter 8 — placement on real clinical notes (24 Sep 2026)

`ch08-routing-placement/probe_clinical.py`. The corpus the failure needs: 60
reference visit notes from ACI-Bench (`data/aci_bench_notes.json`; Yim et al.,
Nature Scientific Data 2023, CC BY 4.0; 20 per subset: aci, virtassist,
virtscribe). Each note divided into subjective / objective_exam /
objective_results / assessment_and_plan with the MEDIQA-Chat 2023 section
tagger's rule (re-implemented from its header lists; identical spans on all 207
notes). VITALS blocks excluded (the tagger files them under subjective by
position). Sentences shuffled, headings removed, the model files each sentence
under one of the four headings. Ground truth: the author's section; a sentence
whose exact text sits in two divisions (46 of 2,070) is correct under either.
2,070 scored sentences. Four prompts × three draws, 720 calls, $1.98, 8 workers.
(24 "duplicate requests" = the NOTES=2 smoke test's fixtures, re-recorded by the
full run; replay reproduces the live table exactly.)

| prompt | misplaced r1 / r2 / r3 (of 2,070) | duplicate | missing |
|---|---|---|---|
| plain (four headings) | 375 (18.1%) / 366 (17.7%) / 381 (18.4%) | 3 / 2 / 0 | 33 / 39 / 32 |
| defined (+ section definitions) | 286 (13.8%) / 268 (12.9%) / 256 (12.4%) | 0 / 0 / 3 | 12 / 16 / 16 |
| graded (+ confidence per sentence) | 271 (13.1%) / 266 (12.9%) / 269 (13.0%) | 0 / 0 / 0 | 3 / 3 / 3 |
| tagged (each sentence carries its section) | 1 / 0 / 1 | 0 / 0 / 0 | 3 / 2 / 1 |

By subset (plain, three runs summed): aci 163/1857 (8.8%), virtassist 332/2091
(15.9%), virtscribe 627/2262 (27.7%). Where the plain prompt's misplacements
went (summed): subjective→A&P 341, subjective→exam 198, A&P→results 172,
A&P→subjective 165, subjective→results 124, A&P→exam 77. Stability: of the 462
sentences misplaced at least once, 283 in all three runs, 94 in two, 85 in one.

Grade (graded prompt, 6,201 graded placements over three runs): HIGH 5,048
correct / 560 misplaced; MEDIUM 322 / 203; LOW 25 / 43. Share misplaced: HIGH
10.0%, MEDIUM 38.7%, LOW 63.2%. A queue on "below HIGH": 593 flagged, 347
correct, 246 of 806 misplaced caught (30.5%). requires_review (180 note-runs):
set on 117 with an error and 8 without; not set on 36 with an error and 19
without (153 note-runs had at least one error).

**Finding.** The failure reproduces as soon as the sections are decided by
convention: ~1 in 6 sentences filed elsewhere by words alone; definitions
remove about a third; the section tag removes it (1, 0, 1). The rate is a
property of the notes, not the model (8.8% → 27.7% across subsets of one
benchmark). Most misplacement is history ↔ assessment-and-plan, then ROS lines
that read like exam findings; 61% of misplaced sentences are stable across runs
(convention, not sampling). The confidence grade carries signal for the first
time in the repo — LOW appears, and the error rate rises with each lower grade —
but 7 in 10 misplaced sentences are graded HIGH, so a queue keyed on the grade
misses most errors and fills with correct ones. The plain prompt also drops
sentences (33/39/32 per run): Chapter 10's failure inside a merge step.
Not measured: the generation step (sentences were the note's own, not a
model's). Book: Chapter 8 test section, provenance "Measured here", "What did
not survive testing", fixes 2–3, takeaways; Chapter 2 and 12 echoes corrected
("never returned its lowest grade" → first two tasks only; "Nothing, in four
chapters" → "Little"); Experiment 8.2's "3–15% wrong section" withdrawn as the
80-character artefact.


## Chapter 8 — shipping documents, level 4, and a scorer artefact of my own (25 Sep 2026)

`probe_convention.py` gained a fourth level: no role labels and no order line,
sender first in half the documents, recipient first in the other half. 48
documents now; 432 calls, $0.79. Two corrections to the 24 Sep entry:

1. **The "empty fields" claim was a scorer artefact.** The judge matched the
   company name only; the plain prompt at level 2 returned correct addresses
   *without* the company line ("22 Tannery Walk, Chester 4423"), which scored
   as "other" and was written up as "left empty". Scored on company OR street,
   every prompt filled 108 of 108 fields at every labelled level. The field
   definitions changed nothing where labels were present. Withdrawn from the
   book, the READMEs and this file's earlier table.
2. **`--live` re-recorded levels 1–3** (the helper re-calls the API for every
   request in live mode; 324 "duplicates"). The earlier draws are gone; the
   numbers below are the recordings on disk. Fix: `--live missing` now records
   only requests with no fixture.

| prompt | L1 misplaced (r1, r2, r3) | L2 | L3 | L4 misplaced | L4 null |
|---|---|---|---|---|---|
| plain | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 | 12, 12, 12 | 0, 0, 0 |
| chapter (Prompt 8-1) | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 | 12, 15, 11 | 4, 2, 5 |
| graded | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 | 12, 12, 12 | 2, 3, 2 |

(of 36 fields per level per run)

Level 4, what happened: both prompts assumed sender-first; every recipient-first
document had origin and destination swapped (6 docs × 2 fields = 12 a run).
Prompt 8-1's "fill only from text carrying its keywords, null otherwise" rule
produced null on 11 of 108 fields (mostly billing) and did not stop the guess.
Grade at level 4 (graded prompt, 108 fields): HIGH 2 correct / 2 misplaced;
MEDIUM 36 / 34; LOW 27 correct / 0 misplaced / 7 empty. `requires_review` set
on all 36 records (21 with an error, 15 without). Levels 1–3 correct fields:
HIGH 306, MEDIUM 18, LOW 0.

**Finding.** On label-decided documents the prompt's definitions change
nothing while labels are present (a plain prompt reads ordinary labels as
well) and do not stop the model when labels are absent: it fills the roles by
convention, like the plain prompt, and is wrong whenever the convention is.
What works there is the flag: with no labels the model marks nearly every
field MEDIUM/LOW and flags every record — it can see that the document gives it
nothing, even though it cannot say which guess is wrong. Contrast the clinical
notes (8.6), where it could not see that its convention was wrong. Book:
Chapter 8 now carries two prompts — 8-1 (labelled forms, this test) and 8-2
(the clinical merge-step prompt that 8.6 ran, printed for the first time).


## Chapter 8 — shipping documents, the "role stated?" prompt (25 Sep 2026)

Prachi asked whether the model could be made to name the wrong *fields* rather
than mark the whole document down. `probe_convention.py` gained a fourth prompt,
`evidence`: Prompt 8-1 plus, per field, `role_stated` (true if the document says
in words which address plays this role — a label or an order line — false if
decided from position or convention), the grade, and `requires_review` when any
field is unstated or LOW. 144 calls with `--live missing`; nothing re-recorded.

| level | role_stated=true (correct / wrong) | role_stated=false (correct / wrong) | requires_review, of 36 |
|---|---|---|---|
| L1 plain labels | 108 / 0 | 0 / 0 | 0 |
| L2 varied labels | 105 / 0 | 3 / 0 | 3 |
| L3 order line only | 82 / 0 | 26 / 0 | 9 |
| L4 nothing | 0 / 0 | 50 / 58 | 36 |

Misplaced at L4 with this prompt: 12, 12, 12 (the same swaps); null 8, 8, 6.

**Finding.** The model can report, field by field, that the document did not
state the role — 108 of 108 at L4, and every "false" at L2–L3 sat on a correct
field — but it cannot report which guess is wrong, because nothing in the
document says; it filled the unstated fields anyway and swapped the same twelve
a run. The actionable output is `role_stated=false`, which code can turn into a
null or a review, whatever grade accompanies it. Book: one paragraph at the end
of Prompt 8-1's "What this prompt does"; the fuller-version sentences for both
prompts are now printed in the prompt intros.


## Chapter 8 — what a strict schema guarantees, measured (25 Sep 2026)

`ch08-routing-placement/probe_schema.py`, Experiment 8.7. Fix 1 ("strict JSON
schema with enum-constrained field names — the model cannot invent field names
or cross-populate them") had never been compared with its absence, because every
run in the repo enforces a schema. Plain prompt (headings only), 60 ACI-Bench
notes, one draw per condition; 193 calls (73 live, 120 replayed), $0.40.

| condition | not JSON | extra keys | unknown IDs | duplicates | missing | misplaced (of 2,070) |
|---|---|---|---|---|---|---|
| free — no schema, code parses the reply | 0 | 0 | 0 | 2 | 8 | 376 |
| schema — JSON schema enforced by the API (8.6's draw 1) | 0 | 0 | 0 | 3 | 33 | 375 |
| validated — schema + Pydantic validator (every ID exactly once) + re-ask, max 2 | 0 | 0 | 0 | 0 | 0 | 383 |

13 of 60 outputs failed the validator at first; all 13 were fixed by one re-ask
(73 live calls = 60 free + 13 re-asks; the schema condition replayed 8.6).

**Finding.** On this task the model never invented a key or an ID, with or
without the schema, so the guarantee fix 1 sells was not exercised. The schema
call dropped *more* sentences (33) than the free call (8) — one draw each, so
treat the direction with care, but the schema clearly does not keep sentences.
What did keep them was the validator-and-re-ask loop (the mechanism Instructor
automates): 0 duplicates, 0 missing, at 13 extra calls in 60. None of the three
touches misplacement. Fix 1 in the book now says this ("Measured here") instead
of "not measured".

Instructor itself: see "Instructor on ten notes" (14 Nov 2026) below. The line that stood here ("a valid filing returned for each") had no script or recording behind it.

Experiment 8.6, counted 29 Sep 2026: the VITALS exclusion removed 27 sentences in 15 of the 60 notes (2,070 scored).

---

## Chapter 9 re-read (29 Sep 2026) — the corrected baseline holds no fabrication, and 9.3's zero is forced

**Manuscript changed in the same pass.** Every case below was opened by replaying
the committed fixtures (`broken.py`, `fixed.py`, `fixed_noncircular.py`,
`fix_provenance.py`); no live calls.

**9.1 and 9.2 — the two survivors of §G are correct readings.**

- *Furosemide, `drug_interactions`.* Value: reduce the dose of other
  antihypertensives by at least 50 percent. Quote, from the supplied
  `dosage_and_administration`: "the dosage of other agents should be reduced by
  at least 50 percent when furosemide tablets are added to the regimen". The
  supplied text states it; §G's heading test cannot see it.
- *Omeprazole, `pediatric_dosage`.* Value: "children under 18 years of age: ask a
  doctor" — verbatim from the supplied OTC directions. §G already names this case
  as a miss of its own detector and it was still counted.

Corrected: **0 fabrications in 35** on the plain prompt. "2 of 2 carried a real
quote" is withdrawn — the quotes are real because the values are. On 12 FDA
labels with Claude Haiku 4.5, sparse field fabrication **did not reproduce**: a
schema that forced a string into every field got "N/A" on all 33 fields the
supplied text did not cover.

**9.3 — the fabrication side is forced again.** `enforce()` keeps a value only if
its quote is located in `SUPPORTING_SECTIONS[field]`, and each field has one
supporting section. The six unanswerable fields are exactly the ones whose
supporting section is absent *from that label*, so their quotes can never be
located there: **0 of 6 is arithmetic.** The script's note "the check CAN pass
here — the supporting sections exist for other drugs in the same run" reasons
about the corpus; the check runs per document. Only the recall side measures
anything. Note corrected in `fixed_noncircular.py`; the printed notes in `broken.py` and `fix_provenance.py` now carry the same corrections (their numbers are unchanged, their claims withdrawn).

**9.3 recall — the ten losses, each opened.**

| cause | n | cases |
|---|---|---|
| section rule rejected a correct children's dose | 5 | Metformin, Atorvastatin, Albuterol, Gabapentin, Furosemide — every quote sits in `dosage_and_administration` |
| quote not matched in the document | 1 | Atorvastatin `drug_interactions` (not opened further) |
| model returned null | 1 | Levothyroxine `pediatric_dosage` (not opened further) |
| correct null, counted as a loss | 2 | Lisinopril — its `pediatric_use` concerns neonates exposed in utero and states no dose; Amoxicillin — a paediatric suspension, "Experience … in adults is not available" |
| scorer artefact | 1 | Gabapentin `drug_interactions` — a complete interaction list, kept by the check, scored as declined because it contains "does not" (`ABSENCE_MARKERS`) |

The five rule losses are a wrong map, not a model error: 21 CFR 201.57(c)(9)(iv)
says "appropriate pediatric dosage information must be given under the 'Dosage
and Administration' section". Recall is at least 33 of 40 answerable fields; the
rule itself cost 5. The report's loss table listed 8 of the 10.

**Fix 4 (embeddings) measured no fabrication.** `fix_provenance.py` counts
`present == False and not declined` as a fabrication without the §G exclusion.
Its 12 "fabrications" are the 10 contaminated fills plus the two above — all
correct values. The top-scoring one (0.85) is Albuterol's children's dose. "0.85
vs 0.55" and the threshold sweep are withdrawn as evidence.

**Fix 3 (null rate) — "0% vs 100%" measured two schemas.** The baseline schema
requires a string, so "N/A" is never null; the fixed side's nulls on withheld
fields are forced by the code check. Not evidence. Never tested as a monitor.

**Fix 1 (optional fields, no defaults)** was never isolated, and the filler-phrase
validator the chapter describes was never built.

**Prompt 9-1 as printed was not the prompt that ran.** It lacked "A null field
is a correct answer, not a failure." and said "ANY OPTIONAL FIELD" where
`fixed.SYSTEM` says "ANY FIELD"; a merge step had also broken its line structure.
The book now prints `fixed.SYSTEM` without its `source_section` instruction, which
the code records and never uses.

**What the book says now.** Chapter 9's box uses outside measurements (Ontario
Auditor General 2026, 9 of 20 approved AI-scribe systems; Fox et al. 2026, 2 of 3
deployed scribes wrote examinations for telephone consultations; Taylor et al.
2026, 41 of 356 notes); the body prints the null result, and Asgari et al. 2025 is
the outside evidence for permitting "unknown". Chapter 3's pointer, Chapter 12's
"6% to zero" and *Where the Numbers Come From* follow.

*Box revised 30 Sep 2026 at the author's review.* The three figures above counted
hallucination anywhere in a note (Ontario, Taylor) or history filed as
examination (Fox, telephone consultations — Chapter 8's pattern), not a field the
source left empty. The box now carries two external measurements that do: Fox et
al. 2026, invented patient identity — "where a name is inaudible or a sex never
stated, the note supplies one and uses it throughout", 34 of 142 consultations,
all three products; and Banerjee et al. 2024 (arXiv 2406.06496) — 52% (95% CI
48.95–54.23) of chest X-ray reports from a research model on the MIMIC-CXR test
set (1,383 studies) referred to a prior exam it never saw. Ontario and Taylor
were removed from the references. *Same day, the author's final choice:* Banerjee was
replaced by this repo's Experiment 9.4 ("No known drug allergies" in 4, 3, 4 of 58
notes; 0 in every run with the "Not discussed." rule), labelled as the companion
repository; the Banerjee reference was removed.

**Open.** The failure needs a template that asks for more than the source
contains — a note written from a conversation. ACI-Bench's dialogues (the repo
holds only its notes) with a full note template are the test to run.

---

## Chapter 3 re-read (29 Sep 2026) — the Sertraline "fabrication" is a correct reading

**Manuscript changed on 29 Sep; see the recount at the end of this section.** Opened by replaying
the committed fixtures; no live calls.

The question "Which other drugs interact with Sertraline Hydrochloride?" is scored
unanswerable because `drug_interactions` is withheld. The supplied
`dosage_and_administration` carries two subsections that answer it: "Switching a
Patient To or From a Monoamine Oxidase Inhibitor (MAOI) Intended to Treat
Psychiatric Disorders" and "Use of Sertraline Hydrochloride With Other MAOIs Such as
Linezolid or Methylene Blue". The model's answer (MAOIs, linezolid, intravenous
methylene blue) and all three of its quotes come from there. `shared/contamination.py`
misses it because neither heading contains the words "drug interactions".

Where it is counted as a fabrication:

| run | as scored | the Sertraline case | other residual cases |
|---|---|---|---|
| neutral prompt (broken.py) | 2 of 34 | counted | Lisinopril pregnancy (not opened here) |
| soft words (broken.py) | 3 of 34 | counted | 2 not opened here |
| soft inference / permission clause | 30 of 34 | counted | — |
| Prompt 3-1, Haiku 4.5 | 1 of 34 | the only one | none |
| Prompt 3-1, Opus 5 | 2 of 34 | counted | Omeprazole pediatric: "The source does not provide a pediatric dose … for children under 18 ask a doctor" — a decline written as an answer |
| Prompt 3-1, GPT-5-mini | 1 of 34 | the only one | none |
| Prompt 3-1, GPT-4.1-mini | 0 of 34 | — | — |
| self-consistency, five draws | "fabricated on every draw: 1" | **is** this case | the two split cases (Lisinopril and Atorvastatin pregnancy) are real |

Consequences for the book:

- **Prompt 3-1 produced no fabrication on any of the four models.** "3%, one question
  in thirty-four … all fell between 0% and 6%" counts correct readings.
- **The quote-existence paragraph has no case left.** "A drug-interactions claim …
  that the supplied label does not make … the model does not invent quotes; it
  attaches real text … to a claim the source does not support" — the label makes
  the claim.
- **The self-consistency conclusion is inverted.** The answer "repeated every time"
  that the method "missed" is correct; the method flagged both real fabrications
  and let the correct answer through. That a fabrication repeated word for word
  cannot be flagged remains true by design, but it was not observed.
- **Plain-prompt 6% (2/34) includes this case**; so does soft-words 9% and the
  permission-clause 88%. Omeprazole's OTC "children under 18 years of age: ask a
  doctor" is a second detector miss (Chapter 9 re-read above).

**Class fix, applied 29 Sep 2026 (Prachi chose the full recount).** `TOPIC_HEADINGS`
gained the two verified shapes (a "Use of X With …:" co-administration heading; an
OTC "children under N years of age:" line). Each matches exactly one label in the
twelve. Covered (label, topic) pairs: 14 → **16**. `fix_judge.py` and
`fix_similarity.py` never applied §G at all: they now skip covered questions and
count an answer to an unanswerable question as ungrounded only if the pinned
classifier judged it ASSERTED (a correct decline is neither a catch nor a miss).
Every figure below is a replay of committed fixtures.

| figure | printed | recounted |
|---|---|---|
| unanswerable questions (Ch 3) | 34 | **32** |
| 3.1 plain prompt | 6% (2/34) | **3% (1/32)** — Lisinopril pregnancy |
| 3.1 soft words | 9% (3/34) | **6% (2/32)** — Prednisone adverse reactions, Lisinopril interactions |
| 3.1 permission clause, Haiku 4.5 | 88% (30/34) | **91% (29/32)** — Furosemide's answer opened it: it goes "beyond the label" |
| permission clause, Opus 5 / GPT-5-mini / GPT-4.1-mini | 100% / 97–100% / 91–100% | **100% / 100% / 94%** (one recorded run each) |
| 3.2 Prompt 3-1, four models | 3%, 6%, 3%, 0% | **0% on all four** |
| recall on answerable, four models | — | 88%, 92%, 96%, 100% (unchanged) |
| 3.4 five draws | 31 / 2 / 1 of 34 | **30 / 2 / 0 of 32** |
| 3.5 logprobs, GPT-4.1-mini | runs 1, 3, 4 | runs 3 and 4 only (run 1 was overwritten): fabricated 11, 7; means −0.40, −0.34 vs correct −0.10, −0.08; cuts −0.20, −0.18 catch 11/11 and 7/7, flag 3/24 correct and 16/21, 17/25 declines |
| 3.3 cross-encoder at 0.3 | 85% caught, 12% FA | **29/29 caught, 3/24 FA**; 5/24 FA from 0.4 up |
| 3.3 bi-encoder | — | 0.4: 27/29, 4/24 FA; 0.5: 29/29, 9/24; 0.7: 29/29, 20/24 |
| 3.3 judge, recorded run | 90% caught (four runs) | **29/29 caught**, 6/24 FA (the other three runs were overwritten; their 4–6 in 24 FA spread stands) |
| 9.1 fields with no heading support (Ch 9) | 35 | **33**; plain prompt filled 1 (Furosemide, a correct reading); Prompt 9-1 null on all 33 |

Book changed in the same pass: Chapter 3's figures and the quote-existence and
five-draws passages, Chapter 9's counts, Chapter 12's "91–100% down to none",
and *Where the Numbers Come From* rows 3.1–3.5, 9.1 and G.1 ("16 of 48").

---

## Chapter 9 — a note written from a conversation, Experiment 9.4 (29 Sep 2026)

`ch09-sparse-field-fabrication/probe_conversation.py`. The setup the failure needs:
60 ACI-Bench conversations (the Chapter 8 encounters, now with their dialogues in
`data/aci_bench_dialogues.json`), a note under eleven headings, Claude Haiku 4.5
(no tools; a short environment block is added to each call). Two
prompts, identical except for one rule: *template* (headings only) and
*permission* ("If the conversation does not cover a section, write exactly 'Not
discussed.' … Do not infer, assume, or fill a section with typical content.").
Three runs each, 360 notes, $8.6 at API prices.

Ground truth is a strict word search over the dialogue: a topic counts as not
discussed only when no related word appears at all (family: the word "family" or
any relative; drug allergies: an allergy exchange about medicines, "allergic
to", "reaction to"; tobacco: smok-/tobacco/cigar/vape; alcohol:
alcohol/drink/beer/wine).

| topic, never discussed | template, runs 1–3 | permission, runs 1–3 |
|---|---|---|
| drug allergies (58 notes) | **4, 3, 4** | **0, 0, 0** |
| tobacco (53) | 0, 1, 0 | 0, 0, 0 |
| family history (41) | 0, 0, 0 | 0, 0, 0 |
| alcohol (49) | 0, 0, 0 | 0, 0, 0 |

Both prompts kept the two real drug-allergy answers (D2N018, D2N022) in every run.

**Every counted case was read** against its dialogue. The first scorer overcounted
three ways, each fixed before the numbers above were taken: (1) a narrow
family regex missed "run in your family", "anyone in your family", "my son" —
five "fabricated family histories" in run 1 were real content; (2) "allerg"
anywhere counted as allergies discussed, which hid four "No known drug
allergies" claims made where only seasonal allergies were asked about; (3)
silence statements ("No drug allergies discussed.", "Tobacco …: Not documented")
were scored as claims. The rule now: "No known drug allergies", with or without
a trailing "documented", and "No drug allergies noted" state the usual claim
about the patient and count; clauses that describe the conversation do not.

**Finding.** The failure reproduces on conversations, in one form: the standard
phrase "No known drug allergies" (about half of the 11 with "documented" or
"noted" after it), plus one "Denies tobacco". The one-line rule removed every
case in all three runs and cost nothing measured: both real allergy answers were
kept, and seasonal allergies the patient reported moved to History or Review of
Systems rather than being dropped. The engineering fixes were not exercised here;
the book's drug-label measurements of them stand.

## Chapter 3 — Prompt 3-1 as printed is not the prompt that ran (2 Oct 2026, resolved 3 Oct)

Found during the book-wide pointer sweep. `ch03-hallucination/fixed.py` adapts the
template; its `SYSTEM` differs from the book's Prompt 3-1 in four rules:

- Rule 2: the code requires a quote of the exact supporting text; the book prints
  `[Source N, paragraph X]`.
- Rule 3: the code says set `answerable` to false and `answer` to null, "That is a
  correct and expected outcome, not a failure."; the book prints say "Not found in
  provided sources. I cannot confirm this." and has no such sentence.
- Rule 5: the code routes unsure claims to `unverified_claims`; the book prints an
  "Uncertain —" line.
- The self-check wording differs slightly.

Two claims in the chapter rest on this. "Rule 3 of Prompt 3-1 accounts for most of
the effect … Most of the drop in fabrication comes from this one sentence — not
from the citation format, and not from the self-check" (repeated in the takeaway:
"That single rule accounts for most of the effect") was never isolated: no run
removes Rule 3 or the sentence. The measured contrasts are plain 3%, soft words 6%,
permission clause 91%, Prompt 3-1 0% (§ Chapter 3 re-read), so the large change
comes from the permission clause, and on Haiku 4.5 Prompt 3-1 moved the plain
baseline by one question of 32. *(Corrected 3 Oct: "one question" holds for Haiku
only; see the resolution below.)* "State the rule in exactly those words" points at words the
printed prompt does not contain. The book is unchanged on this point pending
the author's decision; the same defect in Chapter 9 was fixed by printing
`fixed.SYSTEM` (§ Chapter 9 re-read).

**Resolved 3 Oct 2026, on the author's "yes".** Every figure below is a replay of
committed fixtures; no live calls.

- **The book now prints `fixed.SYSTEM`**, re-wrapped to the page, with
  `{context}` shown as `{{source_document}}`. The four schema fields are named in
  the prompt's introduction; the structured outputs that enforce them are not
  prompt text. The old block's fused line ("…flag it as unverified. `<sources>`") went with it.
- **The Rule 3 paragraph is gone.** In its place, "What the test does not show":
  the test compared whole prompts and never removed one rule at a time. Takeaway 2
  now says the same, without digits.
- **Scope added to every single-model figure.** Plain 3%, soft words 6%,
  permission 91% and the recall figures are Haiku 4.5. The permission clause on the
  other three models: 100% (Opus 5), 100% (GPT-5-mini), 94% (GPT-4.1-mini), one
  recorded run each, already in the Chapter 3 re-read table. Prompt 3-1 is 0/32 on
  all four, with **0 answers rejected by the code gate on each**, so the zero is the
  prompt's own result, not the gate's.
- **Plain-prompt rates on the other models, as scored: Opus 5 69% (22/32),
  GPT-5-mini 22% (7/32), GPT-4.1-mini 22% (7/32).** Not printed. Reading Opus 5's
  counted answers: most say the label lacks the section and then add general
  knowledge marked "not from this excerpt"; a few quote text the excerpt does carry
  (Lisinopril adverse reactions, Metformin and contrast media); some state outside
  facts unmarked (Lisinopril pregnancy). The judge counts any assertion, so these
  rates mix a marked guess with an unmarked one. Printing them needs a re-score that
  separates the two. The GPT answers were not opened.
- **The cost bullet was wrong twice.** Plain-prompt recall on Haiku is 96%
  (23/24), not 100%; the 100% is the soft-words and permission prompts'. And its
  example said the plain instruction "would have guessed a number" for Lisinopril's
  starting dose; it did not. It said the label gives no starting dose, which is
  true (a combination-tablet label), and the grounded prompt declined and put its
  guess in `unverified_claims`. Of the grounded prompt's three declines, Lisinopril
  and Omeprazole (an OTC "Drug Facts" excerpt that never names the drug) have a
  reason in the text; Amoxicillin is the real cost (the label gives 90 mg/kg/day
  for its children's suspension; the plain prompt answered with it). The bullet now
  says this.
- **Takeaway 3 (citation enforcement)** no longer implies real quotes under
  unsupported claims: the check had no fabricated answer to reject.
- **Chapter 12** "91–100% down to none" now names what was compared (the
  permission prompt against the grounded prompt).


## Chapter 10 — the model's own count, asked without ambiguity (Experiment 10.3, 3 Oct 2026)

Closes the §16 caveat ("Chapter 10's 0/6 self-count agreement measures a prompt
ambiguity"). Two probes, Claude Haiku 4.5,
the same six labels, every run kept (`fixtures_count/`):

- `probe_count.py`: fixed.py's prompt word for word ("as-printed"), and the same
  prompt with the count defined as distinct amounts ("distinct"). 3 runs each.
- `probe_protocol.py`: the chapter's inventory protocol (book_prompt.py), 3 runs.
  repeat.py had kept only the last of its three API runs, so two of the three runs
  behind the book's protocol figures could not be reopened.

**The count is the length of the model's own list.** The count the model gave for
the source equalled the number of items it listed in **54 of 54** calls: 18/18
as-printed, 18/18 distinct, 18/18 protocol. In the earlier API runs it held on 4 of
6 (fixed.py; the other two within two items) and 3 of 6 (protocol; Sertraline 31
against 21 items, Gabapentin 77 against 49, both nearer the number of mentions).
A list that drops an item drops it from the count, so "check your list against
your count" cannot find a gap. With the count defined as distinct amounts, no
answer was nearer the mention count (0 of 18, against 3 of 18 as printed).

**The reference count had its own errors**, found by opening every disagreement:
- It counted a lab value as a dose: Lisinopril's "serum creatinine … 3 mg/dL".
  `common.py` now skips a unit followed by `/dL` (`LAB_UNIT_AFTER`); Lisinopril's
  reference count 8 → 7. Replays: fixed.py 96% (52/54, was 53/55), the protocol's
  kept API run 80% (43/54, was 44/55), broken.py 100% (54/54).
- It misses doses printed without their own unit: the first number of a range
  ("0.5 to 2 mg") and the cells of a table whose heading carries the unit
  (Gabapentin's renal-dosing table, "300 TID 400 TID …" under "(mg)"). Gabapentin
  has 24 dose amounts by the model's list and 13 by the pattern; Warfarin 8 and 6.
  Not changed: a stricter reference count misses gaps, it does not invent them.
- It ignores mL, so Amoxicillin's weight-band volumes never count.

**The inventory protocol, same setup as the one-line instruction:**

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| figures returned, one-line instruction (as-printed) | 94% (51/54) | 98% (53/54) | 98% (53/54) |
| figures returned, inventory protocol | 80% (43/54) | 83% (45/54) | 100% (54/54) |
| Step 1 count = items listed | 6/6 | 6/6 | 6/6 |
| Step 3 flagged a short document | 1 of 3 | 0 of 2 | none short |
| Step 3 flagged a complete document | 0 of 3 | 0 of 4 | 0 of 6 |

The kept API run agrees on Step 3: it flagged 2 of 3 short documents and none of
the complete ones. **Withdrawn:** "Step 1 wrong on every document in every run —
forty-seven dose amounts in a document containing thirteen" (a count of mentions
compared with a count of distinct figures); "Step 3 announced a mismatch on
documents that were complete" (no recorded run shows it); "84%, 71% and 80%" (two
runs unrecoverable; replaced by the three recorded runs above); Chapter 10's
"wrong on six of six … forty-one where thirteen … a count bearing no relation to
what it had just listed" and Chapter 12's echoes ("six of six", "18 out of 18").
The book also said "three runs over the same twelve labels": the test uses the six
labels with at least six dose figures.

## Chapter 12 — two withdrawn results were still in the self-assessment list (3 Oct 2026)

"Asked which section of a document its own quote came from, it named the wrong
section in 3–15% of cases" was withdrawn on 24 Sep (the 80-character artefact,
§ Chapter 8 — placement on real clinical notes), and "it attached genuine quotes to
all fourteen of its fabricated values" on 29 Sep (§ Chapter 9 re-read). Both were
still printed in Chapter 12's "five results from five chapters". The list now has
four: Chapter 2's confidence (no information about damage), Chapter 4's grade (LOW
never issued), Chapter 8's grade on clinical notes (7 in 10 misplaced sentences
graded HIGH) and Chapter 10's count (the length of its own list). The "Who checks"
row for the model reads "caught little or nothing" rather than "failed", because
Chapter 8's grade carried some signal; "five to ten times the cost" reads "about
five times", the judge's re-measured multiple.

## Report costs part still printed the withdrawn judge figures (3 Oct 2026)

`report/parts/09-costs.html` carried 38% false alarms, $41 per thousand and "ten
times the price" after Part 3 had re-measured them (4–6 of 24 over four runs, $22,
five times). Corrected there and in the front summary ("one costs ten times").

## References — cited sources sat under "not cited" (3 Oct 2026)

The "Further reading — context, not cited in the text" label stood above entries
46–55, but 49–55 are cited. Renumbered: the cited seven are now 46–52 under
"Studies, datasets and records"; the three uncited are 53–55, last, under Further
reading. 11 markers changed; every marker was checked against its entry's position.

## Two smaller corrections found on the same pass (3 Oct 2026)

- **Report, Chapter 10 audit:** the table and summary said "9 flagged, 1 genuinely
  missing" while the recorded run replays as 8 and 2, which the report's own later
  sentence ("the 2 real omissions and 6 false ones") already used. Aligned.
- **Book PDF citation links:** `convert_to_pdf.py` took reference targets from any
  page where a line began "N." at reference type size, so the Field Toolkit's
  numbered lists, which come first, captured low numbers: at least 16 links (every
  [10], for one) opened the toolkit instead of the reference. Targets now come from
  the References pages only; all 74 links checked against their entry's number.

## Chapter 9 — the checks, run on real invented entries (Experiment 9.5, 4 Oct 2026)

Prachi asked whether Chapter 9's prevention steps were ever tried. Only step 1 was
(Experiment 9.4). Steps 2 and 3 had met only drug labels, where nothing was invented,
so no check had ever been seen catching anything. `probe_checks.py` runs them on
Experiment 9.4's recorded template-prompt notes (60 ACI-Bench conversations × 3 runs):
**101 entries about the four optional topics — 12 invented** (11 "No known drug
allergies", 1 "Denies tobacco", from 8 conversations; each read against its
conversation in 9.4) **and 89 whose topic the conversation discussed.** Model checks:
one verdict per entry.

| check | invented caught (of 12) | discussed entries flagged (of 89) |
|---|---|---|
| keyword topic search, code | 6 | 3 |
| embedding (all-MiniLM-L6-v2, best sentence < 0.5) | 6 | 19 |
| Claude Sonnet 5, shown the conversation | **12** | 6 |
| Claude Haiku 4.5 — the model that wrote the note — shown the conversation | **12** | 7 |
| Claude Sonnet 5, shown only the note | 9 | **48** |

Embedding sweep (caught / flagged): 0.3 2/1 · 0.4 4/4 · 0.5 6/19 · 0.6 8/51 · 0.7 10/72.
No cut-off separates the two groups.

**The flagged discussed entries, read one by one.** Nine were flagged by a model that
saw the conversation; seven are real errors on topics that *were* discussed:
relatives mixed up (two runs of one renal family history, one adding "patient's
father has undergone renal transplantation", never said); "Denies tobacco and drug
use" when the patient answered only about wine; the patient's own pneumonia history
filed as family history (two runs); "Patient is a smoker" for a man who quit seven
years ago; increased caffeine the patient never mentioned. One is a borderline
inference (a sister "ill with upper respiratory infection"; she had "been sick" and
probably shared the patient's virus), one trivial ("Friday and Saturday evenings"
for "on the weekends"). So Sonnet's 6 flags are 5 real + 1 borderline; Haiku's 7 are
6 real + 1 trivial. The 89 "discussed" entries are therefore not all correct, and the
unflagged ones were not read.

**Topic search.** It catches an invented entry only when the topic word never
appears: 6 of the 11 "No known drug allergies" came from conversations that mention
allergies in another sense (seasonal allergies, a cat). Its 3 flags are one
conversation that describes reactions to dexamethasone and methylprednisolone
without the word "allergy" (all three runs), so they are false alarms.

**The blind check** flags whatever looks "unusually precise" (28 of its 48 flags
are family histories) and passed the plainest invented line, "No known drug
allergies. No seasonal allergies.", in all three runs of that conversation.

**Consequences for the book — not yet applied, pending Prachi:**
- Step 3's first condition ("the writing model … asked to check the entry, applies
  the same sense and approves it") is **contradicted**: the writer, asked in a
  separate call with the conversation in front of it, caught 12 of 12 and six of the
  seven real errors. What mattered was seeing the input and a narrow question.
- Step 3's second condition (the checker must see the input) **holds**.
- Step 2's topic check misses invented entries whenever the topic word appears in
  another sense, and flags entries whose topic is discussed in other words.
- Engineering fix 5 (an embedding validator of the ProvenanceEmbeddings kind) is
  now measured, and it separates poorly on this task.

## Experiment 10.3 corrected — a scorer artefact of mine, found by Experiment 10.4 (4 Oct 2026)

The hand-read behind Experiment 10.4 (below) caught two errors in what I printed
on 3 Oct. Both were re-verified against the raw fixtures before this correction.

- **The matcher refused range forms.** Gabapentin run 1 (as-printed and protocol)
  returned "10 to 15 mg/kg/day" and "25 to 35 mg/kg/day"; `dose_figures` credits
  only a number with its own unit, so it scored 10 and 25 as dropped. The figures
  are in the lists. Fix: `dose_figures(…, expand_ranges=True)` credits the first
  figure of "A to B unit" on the MODEL-LIST side only; the conservative reference
  rule over the source is unchanged. Corrected figures returned —
  one-line instruction **53, 53, 53 of 54 (98% each run)**, was printed 94/98/98;
  protocol **45, 45, 54 of 54 (83%, 83%, 100%)**, was printed 80/83/100. With the
  fix, the pattern comparison flags all 4 really short runs and no complete one.
- **The protocol's one "flag" was not about a gap.** Across the 18 protocol runs
  the self-check raised exactly one warning — Gabapentin run 1, a complete list —
  and the warning says the label's sections repeat (`all_counts_match` is true).
  Withdrawn: "flagged one of the five documents whose list was short, and none of
  the complete ones" (book), "flagged 1 of 5 short documents and 0 of 13 complete
  ones" (README), and the 10.3 table's self-check row. Correct statement: **the
  self-check flagged none of the short documents and one complete one, with a
  note about repeated sections.**
- **Whose dose is the missed "1 mg".** Every remaining as-printed shortfall is
  Sertraline's "1 mg/kg" — methylene blue's intravenous threshold, not a
  sertraline dose. The task as prompted is "list every dose amount mentioned in
  the text", so the runs stay counted short, with the attribution noted.

## Chapter 10 — the named-entity count, run as printed (Experiment 10.4, 4 Oct 2026)

The chapter's first engineering fix runs the source through "spaCy
en_core_web_trf or AWS Comprehend" and flags an extraction that returned fewer
items than the entity count. It had never been run; the repo's regular
expression stood in for it. `probe_ner.py` (built by a subagent; its two
decisive claims re-verified by hand above) runs en_core_web_trf 3.8.0 (spaCy
3.8.7, CPU, its own virtual environment) over the six dosing sections and holds
all 60 recorded extractions against it. The model has no dose type: QUANTITY
holds 153 of the 179 unit-bearing dose mentions, alongside lab values and
volumes, so the counting rule is a mg/mcg/g/unit amount inside a QUANTITY
entity, each distinct amount once.

| check, over 60 document-runs | really short (4) | another drug's dose only (6) | complete (50), false flags |
|---|---|---|---|
| NER rule as printed | **4** | 0 | **10** |
| NER rule, lab values skipped in code | 4 | 0 | 0 |
| NER count vs number of items listed | 0 | 0 | 5 |
| pattern count, same rule | 4 | 6 | 0 |

Both headline numbers are narrower than they look: all four real drops sit in
Amoxicillin, the one document where the entity count equals a complete list, and
all ten false flags are one lab value (serum creatinine "3 mg/dL" counted as a
dose — the mistake the pattern made until 3 Oct). Elsewhere the entity count
runs below a complete list, so a list can lose figures unflagged: Warfarin 4 of
its 6 (the genotype table's ranges get no entity at all), Levothyroxine 3 of 11,
Gabapentin its whole renal table (37 of 40 cells get no entity, the unit lives
in the column heading), Sertraline the methylene-blue dose — which is exactly
what six runs dropped, unflagged. en_core_web_sm flags nothing: it tags the
"50" of "50 mg" as a bare number. Read literally as "fewer items than the
count", the check catches 0 of 4. AWS Comprehend was not tested (paid API);
clinical NER with dose types (Comprehend Medical, med7) is the natural next
test. **For the book:** a general entity model can supply the independent count
only after code adds a unit filter, a lab-value filter and table handling — the
pattern's own work again — and it finds no doses at all in either dosing table,
the longest lists on these documents. Numbering: 10.4 is this probe; the
ACI-Bench omission measurement in progress becomes Experiment 10.5.

## Chapter 10 — omission measured where the length pressure is real (Experiment 10.5, 4–6 Oct 2026)

The author's direction: if the drug labels cannot produce the failure, test on a free
corpus where it can occur naturally. The corpus already existed: Experiment 9.4's
360 recorded notes (60 ACI-Bench conversations × 2 prompts × 3 runs), long
role-played visits compressed into eleven-heading notes. The checkable fact type
is the chapter's own: medication dose amounts. Built and first read by a subagent
(scripts and full case log in `ch10-silent-omissions/exp105_dialogue_doses/`,
paths made repo-relative and the run reproduced there); no model calls — every
note replays from Experiment 9.4's fixtures.

**Result: zero true omissions.** 83 raw number-plus-unit mentions in the
dialogues; 9 excluded with printed reasons (dietary sodium, lab values, one
breast-tissue weight, one bra size); 74 kept, including spoken forms ("a thousand
milligrams", "seven and a half", a stutter restart). They give 64 unique
(conversation, dose) facts across 39 conversations. Every one of the 64 reaches
all six of its notes, attached within 80 characters of its own drug's name (396
attachment checks, 6 failures, all one case). The one candidate the matcher
produced, in all six cells, is D2N027's vitamin D "5000 units on sundays, and two
thous… or 50,000 units on sundays, excuse me": a dose the doctor retracted
mid-sentence, and every note carries the corrected 50,000/2,000 — right scribing,
not omission. Doses the conversation left uncertain were flagged, not invented
("Gabapentin (dose uncertain; patient unsure if taking 300 mg or 100 mg)").

**Read as a null, with its limits:** dose facts are maximally note-salient (the
MEDICATIONS heading solicits them); durations, follow-up intervals and lab values
were not measured; dialogue length is 2–8k characters, not a 50-page document;
frequency/route survival and dose *additions* (Chapter 9's fact type) are outside
the measurement. The external studies carry the chapter's real-world rate
(Taylor 18% of 356 deployed-scribe notes; Williams 1.75 vs 0.86 per discharge
summary) — this experiment says the failure is not reproduced at this length and
fact type, not that it does not happen.

## Chapter 9 — fixes 1 and 2, run where the model invents (Experiment 9.6, 4–6 Oct 2026)

The chapter's first two fixes had never met an invented value. `probe_schema.py`
(drafted by a subagent that stalled at the session limit at 182 of 360
recordings; resumed and completed, and every counted case below read
by hand) asks for the four optional topics as a JSON record over the 60
Experiment 9.4 conversations — two conditions, three runs each, Claude Haiku 4.5,
360 replies, $6.23 at API prices:

- **required** — every value must be a non-empty string (what fix 1 removes);
- **optional** — a value may be null when the conversation does not cover it (fix 1).

| of 603 fields per condition whose topic the conversation never discussed | required | optional |
|---|---|---|
| invented values | 5 (all allergies) | 2 |
| silence fillers stored as strings ("Not discussed") | 577 | 0 |
| null | 0 | 585 |
| replies breaking the condition's format rule | 0 of 180 | 0 of 180 |

**Fix 1 does what the chapter claims, and the measured harm of "required" is
fillers, not inventions.** Forced to fill, the model stored a silence filler in
577 of 603 no-source fields — the exact failure the book predicts ("looks like
data and is stored as data") — and invented in 5. Allowed null, fillers vanish
and invention halves.

**Every invented value was read.** Five are one conversation, D2N088: the
patient denies *seasonal* allergies ("none whatsoever") and the value
generalises to "No allergies" / "No known allergies". One (D2N038) rests on "i'm
not taking any medications", which says nothing about allergies. One (D2N101)
came with no quote at all.

**Fix 2, the quote check (partial_ratio ≥ 85), on those values:** it caught the
quote-less one and **passed the other six — their quotes are real text about
something else.** Chapter 3's finding again, now on the fabrication side: a real
quote proves the text exists, not that it supports the value. What the quote
gate did do under "required" is null 546 of 611 silence fillers (their quotes
are empty or not in the conversation), turning most stored fillers back into
empties. Its cost on sound values: 7 of 97 (required) and 3 of 92 (optional)
values on discussed topics rejected; the read sample is a correct
steroid-reactions value whose quote stitched two real passages with "; ",
scoring 82 — the check wants one contiguous passage.

Numbering: this is Experiment 9.6; 9.5 is the checks probe above.

## Experiment 9.5 extended to the record values — the independence condition comes back (6 Oct 2026)

Prachi asked for the step-3 wording to stand on wider evidence, so the three
model checks were rerun on Experiment 9.6's values (`probe_checks.py --source
schema`): the 7 invented values and the 49 run-1 values on discussed topics.
168 verdicts, $1.77 at API prices; one hung call killed the first attempt and the
retry loop now treats a timeout as a failed attempt. Every verdict on an
invented value, and every flag on a control, was read.

| check | invented caught (of 7) | discussed-topic values flagged (of 49) |
|---|---|---|
| keyword topic search | 2 | 2 |
| embedding, 0.5 | 3 | 9 |
| Claude Sonnet 5, shown the conversation | **5** | 1 |
| Claude Haiku 4.5 — the writer — shown the conversation | **2** | 3 |
| Claude Sonnet 5, shown only the record | 2 | 11 |

**The split is clean, and it reverses half of the 9.5 note-set conclusion.**
The two zero-evidence inventions (a quote about medications under an allergy
claim; an empty quote) were caught by both models — as all 12 note-set
inventions were. The five misses are one judgment call: "No allergies" / "No
known allergies" / "none", written from the patient's denial of *seasonal*
allergies, with that denial attached as the supporting quote. **The writer
approved its own generalisation five of five.** Sonnet caught three of five and
was not steady: it returned NOT_SUPPORTED for "No allergies" in one record and
SUPPORTED for the identical entry text, same conversation, in another. The
note-set entries said "No known **drug** allergies" — a specific claim a
seasonal denial plainly cannot support — which is why both models caught all of
those; the record values are looser and carry the writer's own quote, and there
the writer's habit survives its own review.

**Combined, 19 invented entries:** second model shown the input 17 of 19;
writer 14 of 19; every zero-evidence entry (14 of 14) caught by both; every
habit-born entry approved by the writer. The extension's control flags are
again real errors (the D2N185 relative mix-ups; a patient's own answer filed as
family history).

**Consequence for the book, applied:** step 3 keeps "see the input" as the
first condition and restores the independence preference as the second, now
measured rather than asserted — with the caveat that a second model was not
steady on the judgment-call entries either. The 9.5-only conclusion ("which
model matters less than expected") was an artefact of an easy set, exactly what
the wider run was for.

## Chapter 9 — a list of quotes per value (Experiment 9.7, 8 Oct 2026)

Prachi asked for the fix-2 note's schema change to be tested and, if it helps,
promoted to an engineering fix. `probe_schema_list.py` reran Experiment 9.6's
extraction over the same sixty ACI-Bench conversations, one condition, three
runs (180 replies, $2.01 at API prices): fields optional, and `source_quotes` a
LIST — "one list item for each separate place in the conversation; never join
two places into one item." Gate: a value is kept only when every quote in its
list is found (partial_ratio ≥ 85, first eighty characters).

| | single quote (9.6, optional) | quote list (9.7) |
|---|---|---|
| discussed-topic values wrongly rejected | 3 of 92 | **0 of 75** |
| invented values (of 603 no-source fields) | 2 | 1 |
| values carrying ≥ 2 quotes | — | 32 of 93 non-null |
| nulls per run | 195 | 208–210 |

**The target case is fixed.** D2N022's steroid-reactions value — the stitched
two-place quote that 9.6 rejected at 82 — now returns three to four quotes in
every run, each one continuous passage, each found. D2N018 and D2N050 show the
same shape legitimately (question + answer; two separate mentions of the
father's kidney stones).

**Costs and limits, from reading the cases:**
- **Fewer values on discussed topics: 75 across three runs against 9.6's 92**,
  with nulls up accordingly. The stricter quote instruction makes the model more
  conservative about stating values at all.
- **The gate still checks existence, not support.** The one invented value
  (D2N088 run 3, "Denies allergies" from the seasonal denial "none whatsoever")
  passed, as its single-quote cousins did. And D2N059 shows a new face of the
  limit: the value "Seasonal allergies" is right, but its found quotes are
  "yeah i think so yeah" (the answer without its question — ACI's speaker
  labels are scrambled there) and an unrelated ear-fluid line. A quote list
  multiplies the places where an existence check can be satisfied by
  meaning-free text.

**Verdict: adopt as an engineering fix.** It removes the quote check's main
false-alarm mechanism at no gate cost; the support-vs-existence limit is
unchanged and stays with step 3 and fix 3.

## Experiment 9.5, closed with the packaged validator itself (8 Oct 2026)

Prachi asked for the actual Guardrails ProvenanceEmbeddings validator, not only
the from-scratch version of its check. Install route: `guardrails-ai` 0.6.8 in
its own virtual environment; the hub's API host (`hub.api.guardrailsai.com`)
does not resolve from this machine, so the validator was installed from its
public GitHub source. Field notes from running a shipped guardrail: it needs
nltk's `punkt_tab`, which its setup does not fetch; it attempted to send
OpenTelemetry traces home (blocked offline); and it **crashes on sources whose
chunker returns a single chunk** — a `squeeze()` turns the one-row embedding
matrix 1-D and `norm(axis=1)` raises — which sparse-punctuation transcripts
trigger. Workaround: duplicate the source (identical k=1 distances).
`probe_guardrails.py` runs it over the identical 9.5 entries, both source sets,
no model calls.

**How it actually works** (read from source): threshold is a cosine DISTANCE,
default 0.8 — a similarity of 0.2; the output is split into sentences (nltk)
and each sentence is compared with its nearest source chunk (k=1); any failing
sentence fails the value; sources are chunked into five-sentence windows with
overlap 2 by default; cosine is the only metric; there is no fix action.
Metadata must supply `sources` + `embed_function` (here all-MiniLM-L6-v2) or a
`query_function`; chunking is controlled by `chunk_strategy` / `chunk_size` /
`chunk_overlap`.

| configuration (notes set: 12 invented / 89 discussed) | caught | flagged |
|---|---|---|
| as shipped: distance 0.8, five-sentence windows | 2 of 12 | 12 of 89 |
| distance 0.5, five-sentence windows | 9 of 12 | 61 of 89 |
| distance 0.5, single-sentence windows | 7 of 12 | 40 of 89 |
| every setting that caught all 12 (every threshold, not a grid) | 12 of 12 | 72–89 of 89 (five-sentence windows: 76–89) |

Records set (7 invented / 49 discussed) behaves the same; as shipped it caught
2 of 7 and flagged 12 of 49. At the same nominal cut (distance 0.5 ≈ similarity
0.5) the product flags twice what the from-scratch check flagged (40 vs 19 of
89): its any-sentence-fails rule punishes multi-sentence entries, and punkt
chunking struggles on transcripts with sparse punctuation. Five of its flags
were read: all are paraphrase distance, not missing support — "Reduced alcohol
use, particularly during holiday season", "Occasional alcohol use (wine)" — the
same wording-not-meaning behaviour as Chapter 7's distance filter; one flagged
set is the D2N122 family-history entries that really are wrong, flagged for the
wrong reason. **Verdict: the packaged validator confirms the from-scratch
conclusion. As shipped it is looser and misses ten of twelve inventions; no
configuration separates invented from supported on these entries.**

## Chapter 10 — the completeness audit, against extractions with known gaps (Experiment 10.6, 8 Oct 2026)

The chapter's third engineering fix is a second model call — show a model the
source document and the extracted output and ask, verbatim, "What information
present in the source is missing from the extraction?" The book recommended it
without a measurement. `probe_audit.py` ran that audit once over every recorded
extraction of Experiment 10.3: the 54 runs (as-printed, distinct, protocol)
plus the kept API protocol run's 6 — 60 extractions over the chapter's six FDA
labels. The corrected pattern comparison (lab-unit fix on the source side,
`expand_ranges=True` on the list side) names the ground truth: 12 extractions
short, 48 complete, 41 known-missing figures in all. Auditor: Claude Haiku 4.5
— the same model that produced the 54
extractions. The question was asked word for word, with one addition for
scorability: "Answer with JSON only: {\"missing\": [...]}". 60 calls, no
retries, $2.04 at API prices. Every counted case is printed in full in
`audit_log.txt`, and `python3 probe_audit.py` rescores the recorded replies.

**Caught: 10 of 41 known-missing figures** (as-printed 3/3, distinct 0/9,
protocol 5/18, api-protocol 2/11). Every full catch was a one-figure gap: the
methylene-blue dose the Sertraline extractions kept dropping (audit named
"1 mg/kg"; caught in 4 of the 6 runs that dropped it), Warfarin's "≤ 100 mg/day"
cap, Amoxicillin's clavulanate component ("6.4 mg/kg/day"). Of the 12 short
extractions: every figure caught in 5, part in 3, nothing in 4.

**The largest omission got a pass.** distinct/amoxicillin run 1 dropped eight
strength figures — every tablet and suspension strength — and the audit
answered that nothing was missing. The two protocol runs with the same eight
figures missing each got "500 mg" and "875 mg" named (the plain tablet
strengths) and never any combination strength (200 mg/28.5 mg, 400 mg/57 mg,
600 mg/42.9 mg). api-protocol/gabapentin (one figure short, 400 mg) got three
entries, every one a figure already in the extraction, and not the 400 mg.

**Alarms: 6 of the 48 complete extractions.** Four listed doses the extraction
already carried, in different wording ("300 mg three times a day" against the
extraction's "300 mg three times daily"); one of those four also named
"1000 mg/day" — a figure that appears in neither the source nor the extraction
(verified by substring over both; the extraction's titration ladder runs
100–900 then 1400 mg/day). Two named real source content outside the dose task:
treatment durations ("10 days"; "6 to 12 months", "4 weeks", "4 hours",
"2 days") and an INR threshold ("greater than 4").

**Same omission, different verdicts.** The identical one-figure gap — the
methylene-blue dose, same document, same missing line — was caught in
as-printed runs 1–3 and protocol run 2, and missed in distinct run 2 and
protocol run 1.

**Reading.** The gaps in this test are defined by the pattern count in code, so
the code count finds all of them by construction; the audit, given the same two
documents, fully caught 5 of 12. The fix's sentence "catches omissions that
rule-based checks miss" did not show on the dose task: what the audit named
beyond the pattern's reach was non-dose content on complete extractions — that
is, alarms under the task. As a sampled monitor it is cheap and sometimes names
the exact missing line; as the only completeness check it would have passed the
worst extraction in the record. Caveats: one document type, one task, one
auditor model, and the auditor is the same model that wrote the
extractions. Book changes: fix 3 carries this as its "Measured here", the
prevention section's input-coverage paragraph points to it, and the takeaway
box gained one bullet.

## Chapter 10 — the `not_extracted` count, re-read against the fixtures (9 Oct 2026)

Prachi asked "eleven items out of how many?" and the answer was not in the record.
Replaying `fixed.py` (Experiment 10.2, committed fixtures, no live calls): the field
was filled on **3 of 6** documents with **8 entries** — Lisinopril 1, Amoxicillin 3,
Warfarin 4 — naming ten values (the Warfarin intervals entry lists three). No
fixture supports "eleven items" or "four of six documents"; both figures stood in
the book (fix 4's Measured here), in this file (§ "Two improvements that are
definitions"), and in the report (summary table, Fix 4 prose, verdict table). All
three now say 8 entries on 3 of 6.

The book also said the field "stayed empty on the one document where a dose had
silently dropped out". It did not: on Amoxicillin, the document that dropped 200 mg
and 400 mg, the field held three entries (10 days, 2/3 of the water, the remainder
of the water) and named neither missing strength. Chapter 12 already described it
that way; Chapter 10 now does too. The denominators printed in the book are the
post-10.3 reference counts: 7, 11, 10, 7, 6, 13 = 54 figures, 52 returned.

Chapter 10's "What this prompt does" also now says which prompt ran: `fixed.py`'s
wording, which carries the printed `not_extracted` rule and additionally asks for a
source count (`source_count_claimed`), the subject of "What did not survive testing".

## Chapter 10 — the `not_extracted` field on text whose items are not delimited (Experiment 10.7, 10 Oct 2026)

Prachi asked whether anything in the chapter measured its claim that on a document
whose items are not clearly delimited the field "fills with noise rather than
judgement". Nothing did: every run of the field was on FDA dosing sections, and the
sentence was an inference printed as a result (in "Where this prompt works" and in
the takeaway box).

`probe_field_conversation.py`: Prompt 10-1 **as printed** (system prompt), `{item_type}`
= "medication dose amount", the 60 ACI-Bench dialogues as the document, 3 runs,
Claude Haiku 4.5, 180 calls, $3.43 at API prices,
4,563 recorded seconds, fixtures in `fixtures_field_conversation/s{1,2,3}/`. Ruler:
Experiment 10.5's `count_doses.py` (64 unique doses, 39 dialogues; 21 state none).
Every reply parsed as JSON on the first attempt.

| per run | 1 | 2 | 3 |
|---|---|---|---|
| ruler doses in `extracted` | 62/64 | 63/64 | 63/64 |
| true silent omissions, after reading | **0** | **0** | **0** |
| field filled: conversations (of the 21 with no dose) | 49 (19) | 51 (20) | 50 (19) |
| entries | 137 | 149 | 147 |
| — medicine named without any amount | 95 | 91 | 88 |
| — frequency / duration / route only | 13 | 9 | 9 |
| — number that is not a dose (lab, vital, grade, measurement, habit) | 17 | 36 | 37 |
| — excluded by the ruler (sodium, per-dL lab, tissue grams) | 4 | 4 | 5 |
| — other quantities / unit-less numbers | 7 | 9 | 8 |
| — a ruler dose set aside with a reason | 1 | 0 | 0 |
| entries that held back a dose the extraction should carry | **0** | **0** | **0** |

**Read, not just counted.** The miss in every run is D2N027 "5000 units", retracted in
the same sentence; every run extracted the corrected 50,000 + 2,000 units (cases.md §1
already had it). Run 1's 175 mg sat in the field with the right reason (the patient
proposed it; the doctor declined). Every "not found in dialogue" extra was a number
the dialogue states without a unit and the model unit-ed from context ("two . five of
norvasc" -> 2.5 mg; "300 or 100" -> mg; "2000s" -> units; "i'm at 140" -> mg): zero
invented numbers in 180 replies. `extracted` also carried 12/14/12 amounts per run the
ruler has no unit for (puffs, tablets, cc, mL, teaspoon) and 9/7/8 strings with no
amount at all (application schedules, almost all from D2N145) — over-inclusion, the
same direction as Experiment 10.1. The medicine-without-amount class was read in full
for runs 1–3 and the other classes for all runs; the sub-class regexes in
`subclass()` are the scorer's claim, the printed lists are the record.

**Verdict.** Not "noise rather than judgement": none of the 433 entries was a wrong
call. Volume: ~2.3 entries per stated dose, two in three of them a medicine named with
no amount, filled on 19–20 of the 21 conversations that state no dose at all. The
real decisions (lab values, vitals, salt targets, a declined dose, "lortab 500-") are
30–50 per run inside ~140 lines.

**Scorer notes.** The ruler's unit-less blindness ("two . five") needed a spoken-number
matcher with ACI-Bench's "two . five" transcription; `stated_without_unit()` holds it.
The first classification (before `subclass()`) is what `field_conversation_log.txt`
was first written with; the log was regenerated from the final scorer.

**Book.** "Where this prompt works" now carries the measurement with a Measured here;
the takeaway bullet says "the queue lists every one of them, so the real judgement
calls sit inside a much longer list" instead of "fills with noise"; the numbers table
gained rows 10.6 and 10.7. Report part 07-ch10 gained the subsection; README gained
10.7.

## Chapter 10 — fix 1 with taggers that have a dose label (Experiment 10.8, 12 Oct 2026)

Prachi: the chapter recommended AWS Comprehend without trying it; en_core_web_trf has no
dose type so "our" application needed a unit filter, but a reader's fact type may be in
some tagger's label list — give the conclusion generically, and try a tagger with a dose
label if one exists.

**Comprehend.** No AWS account on this machine, so not run. The product the chapter named,
plain Amazon Comprehend, has nine general types (COMMERCIAL_ITEM, DATE, EVENT, LOCATION,
ORGANIZATION, OTHER, PERSON, QUANTITY, TITLE) — no medication type; it would have behaved
like en_core_web_trf. Amazon Comprehend Medical (DetectEntitiesV2) returns MEDICATION
attributes typed DOSAGE, STRENGTH, FREQUENCY, DURATION, ROUTE_OR_MODE, FORM, RATE (API
reference, Attribute.Type). The book now says both, and recommends neither untried.

**Taggers with a dose label, run.** `probe_ner_dose.py`, environment `.venv-med` (spaCy
3.4.4 for Med7's pin, numpy<2, transformers 4.57, torch 2.8; the Med7 wheel's filename
`-any-` is rejected by pip and must be renamed `en_core_med7_lg-3.4.2.1-py3-none-any.whl`).
Same six sections, same 60 recorded extractions, same rule as 10.4.

| | en_core_web_trf (10.4) | Med7 STRENGTH+DOSAGE | DeBERTa DOSAGE |
|---|---|---|---|
| with-unit mentions in the label (of 179) | QUANTITY | 144 | 125 |
| in no entity | — | 35 | 41 |
| Levothyroxine distinct doses (pattern 11, read 14) | — | 1 | 3 |
| Amoxicillin (10) | — | 8 (no 200, 400) | 6 (no 28.5, 57, 200, 400) |
| Warfarin (6) | — | 6 | 2 |
| real drops flagged (of 4) | 4 | 3 | 3 |
| complete runs flagged, false (of 50) | 10 | 0 | 0 |
| short only by another drug's dose, flagged (of 6) | 0 (corrected 14 Nov 2026: trf counts 6 doses on Sertraline, so the 6-item lists are not flagged; §10.4's 0 was right) | 0 | 6 |

Forms neither label covered: "90 mg/kg/day", "1.6 mcg/kg/day", "200 mcg/day", "50-200
mg/day", "600 mg/42.9 mg per 5 mL", the genotype table cells. Med7 tags "3 mg/dL" as
STRENGTH in a test sentence but did not in the Lisinopril section as written, so no lab
false alarm appeared; the risk is there. The drop both taggers missed is the api-run
Amoxicillin extraction (8 of 10, lost 200 and 400 mg): a tagger whose count is 8 or 6
cannot flag a list of 8. Per document 0.2–0.8 s (Med7), 0.2–0.6 s (DeBERTa, mps).

**Generic conclusion, as now printed in fix 1:** read the label list (a matching label
removes look-alike false alarms); measure the label's coverage on your own documents
against a hand-read sample (a label knows one way of writing the fact); where coverage is
poor write the pattern (same domain work, your rule); a tagger's count flags only the
loss of what it sees; the count must come from outside the model either way.

## Experiment 10.7, fourth condition — the field with one line added (12 Oct 2026)

Prachi: "do the 4th run". The line: "Do not list items that simply have no amount. List
only values that could be mistaken for a medication dose amount." — inserted before the
printed prompt's "An empty not_extracted list is a claim…". Three runs, same 60
conversations, same ruler, 180 calls, $4.69 at API prices, 6,575 recorded seconds
(`--condition narrowed`, fixtures in `fixtures_field_conversation/narrowed/s{1,2,3}/`).

| per run | as printed 1/2/3 | one line added 1/2/3 |
|---|---|---|
| ruler doses in `extracted` (of 64) | 62/63/63 | 62/63/63 |
| true silent omissions, after reading | 0/0/0 | 0/0/0 |
| field filled: conversations (of 60) | 49/51/50 | **26/32/30** |
| of the 21 with no dose | 19/20/19 | 13/11/10 |
| entries | 137/149/147 | **57/62/58** |
| — medicine named without any amount | 95/91/88 | **5/2/3** |
| — number that is not a dose | 17/36/37 | 28/40/36 |
| — frequency / duration / route only | 13/9/9 | 9/3/5 |
| — excluded by the ruler | 4/4/5 | 7/7/5 |
| — other quantities / unit-less | 7/9/8 | 7/9/9 |
| — ruler dose set aside with a reason | 1/0/0 | 1/1/0 |
| entries that held back a dose the extraction should carry | 0/0/0 | 0/0/0 |

Read: the two set-aside ruler doses are the right two (175 mg proposed-and-declined; run 2's
retracted 5000 units, with the reason "corrected to 50,000 units"). The five remaining
medicine entries in run 1 are tablet counts without a unit ("i'm just on one now") and
"a little bit of anti-inflammatory"; run 2 listed four drug prices ($850, $70…) as
look-alikes — a stretch, harmless. Contents vary run to run (D2N088: two A1C values in run
1, none in run 2; D2N013: none in run 1, "162" in run 2). Extraction unchanged in every
cell.

Verdict: the volume was the prompt's fault, not the field's. One line that says what the
field is for cut it by more than half and removed the medicine inventory, with no loss on
the extraction side and no wrong call. Book: the "Adapt this before you use it" note now
carries the line with its measured effect; "Where this prompt works" has the before/after
counts; numbers table row 10.7 updated. The printed prompt is unchanged (it is the one
the FDA-label results were measured with).

## Chapter 10 — the fixes on output that cannot be counted (Experiment 10.9, 13 Oct 2026)

Prachi: the fixes all assume enumerable items; run them on a task without them and
report inside each fix. Task: Experiment 9.4's 360 recorded template/permission notes
from the 60 ACI-Bench dialogues (prose output; no new note generation).

**Fix 1 — tagger count on prose** (`probe_note_count.py`, Med7 DRUG spans, local, 235 s).
Dialogue vs note distinct-drug-name counts; note flagged when lower. Per dialogue: 1–10
names, median 3. Flags: template 33/30/32, permission 31/33/29 of 60 → 188 of 360.
Classified then read: 109 flags = junk only (Med7 on spoken text tags first names —
sarah, michelle, katherine, linda, clark, walmart, atlanta — and fillers — um, hey, i —
as DRUG). Remaining 79 read at their four strongest: D2N139 Benicar IS in the note
(olmesartan combo line) and carvedilol is "next medication… which I try to avoid" (a
future option); D2N026 Eliquis IS in the note, prednisone was a doctor question the
patient never confirmed; D2N064 Tylenol appears as acetaminophen (generic rename);
D2N186 Vicodin requested and declined, note records "non-narcotic options". Verified
omissions: 0. Mechanisms: tagger out of distribution + prose renames + a note is
selective by design (the case study's reproduce-vs-compress line).

**Fix 2 — list-length assertion**: no list on prose; does not run. Printed as the result.

**Fix 3 — completeness audit on prose** (`probe_note_audit.py`, 64 calls incl. 4
re-records of unparsable replies, $2.16 at API prices, 3,282 s; every claim printed in
note_audit_log.txt with a content-word check against note and dialogue). 91 claims on
45 of 60 notes; 1 unparsable left. Checks: 1 claim names a dose and is false by 10.5's
settled record (D2N088 metformin, in the note as "metformin increased to 1000 mg twice
daily" — the audit's quote even carries the dose); 17 claims' content words are mostly
in the note already; 0 quotes absent from the dialogue (no invented quotes). The rest
are real absent content — hydration counselling on a new diuretic (D2N008), the
betamethasone-over-methylprednisolone rationale (D2N022), "extremely low" days
(D2N015), a missed Dr-Davis appointment (D2N022) — whose note-worthiness is editorial.
No enumerable ground truth exists; that is the experiment's stated point.

**Fix 4 — not_extracted field**: no answer schema on prose output; na. 10.7 is its
free-text measurement (input side).

**Book**: a "same check on output that cannot be counted" passage in fix 1, one-sentence
results in fixes 2 and 4, a "one fix left standing" passage in fix 3, numbers-table row
10.9. Scorer notes: the junk/real split in probe-note-count is a regex suggestion over
the printed per-case list; the four strongest real-looking flags were opened in both
dialogue and note before "0 verified omissions" was printed.

## Fix 4 checked in code (Experiment 10.10, 14 Oct 2026)

Prachi: the field is an engineering fix, so check it through code — deterministic
results may differ. The deterministic half is verification of the model-written
entries: `probe_field_codecheck.py` replays all 360 recorded 10.7 replies and traces
each `extracted` item and `not_extracted` entry to its dialogue (digits → spoken
forms → item words; entries read when flagged).

Per run (field / extracted NOT TRACED after the final matcher): as-printed 1/0, 0/0,
1/0; narrowed 1/0, 0/1, 0/0 → 4 of 1,192. Read: D2N104 "methoprexate" (dialogue says
methotrexate — a corrupted drug name, the one real catch); D2N104 "Unit of measurement
for prednisone doses" (describes an ambiguity, quotes nothing); D2N160 "90 (or 79)"
(the transcript itself is garbled: "seven over ninety"); D2N104 "prednisone: one
(additional dose taken occasionally)" (paraphrase of "i take an extra one"). Zero
invented values anywhere.

Checker archaeology, kept because it is the finding: the first strict run raised 43
alarms and 39 were the checker — "a thousand milligrams", "seven and a half", "two and
a half milligram pills", "a half a cc", "one fifty", "one thirties", "a hundred and
eighty over eighty", PSA written ".5", Fitzpatrick "iv to v", plus a double-normalised
0.6 (my bug). Each fixed form is in `spoken_variants()` / `numbers_in()`; every case
was read before any count was printed. Same lesson as 10.8, now on the checker's side:
a deterministic verifier is only as good as its spelling of the domain.

Book: fix 4 gained "Check the field in code." with the numbers and the lesson; numbers
table row 10.10; report subsection; README entry.

## Fix 4: the code-check trimmed in the book; enforcement measured (14 Oct 2026)

Prachi: is the trace check needed in the omission chapter, since it measures
fabrication? Verdict agreed: it is a precondition for trusting the queue, not an
omission finding — the book now carries two sentences inside the routing block (no
invented value, one corrupted drug name, Experiment 10.10) and the 43-alarms
spoken-number story lives only here and in the report (it duplicated fix 1's lesson
in the book).

Her second ask, run as **Experiment 10.11**: enforcement through the answer schema.
Decoder-level (API structured outputs) was not run.
Engineering enforcement is deterministic given a reply, so it was computed by replay
over the 360 recorded 10.7 replies instead of a 180-call live arm: 359 conform to the
strict schema as generated; the one failure (as-printed s2 D2N049: extracted items as
{'medication','dose'} objects) was corrected with one live call — same three
medicines re-written as strings, not_extracted identical before and after. Conclusion
printed in fix 4: the schema requirement is cheap to meet; enforcement changed format
once in 360 and content never; what the field holds is governed by the prompt. The
unmeasured remainder stays named: generation-time enforcement via structured outputs.


## Correction — Chapter 5, the normaliser's loss count is 40, not 52 (14 Oct 2026)

The book and the section "Where the Numbers Come From" printed "52 recorded
losses" for Experiment 5.2, and §10 above says 53 discard rows. A replay of the
committed `ch05-extraction-normalisation/fixed.py` from its fixtures prints 40
losses, and the README has said 40 since the repository was first published. The
52 and 53 came from runs that predate the initial commit; `fixed.py` has never
changed in git. Found by the 14 Oct book-to-repository cross-check. The book now
prints 40 in both places. The earlier §10 sentence stands as a record of the
pre-commit run it describes.

## Correction — README quoted the wrong arm for Chapter 6's protocol (14 Oct 2026)

The top-level README's Experiment 6.1 line said "the book's six-rule protocol
33%"; 33% is the status+date+version arm. The full protocol's measured rate is
30% (arm table above). README corrected. COSTS.md and the report's front page
also still carried the withdrawn $41 / ten-times judge figures after the 3 Oct
re-measure ($22, about five times); both corrected. The section "Where the
Numbers Come From" in the book gained Experiment 4.2 as a repository identifier
(the three-system ensemble, previously recorded only as "Chapter 4 fix 2"
above), and its dataset summary now names every ACI-Bench experiment.

## The audit with a second, different model (Experiment 10.12, 14 Oct 2026)

Prachi caught the heading/evidence mismatch: fix 3 said "secondary model call" while
10.6's auditor was the same Haiku that wrote the extractions. Fixes: the heading is now
"Completeness audit via a second call" with a clarifying sentence; the prevention
sentence, the takeaway bullet and the numbers-table row for 10.6 no longer say "second
model" where the same model was measured; and the different-model arm was run at her
ask.

`probe_audit.py --auditor claude-sonnet-5` (new flag; per-auditor fixture subdir and
per-auditor call budget — the first attempt died on the shared 60-call budget already
consumed by Haiku's fixtures). Same 60 recorded extractions, same question verbatim.

| | Haiku (10.6) | Sonnet 5 (10.12) |
|---|---|---|
| known-missing named (of 41) | 10 | **39** |
| incomplete: all/some/none (of 12) | 5/3/4 | 11/1/0 |
| worst extraction | "nothing missing" | all but two figures (42.9, 600 — inside the paired strengths) |
| complete alarmed (of 48) | 6 | 12 |
| invented figures | 1 | **0** |
| cost at API prices | $2.04 | $1.98 |

Alarms read: restatements or real off-task content (water volumes, INR target,
creatinine clearance, intervals); one complete Sertraline extraction drew 15 entries,
nearly all restatements. Verdict in the book: the auditor decides what the audit is
worth — the same model misses what it wrote past; a stronger different model caught
nearly everything at the same per-call cost, paying in off-task alarms. "Sampled
monitor, never the only check" stands for both arms. Takeaway bullet rewritten to
carry both arms without numbers.


## Replay audit (14 Nov 2026): every experiment replayed against the README and the book

All 56 README experiments were replayed offline from the committed recordings and every
stated number compared with the README entry and the book (full list:
`../questions/replay-audit-2026-11-14.md`). Most reproduce exactly. The rest share one cause:
**the cache keeps one recorded answer per request**, and later live runs (the Aug repeat
sweep, `shipped_prompt.py --live` 13 Sep, `model_ensemble.py --live` 14 Sep, the Ch7
`--no-ood --live` runs) overwrote earlier answers while the book kept the earlier numbers.
Git history starts 7 Sep and Tables 4-1 and 4-2 sample the same keys, so the old answers
cannot be restored; the book and README now print what the repo replays.

Corrections made in the book and the README on the same day:

- **Ch2.** Prompt 2-1 as printed had never been run (its figures were book_prompt.py's):
  now Experiment 2.7, three runs. The p.46 grade table is
  book_prompt.py's (HIGH 24 / MEDIUM 29), not why_no_low.py arm A's (14 / 39); the
  grade-only row replays 12 / 41 / 0. Entropy: lookalike letters RAISE entropy by
  0.145-0.207 bits/char; they escape because clean labels spread 4.30-4.76 and the band is
  4.15-4.91 (the old "the number does not move" was wrong). Most Cyrillic in one document:
  55, not 65. l/1 swaps: 39 (33 one way, 6 the other). The 85.5% OCR word accuracy came
  from difflib's default autojunk and no scorer is committed: dropped from the book.
- **Ch3.** Self-consistency: 280 calls, $0.86 (290/$0.91 was the pre-recount set). Judge:
  $0.0164 per audit vs $0.0042 per answer on the recorded run, about four times, not five.
- **Ch4.** Every figure moved to the recorded runs: template 99%/90%; Prompt 4-1
  99, 99, 97 / 93, 93, 93; HIGH 99% / 98%; MEDIUM 3 of 192; errors graded HIGH 1 of 1 and
  9 of 10; runner-up 4 of 5 and 15 of 21; gate caught 1 of 11 errors, held 2 correct;
  body 90%, F1 0.76 / 0.78; Table 4-2 GPT-4.1-mini opening 98, 98, 98 and review 1, 1, 1
  (bart on the category descriptions, now `model_ensemble.py`'s default).
- **Ch5.** Plain-prompt auditability 64% (196/307 over five runs), not 66%; values
  returned 59-80 across the three prompts, not 54-77.
- **Ch7.** Classifier: in scope 11 of 12 on the direct attack, one Hindi question labelled
  ambiguous, 107 of 132 correct. The plain prompt obeyed 0 of 48 injections in every run;
  the 1, 1, 2 of 48 in the sweep was out-of-scope questions answered (the one such case still recorded, Warfarin ood_numeric, was a refusal `_declines()` missed: "unable to interpret". The phrase is now on the list: the recorded run replays 0 of 48 answered and 144 of 144 correct). In the `--no-ood` run the phrase list stopped 36 attacks and the
  classification call declined all 36 out-of-scope inputs, so Prompt 7-1 itself faced only
  the 12 Spanish attacks; Table 7-1 now says so.
- **Ch8.** 64 of 66 planted-swap rejections named the true section (two on the Amoxicillin
  boilerplate quote).
- **Ch9.** Five of the six passed inventions quote the seasonal-allergy denial; the sixth
  quotes a medications line.
- **Ch10.** Sonnet named all 8 figures on the extraction Haiku passed as complete (the 7/9
  case is api-protocol, which Haiku did not pass). "Dropped the most" was the 9-figure
  api-protocol case, not the 8-figure one. The general tagger (rebuilt .venv-ner, spaCy
  3.8.7, en_core_web_trf 3.8.0) counts 6 doses on Sertraline: the six Sertraline runs are
  NOT flagged (the 10.8 table above said 6). mL is not a counted unit; the pattern count is
  fix 1, not fix 2; 63 of 64 dose facts reached all six notes.
- **X.1.** GPT-5-mini silent corruption replays 88% (36/41), not the sweep's 80%;
  GPT-4.1-mini 73%. **C.1.** Three of the four "silent omissions" under real OCR are figures
  the OCR invented.

Not replayable here: three-run spreads (only the last run is on disk), the Guardrails
validator settings beyond the shipped one, LLM Guard timings, and R.1 (repeat.py is live
only). Repo fixes the same day: probe_convention.py reads Prompt 8-1 from prompt_8_1.txt
(the book's re-wrap had moved two line breaks and broken the replay); scripts that need an
optional package now say so and `run_all.py` prints them as skipped. `model_ensemble.py` now scores bart on the category descriptions by default, so a plain replay prints Table 4-2 cell for cell; `ZS_LABELS=names` keeps the 41% bare-name run.

Added the same day, Chapter 9 (Experiment 9.5): the nineteen invented entries split 11 with no evidence (both checkers caught all 11) and 8 widened from D2N088's seasonal-allergy "none whatsoever" (3 in notes: writer and second model caught all 3; 5 in records: writer approved all 5, second model caught 3). The book had said 14 and 5, counting the three D2N088 notes as no-evidence entries; the 17/19 and 14/19 totals were right. D2N185's "No known drug allergies" stays a no-evidence entry: its conversation mentions only Claritin for seasonal allergies.

Also 14 Nov 2026, C.1's simulated-OCR arm: the recorded run of `CORRUPT_MODE=ocr ch10-silent-omissions/broken.py` replays 51 of 52 dose figures and 1 of 6 documents short, not 2 of 6, and that one drop (Lisinopril "5 mg") is a figure the damage created ("12.5 mg" became "l2.5 mg"). The "2 of 6 in every run" above cannot be confirmed from the recordings. The clean arm replays 54/54, not 55/55.

**Timings re-measured, 14 Nov 2026.** `probe_llmguard.py --timings` (log `ch07-edge-input/llmguard_timings_log.txt`) re-scanned all 144 cases, 3 passes, on an Apple M5 Pro. On Apple silicon llm-guard runs its model on the GPU by default: 45 ms (full) and 79 ms (chunks) per scan; pinned to the CPU, 80 and 236 ms. The 23 Sep figures (51 / 77 ms) match the GPU path, so "local CPU" was wrong. Every fresh flag matched the recording on both devices (276 of 276). The book's "ordinary laptop processor" sentence and Table 7-1's cost cell now say so.

**Guardrails, every threshold, 14 Nov 2026.** The 8 Oct sweep tried seven thresholds. `probe_guardrails.py` now reads each entry's worst-sentence distance from the validator's own query function and checks the validator's own pass/fail against those distances, entry by entry, so one threshold per distinct distance gives every result the validator can produce (log `ch09-sparse-field-fabrication/guardrails_sweep_log.txt`). The grid rows reproduce exactly. The loosest setting that catches all 12 flags 76 of 89 (five-sentence windows) and 72 of 89 (one sentence), so the range is 72–89, not 79–88, and the book's "about nine in ten" is now "at least 72 of the 89, about four in five". AUC 0.55 on the notes; 0.36 and 0.43 on the records (worse than chance). The verdict stands: no setting separates the groups. The probe now switches hub telemetry off.

**Instructor on ten notes (Ch8), 14 Nov 2026.** No script or fixture recorded the earlier run, so the book sentence was removed and the run was made again: `ch08-routing-placement/probe_instructor.py`, Instructor 1.17.0 in its own environment, the same `Filing` validator, `max_retries=2`, the plain prompt, the first ten of the 60 notes, Haiku 4.5 with thinking off (with thinking on, a 476-character reply took 2,685 output tokens; about 250 with it off). No schema was enforced, so Instructor ran in Mode.JSON: it writes the schema into the system prompt and parses the reply. 16 calls, recorded in `fixtures_instructor/`. **9 of 10 notes ended with a valid filing**; 4 failed at first, 2 fixed by one re-ask, 1 by two, 1 still failing. 3 of the 4 first failures wrote each sentence's text after its ID ("S21: Sean Phillips is…"), which the validator reads as unknown IDs plus missing ones; the fourth left S22 unfiled. The still-failing note (D2N186) kept that form in all three replies; with the text after each ID removed its filing is complete (0 missing, 0 doubled). The validator's error listed the entries as "not in the input" and never said that only the IDs were wanted. On the same ten notes, the hand-built loop of 8.7 (schema enforced by the API) failed 1 at first and fixed it with one re-ask. One draw each, and two differences at once (enforced schema, and the error wording Instructor wraps), so the gap is not attributed.

**The first recordings of some experiments ran with thinking on, 14 Nov 2026.** The first recordings of 2.7, 9.4–9.7, 10.3, 10.6, 10.7, 10.9, 10.11 and 10.12 ran with thinking on; the API experiments (`shared/llm.py`) send no thinking parameter. Those recordings keep a cost at API prices but no token counts, so one recorded request per script was rebuilt by the script itself (its recording deleted in a scratch copy, the script run with `--live`) and sent twice, thinking on and off, 18 calls in all (2 of them lost to an error in the checking harness). Output tokens implied by the recorded cost, after subtracting the input cost seen today, against today's two calls:

| Script (experiments) | Recorded cost | Implied output tokens then | Today, thinking off | Today, thinking on |
|---|---|---|---|---|
| ch02 probe_prompt21 (2.7) | $0.0069 | ~940 | 295 | 858 |
| ch09 probe_conversation (9.4) | $0.0116 | ~1,490 | 668 | 1,311 |
| ch09 probe_checks (9.5) | $0.0130 | ~30 | 28 | 28 |
| ch09 probe_schema (9.6, 9.7) | $0.0310 | ~5,350 | 153 | 4,642 |
| ch10 probe_count (10.3) | $0.0146 | ~2,440 | 218 | 2,125 |
| ch10 probe_audit (10.6, 10.12) | $0.0292 | ~4,800 | 90 | 8,288 |
| ch10 probe_field_conversation (10.7) | $0.0070 | ~580 | 105 | 1,136 |
| ch10 probe_note_audit (10.9) | $0.0247 | ~3,680 | 145 | 5,634 |

Every recording where the two settings differ sits on the thinking side; 9.5's one-word verdicts show no thinking either way. probe_schema_list (9.7), probe_protocol (10.3) and probe_field_enforce (10.11) reuse those scripts' model call, so they ran the same way (seen in code, not re-sent). So two configurations of Claude Haiku 4.5 sit in this repository: the API experiments without thinking, these experiments with thinking on. No recorded number changes. Two consequences: a reader re-running one of these experiments without thinking is not repeating it; and Ch10's audit (10.6, 10.12), described in the book as put "to the same model that wrote the extractions", read 60 extractions of which 54 came from runs with thinking on (like the audit) and 6 from the API protocol run (no thinking). `probe_instructor.py` (8.7) runs with thinking off on purpose, to match 8.7's API calls. Prachi decided the same day that every experiment should run each model at its API default; these experiments were re-recorded that evening (next entries), so the paragraph above describes the first recordings.

**Re-recorded at the API default, 14 Nov 2026.** Every one of these scripts now calls `shared/cli_defaults.api_defaults()`: Haiku 4.5 with `MAX_THINKING_TOKENS=0`, Sonnet 5 with `--effort high` (its API default; the first recordings ran it at a higher effort). The first recordings moved to `*_cli_defaults/` folders (git mv; old logs to `*_cli_defaults.txt`) and replay with `CLI_SETTINGS=cli`; every script was checked to replay them byte for byte under that setting before any new call. 2,125 calls re-recorded (2.7, 9.4–9.7, 10.3, 10.6, 10.7, 10.9, 10.11, 10.12) plus 225 for 9.5's record-value checks; downstream analyses (10.4, 10.5, 10.8, 10.9's count, 10.10) read the new recordings.

*Chapter 2 (2.7).* 39 of 41 damaged flagged in every run (first recording 40, 39, 39; misses the truncated Atorvastatin and Omeprazole copies each time); 12 of 12 OCR-damaged; clean controls 2 of 12 in every run, both real defects (Metformin's "1.73 m 2" now passed); no false alarm in 36; SEVERELY_CORRUPTED 1, 2, 1 times, each a truncated copy cut inside the dosing passage (Metformin every run, Furosemide once), as the prompt's own rule says.

*Chapter 9.* 9.4: template prompt filled 9, 3, 1 of 201 uncovered entries per run (NKDA 2, 1, 1 of 58; tobacco denials 4, 1, 0 of 53; alcohol denials 3, 1, 0 of 49); rule prompt 0, 0, 0. Scorer widened: silence statements with "explicitly/specifically" and "specified" ("Not explicitly stated in conversation", "Not specified in conversation"), and nasal-symptom words as non-drug allergy; four such entries had scored as claims; the first recording scores identically under the widened rules. 9.6: required fields 565 fillers and 19 inventions of 603 (16 negatives such as "No tobacco use reported" whose own quote says the topic was never mentioned), optional 1; the quote check caught 16 of 20 inventions, nulled 584 of 595 fillers, and rejected 18 of 106 and 10 of 94 sound values: read, 19 correct values wrongly rejected (most a question and its answer joined into one quote), 7 unsupported values rightly rejected, 2 misfiled. 9.7: rejections 1 of 80 with the list against 7 of 75 with one quote (same filter: values that state something on a discussed topic; the first write-up's "3 of 92 / 75 vs 92, model more conservative" compared different filters, same filter 3 of 76 vs 0 of 75); no invention; 47 of 102 values carried two or more quotes. 9.5: notes 13 invented / 83 discussed, records 20 / 55; Sonnet 5 and the writer each caught 31 of 33, each passing two different D2N088 seasonal-denial records, so the checking model made no difference (first recording: 17 vs 14 of 19, the writer approving 5 of its 8 generalisations); the book's step 3 no longer asks for a different model. Embedding (from scratch): 9 of 13 caught with 0 of 83 flagged at similarity 0.3, the misses the four NKDA; all 13 only at 0.6 with 46 flagged. Guardrails (rebuilt `.venv-guardrails`, reproduces the first log exactly on the first recordings): as shipped 7 of 13 caught, 15 of 83 flagged, every one of the 15 from a transcript the sentence splitter cannot divide (19 of 60 have no full stops; the whole conversation becomes one window: "Alcohol use: one to two beers on weekends" is 0.19 from the patient's answer and 0.96 from the window); loosest catch-all flags 60 of 83 (one-sentence windows); AUC 0.71 notes, 0.77 records. Figure 9-2 now shows that case.

**Chapter 10 re-recorded at the API default, 14 Nov 2026.** Every affected Chapter 10 experiment was recorded again with each model at its API default (Haiku 4.5 thinking off; Sonnet 5 adaptive thinking at effort high); the first recordings stay in the `_cli_defaults` folders and replay with `CLI_SETTINGS=cli`. Five conclusions moved. (1) 10.7: Haiku now lists 72–77 medicine names with no amount in `extracted` itself, and the one-line narrowing instruction made the field longer (210/226/203 entries against 177/190/169); with thinking it had cut 137–149 to 57–62. Its effect depends on the model setting. (2) The sixty-extraction test of 10.4/10.8 now holds 9 real drops (was 4): the pattern count flags 4, Med7 3, DeBERTa 1; a figure-by-figure comparison with the pattern flags 5; the remaining 4 are Gabapentin's 1,400 mg/day, a table cell with no unit. "The pattern flagged every short list" no longer holds. (3) 10.6: the same-model audit named 27 of 31 known-missing figures (was 10 of 41); on the 6 unchanged API extractions, 11 of 11 against 2 of 11 with thinking. (4) 10.12: Sonnet named 31 of 31 and 3 of the 4 pattern-invisible 1400s, at about six times the cost. (5) 10.11: 12 of 360 replies failed the strict schema (objects instead of strings), and 5 corrections moved dose-less medicines; 10.10's 57 alarms were all the checker's blindness, no invented value, no real catch. 10.3 holds in substance (count = list length in 46 of 54; no mismatch pointed at a real drop). Scorer changes: `probe_count.parse` reads the last fenced JSON block (one reply wrote a corrected second answer); `probe_field_conversation.subclass` files a digit-free extracted item as "a medicine named without any amount" (was "other"). Both leave the first recordings' results unchanged except that label.

*10.4, computed rather than re-run.* en_core_web_trf's per-document counts from the first run (Amoxicillin 10, Lisinopril 8 with the lab value, Sertraline 6, Levothyroxine 3, Warfarin 2, Gabapentin below every list; the label text did not change) against the new 60 extractions: 4 of 9 real drops (all Amoxicillin), 0 of 4 other-drug, 10 of 47 complete flagged (Lisinopril; 0 with the "/dL" skip). The model's 457 MB wheel could not be downloaded here (about 26 KB/s from GitHub); `probe_ner.py` will confirm once installed.

**Experiment 10.9 at the API's default setting, 14 Nov 2026.** The 9.4 notes it reads and the fix-3 audit were re-recorded with thinking off (MAX_THINKING_TOKENS=0; first recording kept in the _cli_defaults folders). Fix 1: 208 of 360 notes flagged (template 37/32/35, permission 32/36/36; first recording 188). Every flag classified, every remaining drug word opened in dialogue and note: 110 junk only (first names, fillers, months, places, conditions, tests, diet words); 68 with every drug word in the note (24 renamed — acetaminophen 20, betamethasone 3, ibuprofen 1; 22 the same word, which Med7 did not count in the note; 22 a class or other words, e.g. "migraine medication" = propranolol); 30 with a drug word absent: prednisone asked about and never confirmed (D2N026, 6), Vicodin declined / antibiotics judged unnecessary / carvedilol a future option (8), insulin named only because the patient does not take it (D2N160, 6), ibuprofen as "avoid NSAIDs" (2), an alternative or past treatment (Aleve beside the prescribed ibuprofen, past ED and childhood antibiotics, past high-dose gabapentin; 7), and one list change left out (D2N145 permission run 3: clindamycin removed from the list; the other five notes record it). Medicines in use dropped, among the flags: 0. Fix 2: does not run. Fix 3: 60 calls, $0.48 at API prices, 268 s; 223 claims across 57 of 60 notes; 2 replies unparsable (commentary written after a closing quote inside the JSON: D2N030, D2N182). Every claim read against dialogue and note: 83 already in the note, 1 a dose the note carries (amlodipine 10 mg, false by 10.5's record), 30 not in the conversation (13 "allergies / family history / vital signs not documented" where nobody discussed them; vital-sign, A1c and blood-pressure values the doctor read from a screen without saying them; an AF drug, an antidepressant name, a prior lisinopril dose, a "new anxiety medication", a methotrexate dose, never named; two age/date-arithmetic claims; one critique of the plan), 96 real absent content whose note-worthiness is editorial, 3 trivial. Three are real omissions that matter: D2N025 oxybutynin ("i think the oxyglutinine is helping as well", urgency much better) is in neither the note's medication list nor its text (absent from 4 of the conversation's 6 notes; Med7 does not tag the garbled spelling, so fix 1 cannot see it); D2N093 the negative suicide/homicide screen ("you don't want to hurt yourself or anyone else?" — "absolutely not") is not recorded (the first recording's note had it); D2N023 gynecomastia, named by the doctor as the patient's other area of concern, is absent. Seven claims point at errors written into the note: D2N036 right hand for the left; D2N118 "denies use of television or phone during sleep" where the patient sleeps with the TV on and the phone by the bed; D2N123 "80% of readings within range" where the patient checks 80% of the time; D2N145 tacrolimus "0.1%", a strength nobody stated; D2N100 "18-year-old" for a 7th-grader whose age was never stated, only a date of birth; D2N049 "right flank bilaterally"; D2N026 Eliquis listed beside "denies use of blood thinners", before a planned epidural — a contradiction the conversation itself contains. First recording: the oxybutynin and gynecomastia omissions were in its notes too and its audit flagged both (oxybutynin as "an SGLT2 inhibitor"); the 13 Oct write-up filed them with the editorial content, so "the rest real but judgement-dependent" understated the audit. What thinking off changed: audit replies about twice as long (median 809 vs 363 characters) and 2.5 times as many claims, more of them about content already present or never stated; notes the same length (median about 2,560 characters), but four of the seven note errors (D2N036, D2N118, D2N145, D2N049) and the lost suicide screen (D2N093) are new. Verdict unchanged in kind: on prose the audit is the one fix that runs, and it is a reading feed, not a gate. It is a feed worth reading, because it finds a dropped medicine and errors the note introduced among claims that mostly need no action.


## Chapter 3's verification advice follows Chapter 9 (15 Nov 2026)

Chapter 3 said "Any verification mechanism that uses the same model that
generated the content will fail at exactly the class of fabrication that the
generative step failed at", and its desk tip said never to ask the model that
produced an output to check it. Neither claim was ever measured in this
repository. The one measurement of it here contradicts the absolute: at the API
default (Experiment 9.5, on 9.4's notes and 9.6's records, re-recorded 14 Nov
2026), the model that wrote them, shown the conversation in a call of its own, caught every invented
entry with no evidence behind it, and so did Claude Sonnet 5; on the seven that
widened a real answer each caught five, not the same five. The same-call
self-check measured in Chapter 10 (Experiment 10.3, step 3) still flagged none
of the lists that were missing doses. What separates the two is whether the
checker gets the source, in a separate call. Chapter 3's tip, its
"Do not use the same model" paragraph, prevention item 4, two Quick-reference
cells and one Monday-morning question now say that: the checker must see the
source; it can be the same model, another model, a rules pass or a person; a
claim that widens the source goes to a person. Book only: no experiment or
number changed.

## Experiment 10.4 re-run with the model installed (15 Nov 2026)

The 14 Nov note above computed 10.4 from the first run's recorded counts because
the model's 457 MB download from GitHub would not finish (about 29 KB/s per
connection). It finished over 32 parallel range requests (zip CRC check clean)
and `probe_ner.py` ran (spaCy 3.8.7, en_core_web_trf 3.8.0, CPU; output in
`ch10-silent-omissions/ner_trf_out.txt`). Every flag matches the computed
result: 4 of 9 real drops, all Amoxicillin; 10 of 47 complete runs flagged, all
the Lisinopril lab value, 0 with lab values skipped; pattern count 4 of 9, 5 of 9
by figure comparison, 0 false. One recorded count was wrong: Levothyroxine's
tagger count is 8, not 3. Its flag does not change (8 is below the 12 to 14
figures every Levothyroxine list carries); Table 10-2 and the report now print 8,
and Gabapentin's cell prints its count, 13.
