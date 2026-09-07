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
| **3** | fabrication rate, soft-inference prompt | **92%** (44/48) | **23%** (11/48) | the repo's strongest result |
| **3** | fabrication rate, neutral prompt | 29% (14/48) | — | baseline |
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
| **7** | aggregate correctness across every subclass | **100%** (144/144) | **82%** (118/144) | the fix is a regression |
| **7** | legitimate queries answered | 100% (48/48) | **46%** (22/48) | |
| **8** | placement error rate | 3% (1/33) | 3% (1/33) | *[noise]*, and the 1 is a checker bug — §3 |
| **8** | model named the wrong section for its own quote | 18% (6/33) | 3% (1/33) | **0/33 real** — §3 |
| **9** | fabrication on fields with no source content | 29% (14/48) | **0%** (0/48) | forced by construction — §1 |
| **9** | recall on fields the document does cover | 96% (23/24) | 92% (22/24) | *[noise]* — but it did move |
| **9** | fabrications whose quote IS in the document | **100%** (14/14) | — | the finding |
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

Chapter 7's fix then makes things worse: aggregate correctness 144/144 → 118/144,
legitimate queries answered 100% → 46%. And 96 of its 118 correct answers involve
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

The −69-point grounding-template result across four models is unaffected.

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
| **mean** | **91%** | **20%** | **$22** |
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

**8 of 14 published headline figures fall outside their own 3-run range:**

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
