# Review — nine chapters, audited before the author sees them

Adversarial read of all nine built chapters, the shared harness, and the three
consolidated documents. Everything below was re-derived from the committed
fixtures or from fresh live sampling; nothing is taken on the word of a chapter
README.

**Conditions.** Claude Haiku 4.5, 12 FDA drug labels, replayed offline on
Python 3.9.6, 23 August 2026. `shared/llm.py` was not modified.

**Bottom line.** The engineering is careful and the chapters are unusually
honest about their own null results — ch04 and ch07 both open by saying the
failure barely reproduces, which is the right instinct. But **six of the nine
chapters have a headline number I would not publish as it stands**, and two of
them (ch09, ch08) are the ones the book leans on hardest. The single largest
problem is not any individual bug: it is that **no number in this repo has ever
been measured twice**, and where I measured them twice the spread is as large
as most of the reported effects.

---

## What I did that the repo has not

`shared/llm.py` never sets `temperature`, so every call in the repo — all 3,300
recorded ones — was sampled at Anthropic's default of 1.0. Nothing is
greedy-decoded and nothing has a seed. ch04's README asserts a noise floor
(94/96 then 93/96) but no second run is committed anywhere, so it cannot be
checked.

So I measured it. I copied four chapters' `broken.py` into a scratch directory
with an empty fixture cache and ran each **three times live**, on identical
inputs and identical prompts. Committed fixtures were not touched.

| chapter · metric | committed | run 1 | run 2 | run 3 |
|---|---|---|---|---|
| **ch09** fabrication on unsupported fields | **14/48** | 13/48 | 12/48 | 12/48 |
| **ch09** recall on supported fields | 23/24 | 23/24 | 23/24 | 23/24 |
| **ch08** placement error rate | **1/33** | **0/33** | 1/33 | **0/33** |
| **ch08** quote matches no section | 1/33 | 1/33 | 0/33 | 1/33 |
| **ch08** model named wrong section for own quote | **6/33 (18%)** | **2/33** | **3/33** | **2/33** |
| **ch10** dose figures returned | 55/55 | 55/55 | **54/55** | **51/55** |
| **ch10** documents silently truncated | **0/6** | 0/6 | **1/6** | **2/6** |
| **ch05** values findable in source | 45/**70** | 44/**69** | 51/**77** | 45/**65** |
| **ch05** qualifier retention | 11/38 | 10/38 | 11/38 | 11/38 |
| **ch05** dose ranges preserved | **7/11** | **9/11** | **8/11** | **8/11** |

Cost: $0.55. This is the most useful half-dollar anyone has spent on this repo,
and it should become a `--repeat N` flag rather than a one-off.

**Read the bold cells.** In four separate places the committed run sits at the
edge of the distribution, and in two of them the committed run is the *only* one
that supports the chapter's claim.

---

## Problems, ranked by how much they would change a conclusion

### 1. ch09's provenance check is the ground-truth answer key, applied as a filter

**This is the most serious finding in the review.** It invalidates the repo's
single most-cited result.

`ch09-sparse-field-fabrication/fixed.py:62-69` defines `SUPPORTING_SECTIONS`,
mapping each field to the section allowed to support it. `enforce()` (line 121)
locates the quote among `case["section_texts"]` — which `common.py:112-116`
builds from `CONTEXT_SECTIONS` only, i.e. the two sections that were supplied.

Ground truth in `common.py:131` is `present = (section in CONTEXT_SECTIONS)`.

Those are the same predicate. Proved by enumeration:

| field | `SUPPORTING_SECTIONS` | can it ever be located? | ground-truth `present` |
|---|---|---|---|
| `indications` | `{indications_and_usage}` | yes | True |
| `adult_dosage` | `{dosage_and_administration}` | yes | True |
| `pediatric_dosage` | `{pediatric_use}` | **never — not supplied** | False |
| `pregnancy_guidance` | `{pregnancy}` | **never** | False |
| `overdose_management` | `{overdosage}` | **never** | False |
| `drug_interactions` | `{drug_interactions}` | **never** | False |

For all 48 fields scored as "no source content", `located` can only be one of
the two supplied sections, and neither is in `allowed`. **Every one is nulled
unconditionally.** `0% (0/48)` is arithmetic, not measurement. It could not have
come out any other way, on any corpus, with any model, at any temperature.

The chapter's defence — *"the mapping is a design decision your team makes, not
something the model produces, and that is why it holds"* — is correct **in
production** and vacuous **in this experiment**, because here the mapping and
the answer key are the same object. To measure the check you need cases where a
supporting section *is* supplied and misattribution is still possible. There are
none.

Two things the check *does* measure, and they are worth keeping:
- It nulled **2 of 24** legitimate `adult_dosage` fields (null rate 17%, 2/12).
  That is the false-positive rate of quote-location, and it is real.
- The null-rate monitoring signal ("0% on supplied vs 100% on absent, separates
  cleanly") is produced by the same tautology. It is not evidence.

**Do not publish** FINDINGS §3's *"That check alone takes fabrication from 29% to
0% with no loss of recall"* or FIX_STATUS fix #2. Both sentences are wrong twice
over — the check is circular, and recall did move (see #3).

---

### 2. ch07's baseline is a null result and its fix is a pure regression, with 96 of 118 "correct" answers backed by no model call

`ch07-edge-input/broken.py` scores **144/144**. Zero injections obeyed, zero
out-of-scope queries answered, 100% of legitimate queries answered. The failure
the chapter is named after does not reproduce at all.

`fixed.py` then makes every number worse: legitimate queries answered
100% → **46% (22/48)**, in-distribution controls 24/24 → 22/24, aggregate
144/144 → **118/144**.

Worse, the two rows that read as "unchanged" are not comparable. `common.py:387`
short-circuits scoring for any input the gate blocked:

```python
if blocked_by:
    answered = canary = obeyed = False
```

Then `expected == "decline"` scores `not answered` and `expected == "no_canary"`
scores `not obeyed` — so a blocked input is **correct for free**. In the fixed
arm, 122 of 144 cases never reached the model. **96 of the 118 correct answers
(81%) involved zero model output.** The two `0% (0/48)` rows printed side by
side against the baseline are, on the left, 48 real model responses and, on the
right, arithmetic over an empty set.

Consequence: the hardened system prompt — every SCOPE RULE and ROBUSTNESS RULE
in `fixed.py:217-240` — was **never exercised against a single adversarial,
out-of-scope or OOD input**. Only the 22 in-scope queries reached it.

Also: the 144 cases are **22 unique query strings**. Eleven of twelve subclasses
use one identical string replicated across 12 drugs, and the OOD gate only sees
the query. So *"24 legitimate queries destroyed"* is **two sentences**, counted
twelve times each. The clean multiples of 12 throughout the threshold sweep are
the tell.

---

### 3. Every claim of "no cost to recall" is wrong, in three chapters

| chapter | claimed | actual, from today's fixtures |
|---|---|---|
| ch09 | recall unchanged at 96% (23/24) | **92% (22/24)** — 1 legitimate field lost |
| ch10 | *"Unchanged from the baseline"* (hardcoded note in `fixed.py:139`) | **96% (53/55)** vs 100% (55/55) — the note contradicts the number printed one line above it |
| ch07 | fix 1 cost "2 legitimate queries" | **3** — the third is masked because the OOD gate fires first |

ch10's is the worst of the three because the false statement is *in the program's
own output*, not in a document someone forgot to update. Anyone running
`fixed.py` reads `>> Dose figures returned: 96% (53/55)` immediately followed by
`Unchanged from the baseline.`

(One of ch10's two lost figures is `10 mg` for Gabapentin, which is a reference-set
artefact — see #5. The real loss is 1 case, which is inside the noise floor.)

---

### 4. ch04 changes the denominator between arms; ch05 lets the model choose it

**ch04.** `broken.py` reports accuracy over 96 passages; `fixed.py` reports it
over the **95** and **91** that survived the confidence gate
(`fixed.py:255` scores `auto` only). "97% (93/96) → 100% (95/95)" is not a
comparison — the fix's denominator excludes exactly the cases it withheld.
The per-category F1 gate has the same defect: computed on post-router survivors,
it *structurally cannot fire* if the router works, and `fixed.py` duly reports
all ten categories at F1 1.00. The README's F1 numbers (0.74, 0.77) are quoted
from the **broken** arm.

**ch05.** `common.py:58-71` declares `fields` as an unbounded array. The prompt
asks for four; nothing enforces four. So the model chooses the denominator:

| | broken | fixed |
|---|---|---|
| Metformin | **11** fields | **4** fields |
| Gabapentin | 9 | 12 |
| Atorvastatin | 11 | 12 |
| **total** | **70** | **66** |

`45/70` and `62/66` are 70 unpaired items against 66 different unpaired items.
My three live re-runs of the *same broken prompt* produced denominators of
**65, 69 and 77** — the denominator moves more between samples than the metric
does. On a common denominator (first four fields per document) the effect is
**52% (25/48) → 91% (43/47)**: still real, still worth publishing, but not
"64% → 94%".

And the two sides count different objects. **37 of broken's 70 "findable"
values are ≤6 characters** — `'1'`, `'2'`, `'3'`, `'10'`, `'80'` — which score
100 against any 3,500-character source. In `fixed.py` that count is **1 of 66**.
The baseline is being credited for single digits matching somewhere.

---

### 5. Reference regexes that are wrong in the same way ch10's `VKORC1` bug was

The `VKORC1−1639G` fix in `ch10/common.py:45` patched two specific shapes. The
underlying class was never addressed, and it recurs in three chapters.

**ch10 — 31% of the reference set is not a dose figure.** `DOSE` matches a number
followed by a unit, so `15 mg/kg/day` scores as a 15 mg dose. Measured:

| drug | figures appearing **only** as per-kg/per-m² rate coefficients |
|---|---|
| Levothyroxine | **8 of 11** |
| Gabapentin | **6 of 13** |
| Amoxicillin | 2 of 10 |
| Sertraline | 1 of 7 |
| **total** | **17 of 55 (31%)** |

**ch06 — the chapter's central metric is a unit-attachment artefact.** `DOSE`
(`common.py:50-54`) includes `mL` under `re.IGNORECASE`, so `15 mL/min`
creatinine clearance reads as a dose. Both "novel dose values" that admitted the
Gabapentin renal subsection to the corpus are eGFR thresholds. Meanwhile the
flattened FDA table the model was shown — `"≥60 900 to 3600 300 TID 400 TID …"` —
returns `[]` from `dose_values()`, because no unit sits next to any number. So
the model read the table correctly, re-attached the units, and was scored as
seven fabrications. **All 16 flagged values in all 4 failures are bare numbers
already present in the excerpt.** `common.py:446` asserts *"The value is provably
not in the text the model was handed"*; that is false for every measured case.
The residual real finding is 2/39, not 4/39: on Furosemide and Levothyroxine the
model closed a severed range (`20 to` → `20 mg`).

**ch05 — the unit is optional in `RANGE_RE` (`common.py:50`).** It matches
`ages 6-12`, `every 4 to 6 hours`, `INR of 2 to 3`, `for 10-14 days`, `Table 1-2`
— and, tested directly, `VKORC1-1639G` → `1-1639`. **5 of the 11 documents in
the "dose ranges preserved" denominator contain no dose range at all.**
Warfarin's "range kept = yes" on both sides is `1 to 4`, the INR check interval.

FINDINGS keeps `64% (7/11) both ways` as a null result. It is not a null result;
it is an unmeasured quantity. My three live re-runs of the broken arm gave
**9/11, 8/11, 8/11** — the baseline alone moves more than the reported effect.

---

### 6. ch08 measures one case, and that case is a checker bug

Every ch08 headline is 0 or 1 events out of 33.

The chapter's single placement error is **not a placement error**. The quote is
genuinely in `contraindications`; `locate()` (`common.py:60-69`) compares only
the first 80 characters (`VERIFY_WINDOW`), and those 80 characters are the drug
name and strength, which every section of an FDA label repeats:

```
window=80   indications 100.0  contraindications 100.0  adverse 100.0  → indications  (first match wins)
window=200  indications  69.0  contraindications 100.0  adverse  65.0  → contraindications
window=0    indications  54.8  contraindications  92.2  adverse  49.8  → contraindications
```

At any window other than 80, **misplaced = 0/33 on both sides.** The model was
right; the checker was wrong. And `fixed.py`'s rules engine fires exactly once
in the whole chapter — to reject that correctly-extracted contraindication. The
review queue's only row is a false rejection, and "Boxes filled and stored:
97% (32/33)" is 3% of good data thrown away.

`fixed.py:138-143` is worse:

```python
pct(0, len(all_rows)) if not misplaced else pct(0, len(all_rows)),
```

Both branches are identical and the value is the literal `0`. "Placement errors
that survived into storage: 0% (0/33)" is hardcoded. If the rules engine stored
every misplaced box, this line would still print `0%`.

`VERIFY_WINDOW = 80` was tuned in ch09 to protect **recall on long paraphrased
quotes**. Importing it into ch08, where the task is **precision on section
attribution**, is the actual bug — one shared constant, two incompatible jobs.
This is a fourth instance of the pattern the brief flagged: shared code reviewed
twice and still wrong.

---

### 7. ch02's fix is scored under a different definition than its baseline, and 35 of its 41 denominator slots cannot fire

Two defects compounding.

**Different definitions.** `broken.py:73` counts a silent corruption as
`changed AND confident`; `fixed.py:61` counts it as `changed` alone. The
published pair `24/41 → 4/41` applies neither definition consistently. Held
constant it is `31/41 → 4/41`, or `24/41 → 3/41`.

**Rejected-as-success.** `fixed.py:57-59` skips any case the gate blocked, but
`fixed.py:82` divides by all 41. Only **6** of the 41 slots are eligible to be
counted. Among documents the gate actually passed to the model, **4 of 6 (67%)
still stored a wrong value — higher than the 59% baseline.** The honest sentence
is *"the gate cut exposure from 41 documents to 6; of those 6, four were still
silently corrupted"*, and that is a better sentence than "10%".

**The gate is the inverse of the corrupter.** `corrupt()` and `validate()` sit
50 lines apart in the same file, by the same author. Three of four checks undo
three of four corruptions exactly — `GARBLE` is literally the character set that
latin-1 mis-decoding emits. Decomposed: **29/29 (100%) on the three inverted
modes, 6/12 (50%) on OCR**, the one that is not inverted. A reader importing this
gate gets the 50%.

Separately, the false-alarm rate is a mis-set constant, not a cost of the
approach: at a 1% non-ASCII threshold instead of 0.4%, the gate catches **the
same 35 damaged documents and halves the false alarms to 1/12**.

---

### 8. ch06's stale-index result is true by construction, and its version model is not a version chain

`fix_freshness.py:53` sets `STALE_INDEX_DATE = "20260101"`. The six ACTIVE labels
have effective times `20260109 … 20260717` — **all six post-date the cutoff**, so
the stale index arithmetically cannot return an ACTIVE label. "Correct-looking
filter over a stale index: 100% (6/6)" is a tautology given a date chosen eight
days before the earliest ACTIVE label. Move it to `20260109` and it reads 83%; to
`20260602`, 50%.

`fix_freshness.py:290` claims *"Every one of these passes a status check."* The
stale query (`:198-203`) has **no status clause at all**. For Furosemide — the
drug producing the `579 days` headline — the served document would have been
SUPERSEDED even inside the stale index.

**And the version model itself does not hold.** `data/label_versions.json` has 48
records, 8 per drug, and **48 distinct `set_id`s across 39 distinct labelers**.
No `set_id` repeats. These are eight *different repackagers'* labels for the same
generic — St. Mary's Medical Park Pharmacy, Bryant Ranch Prepack, PD-Rx — not
eight revisions of one document. **No ACTIVE label shares a labeler with any
document called SUPERSEDED against it.** Calling Aphena's 2023 Lisinopril label a
superseded version of St. Mary's 2026 label is a modelling choice, not a
derivation, and the file's own note (*"status is derived"*) papers over it.

Everything downstream inherits this: ch03's *"83% of unfiltered retrievals were
superseded"* and *"oldest 7.5 years stale"*, and all of ch06's freshness work.

Also fragile: at `now() = 20260822` the book-filter empties 2/6. Lisinopril's
ACTIVE label is 81 days old — **nine days** from flipping the headline to 3/6.
The date is hardcoded so it will not drift, but a corpus refetch moves it.

---

### 9. Metrics that are string equality over independently sampled free text

`ch06/fix_freshness.py:237` and `ch03/fix_retrieval.py:141`:

```python
differ = normalise_ws(stale_answer) != normalise_ws(active_answer)
```

`normalise_ws` lowercases and collapses whitespace. Both report **100% (6/6)**.
At temperature 1.0, two samples of the *same* context would also differ close to
100% of the time on free text. There is no same-context control anywhere in the
repo, so "100% of answers changed" is not established as measuring retrieval.

ch02 has the same shape: its "reference" clean answer is one sample. Of the 24
counted as silent corruptions, **12 have an identical set of dose figures** and
differ only in wording (`'5 mg to 60 mg per day'` vs
`'5 mg to 60 mg of prednisone per day'`). On Atorvastatin the *three damaged
variants agree with each other byte-for-byte* and only the clean reference
differs — the signature of the reference being the outlier draw.

Cheapest fix in the review: sample each clean document twice, 12 extra calls,
about $0.01, and report the self-disagreement floor.

---

### 10. Absence predicates that are hand-written phrase lists, and that misfire

`ch09/common.py:64-82` and `ch04/common.py:167-179` decide the outcome variable
with 17–18 unanchored substrings including `"does not"` and `"no specific"`. Both
files claim the list is *"deliberately generous — anything ambiguous is scored in
the model's favour"*. It is the opposite. Verified in ch04: **11 of 14 opening
declines and 6 of 12 body declines are false**:

> `"Overdose of atorvastatin has no specific antidotes. Management involves…"` → scored DECLINED
> `"Chemical name: Lisinopril - (S)-1-[N2-(1-carboxy-3-phenylpropyl)…"` → scored DECLINED

Corrected, ch04's counter-metric moves from **85% (79/93) to 97% (90/93)** on
opening and **86% → 92%** on body. That inverts the README's argument: the
extractor declines on 1 correctly-labelled passage in 31, not 1 in 7, which
*weakens* the cascade rate's interpretation.

ch04's comment says the predicate is *"lifted from ch09 … the same predicate, so
the two chapters' numbers are comparable"*. Diffed: five markers differ; ch09 has
`"no pediatric"` and `"not in the"`, ch04 does not; ch04 has three dead entries
that are strict supersets of markers already present. They are not comparable.

---

### 11. ch04 classifies a third of its corpus twice and counts it twice

`common.py:248`: `index = {"first": 0, "middle": len(pieces) // 2, …}`. For a
section yielding one chunk, `0 == 0 // 2`. **32 of 96 sections yield one chunk**,
so `--chunk first` and `--chunk middle` hand the classifier a byte-identical
passage, hashing to the identical fixture. Zero of those 32 answers can differ.

- *"requires_human_review matched on 100% of **192** classifications"* → effective n is **160**.
- *"accuracy falls from 97% to 91% … purely on where the passage was cut"* → on the 64 passages actually cut differently it is 63/64 → 57/64. For the other third **nothing was cut differently**.
- *"**8 of the 12** misclassifications produced confident downstream output"* → 12 slots are **10 distinct passages**; the correct figure is **6 of 10**.

Separately, `LEAK_PHRASES` contradicts its own stated rule. The comment says a
section leaks when the body contains **the section title**; the code adds
`"contraindicated"`, the ordinary verb every contraindication passage uses. All
six flagged contraindications passages contain `contraindicated` and not
`contraindications`. Remove that one word and the leak rate drops from 29% to
23% (opening) and 25% to 19% (body).

And the leak matters more than the README lets on: split by leak, **every one of
the three prompts scores 100% on every leaking passage, in both configurations**.
Every misclassification lives in the non-leaking subset. On passages that do not
name their own section the book prompt scores **96% and 88%**, not 97% and 91%.

---

### 12. Fixes credited to the fix that run identically in both arms

- **ch04 fix 3 (per-category F1 gate)** — called at `broken.py:89` *and* `fixed.py:275`.
- **ch04 fix 4 (audit trail)** — called at `broken.py:86` *and* `fixed.py:272`; `alternative_considered` is already in `broken.py`'s schema.
- **ch05 "52 losses vs 0 in the baseline"** — `broken.py` never imports `normalise`. The 0 is not a measurement; the baseline was never instrumented. **Running the identical `normalise.py` over broken's own values yields 53 discard rows — one more than the fix.** The underlying argument (the fix *records* what the baseline swallows) is sound; the number is a definitional artefact printed in bold in two documents.
- **ch06 "characters discarded: 0 vs 123"** — `naive_cut` returns `text[:budget]`, so `discarded = budget - len(context)` is 0 by definition on the left.

---

## Reported results I believe are inside the noise floor

Measured floor: **±1–2 cases per ~40 samples** (my three-run spreads above;
ch04's own 94/96-vs-93/96 report). At n=24 that is ±4 points; at n=48, ±4 points;
at n=33, ±6 points.

**Inside the noise — do not publish as effects:**

| chapter | result | why |
|---|---|---|
| ch08 | placement error 3% (1/33) → 0% (0/33) | 1 case, and it is a checker bug. Baseline is 0/33 on two of three fresh runs |
| ch08 | quotes matching no section 1/33 → 0/33 | 1 case; my runs give 1, 0, 1 |
| ch08 | boxes stored 97% (32/33) | 1 case, and it is the false rejection |
| ch09 | recall 96% (23/24) → 92% (22/24) | 1 case; 23/24 on all three of my fresh baseline runs |
| ch10 | dose figures 100% (55/55) → 96% (53/55) | 2 cases, one an artefact; baseline itself runs 55, 54, 51 |
| ch10 | documents silently dropped 0/6 | baseline runs 0, 1, 2 of 6 across three samples |
| ch05 | dose ranges 7/11 both ways | baseline alone runs 9, 8, 8 of 11; and 5 of 11 are not ranges |
| ch05 | qualifier retention 11/38 → 17/38 | 6 cases, of which **3 come from the fixed prompt naming six of the seventeen scored stems verbatim** |
| ch04 | fix 1, opening: 3 wrong → 2 wrong | 1 case; the README says so |
| ch04 | fix 1, body: 2/9 errors flagged, 3/5 flagged-already-right | 2 and 3 cases; README quotes both as findings without a caveat |
| ch04 | book-vs-naive gap on opening (95 vs 93) | 2 cases, carrying the *"the book's template is the worst classifier"* claim |
| ch04 | MEDIUM accuracy 0% (0/1) opening, 60% (3/5) body | n = 1 and n = 5 |
| ch06 | MIDFACT 4/39 → 0/39 | 4 cases, reducing to **2** once the `mL` bug is fixed. Fisher p = 0.12 is hand-written prose, not computed anywhere |
| ch06 | prompt protocol 5/6 → 2/6 and 4/6 → 2/6 | 2–3 cases out of 6, and the gain is bought by refusing (0/6 → 2/6 refused, with no recall counter-metric) |
| ch06 | freshness scoring disagrees 3/6; filter empties 2/6 | n = 6, and 2/6 is 9 days from being 3/6 |
| ch07 | in-distribution controls 24/24 → 22/24 | 2 cases — the entire "the fix hurt in-scope traffic" claim |
| ch07 | `--no-ood` aggregate 141/144 | 3 cases; README line 151 says it *"loses nothing"* while its own table on line 68 says 100% → 98% |
| ch02 | silent corruptions survived 4/41 | 1 case from opus's 5/41, and only 6 slots can fire |
| ch02 | clean inputs wrongly rejected 2/12 | deterministic, so not decode noise — but both are artefacts (one is the corpus builder's 500-char floor disagreeing with the gate's 900-char floor on a 739-char Omeprazole excerpt) |

**Outside the noise, and I would publish:**

- ch03 soft-inference vs neutral baseline: **92% (44/48) vs 29% (14/48)**. A 63-point, 30-case gap. The strongest result in the repo.
- ch03 grounding fix: 92% → 23% (11/48). 33 cases.
- ch09 baseline fabrication ≈ 25–29%: three fresh runs gave 12, 12, 13 of 48. Stable.
- ch09 *"100% of fabrications carried a quote genuinely in the document"* (14/14). Structural, not marginal, and the best-constructed finding in the repo.
- ch04 fix 2 on body passages: 9 wrong → 0. 8 cases.
- ch06 monitoring recall **50% (20/40)** with **0/1381** false alarms. Fully deterministic, no model calls, no regex in the ground truth. The cleanest result in ch06 by a distance.
- ch02 gate catch rate 35/41 and calls avoided 37: model-free, byte-stable across all three models in the sweep.
- ch09 `partial_ratio` window sweep (recall 54% → 95%): mechanical, and the effect is 40 points.

---

## Ground-truth derivations I do not trust

Ranked by how much weight they carry.

1. **ch09 `SUPPORTING_SECTIONS`** — is the ground-truth predicate. Circular. (#1)
2. **ch06 `DOSE` regex** — reads eGFR thresholds as doses and cannot see flattened tables, so "provably not in the text" is false for 16/16 flagged values. (#5)
3. **ch10 `DOSE` regex** — 17/55 of the reference set are per-kg rate coefficients. The `VKORC1` patch fixed two shapes, not the class. (#5)
4. **ch05 `RANGE_RE`** — unit optional; 5/11 documents in the denominator have no dose range. Reproduces the `VKORC1` failure directly. (#5)
5. **ch08 `locate()` at `VERIFY_WINDOW=80`** — first-match-wins over a prefix that every section repeats. Four quotes match all three sections; ties always go to `indications_and_usage`. (#6)
6. **ch08 `canonical_section`** — strips punctuation but not section numbers, so `4_contraindications` ≠ `contraindications`. **All six "the model named the wrong section" cases named the right section.** (#13 below)
7. **ch06/ch03 `label_versions.json`** — 48 distinct labelers' documents presented as a version chain. (#8)
8. **ch09/ch04 `is_absent_answer`** — hand-written phrase lists, with false positives that move ch04's counter-metric by 12 points. (#10)
9. **ch04 `HEADER_ALIASES` (25 strings) and `MIN_SECTION_CHARS = 200`** — the alias list is hand-labelling against one corpus snapshot and silently rots on refetch; the 200-char floor deletes 8 real sections, two of which miss by 3 and 8 characters.
10. **ch03's judge** — the headline fabrication rate is produced by a Sonnet 5 model call (`common.py:98-112`). The repo discloses this and pins the judge model, which is right. What is missing is **any measurement of the judge's own reliability** — no human spot-check, no agreement rate. A repo whose recurring thesis is *"model self-assessment is unreliable"* should not leave its flagship number resting on an unvalidated model classifier.

**Derivations I do trust:** ch03/ch09's `answerable`/`present` flags (with the
caveat in #14), ch04's `true_category` from openFDA section names, ch07's
by-construction adversarial set and its canary substring test, ch06's
`fix_monitoring` ground truth, and ch02's corruption modes.

---

## Cross-chapter contradictions

**13. The self-assessment finding is counted three different ways and two of the five instances measure nothing.**

The brief says it has been measured five ways. The repo cannot agree on the
count:

| location | claim |
|---|---|
| `report/parts/07-ch10.html:198` | *"arriving a **third** time from a third direction"* |
| `ch04/README.md:180` | *"This is the **fourth** time this repo has measured self-reported confidence"* |
| `ch07/README.md:156` | *"**Three earlier** measurements … this is the **fourth**"* |

Two chapters both claim to be fourth. The actual instances are ch02 (confidence
on damaged input), ch03 (the judge), ch04 (LOW never issued), ch07 (injection
classifier), ch08 (self-reported section), ch10 (self-count) — six, or five if
ch03 is excluded.

Worse, **two of them do not measure what they say**:

- **ch02's 83% (34/41)** has no control. Re-derived: `confident=False` on damaged is **17.1% (7/41)**; on clean it is **16.7% (2/12)**. The flag separates clean from damaged by **0.4 points** — it has zero discriminative power, which is a *stronger* version of the chapter's claim, sitting unused. And all 9 non-confident answers come from two drugs (Levothyroxine, Warfarin, both of whose labels say "dose must be individualized"). The flag tracks the drug, not the damage.
- **ch08's 18% (6/33)** is 0/33 real. All six named the section as printed in the document, including its number, which is what the prompt asked for. Cross-model the number is 18% / 64% / 12% — a 52-point spread that tracks how verbosely each model writes a header. My three fresh Haiku runs give **2/33, 3/33, 2/33 (6–9%)**, so the committed 18% is also a high outlier.

This matters beyond ch08. **`ch09/fixed.py:108-113` and `ch09/common.py:107-108`
cite "about one time in five" as the design justification for locating quotes
independently**, and ch07 counts it as one of its priors. That number is
6–9% on re-sampling and 0% once the string normaliser is fixed. The design
decision is still right; the evidence offered for it is not.

**14. Two chapters describe the same ground truth two different ways, and the root README states it wrongly for both.**

Root `README.md:66-68`: *"Prednisone's label has no pediatric-use section,
Sertraline's has no pregnancy section. Those gaps are the ground truth every
chapter scores against."* `FIX_STATUS.md:178`: *"Ground truth is the labels' own
missing sections."*

That is not what ch03 and ch09 do. Both derive it as *"is this section in the two
we supplied?"* (`ch09/common.py:131`, `ch03/common.py:58`). The corpus actually
has these sections in most cases:

| section | labels that have it |
|---|---|
| `pediatric_use` | **8 of 12** |
| `pregnancy` | **7 of 12** |
| `overdosage` | **10 of 12** |
| `drug_interactions` | **10 of 12** |

So for the large majority of the 48 "unsupported" fields, **the document does
cover it — the context window does not.** The metric is still meaningful, but it
is *ungrounded-in-context generation*, not *fabrication about a gap in the
document*, and the model may be recalling genuine label content it was trained
on. The framing needs to change in three places.

**15. ch06 vs ch03 on the freshness filter — confirmed, with a correction.**

Verified: `ch06/fix_freshness.py:186-193` applies `status == ACTIVE AND
effective_int > cutoff` and empties 2/6; `ch03/fix_retrieval.py:117` applies
`{"$and": [{"drug": drug}, {"status": "ACTIVE"}]}` with no date clause. Same
corpus, same `TOP_K = 3`. The contradiction is real and ch03 is the one that is
right.

But ch06's README implies ch03 handles the top-k instability ch06 documents.
**It does not.** ch06 uses `common.stable_top_k` (over-fetch to 64, deterministic
sort); ch03 sorts the *prompt* by id but never over-fetches, so ch03 remains
exposed to the membership instability. That is a live defect in ch03 presented
as fixed.

**16. `FINDINGS.md` says "Furosemide's current label is 226 days old, Sertraline's 215."**

From the code's frozen `now() = "20260822"` the answers are **225 and 214**. Both
figures match **2026-08-23** — the day the README was written — so they were
computed by hand against a wall clock rather than against the pinned date. Small,
but it is the exact drift class this audit exists to catch, caught in the act.
Corrected in `FINDINGS.md`; `ch06/README.md:152` still has it.

---

## Reproducibility

**`python run_all.py` — fails immediately.** There is no `python` on this
machine, only `python3`. Every command in `README.md`, every chapter README, and
`requirements.txt`'s promise all say `python`. On macOS 12.3+ this is the default
state. `python3 run_all.py` works: **17 of 18 scripts pass, 46 s, no API key.**

**`ch03-hallucination/fix_judge.py` cannot replay.**

```
shared.llm.FixtureMissing: No fixture for this request (00a86c86b4e3121bf90a).
```

It depends on `broken.py`'s soft-inference answers to build the judge request.
Those answers were re-recorded; the judge fixtures were not. So
`FIX_STATUS`'s *"LLM-as-judge: 85% recall (41/48), 38% false alarms (9/24)"* and
`COSTS.md`'s *"$41 per 1,000 answers, +4.1 s"* are **not reproducible offline**,
and were measured against a different set of baseline answers than the ones now
committed.

**`python3 prune_fixtures.py --dry-run` aborts** on the same failure — by design
(`prune_fixtures.py:41`), correctly refusing to delete on a partial run. So the
orphan audit cannot be run at all. I reproduced it manually, tolerating that one
failure:

| chapter | fixtures | orphaned |
|---|---|---|
| ch02 | 180 | **127 (71%)** |
| ch03 | 1,855 | **1,484 (80%)** |
| ch04 | 647 | 0 |
| ch05 | 73 | 49 (67%) |
| ch06 | 165 | 0 |
| ch07 | 309 | 35 (11%) |
| ch08 | 63 | 41 (65%) |
| ch09 | 64 | 40 (62%) |
| ch10 | 30 | 12 (40%) |
| **total** | **3,386** | **1,788 (53%)** |

(ch03's figure is a lower bound — `fix_judge.py`'s fixtures could not be marked
in use.) More than half the repository is dead weight, and the chapters with the
heaviest orphaning are exactly the ones whose documented numbers no longer match
their code — see below.

**"No installs" is false for six scripts.** `requirements.txt` opens with
*"Nothing here is needed to replay the recorded runs"* and `README.md:21` says
replaying *"needs no key and no installs"*. But `ch03/fix_retrieval.py:56`,
`ch03/fix_similarity.py:81`, `ch06/fix_freshness.py:82`, `ch06/fix_monitoring.py:46`,
`ch06/fix_prompt.py:89`, `ch07/fixed.py:122` and `ch09/fix_provenance.py:60`
import `chromadb` or `sentence_transformers` **with no fallback**, and neither is
in `requirements.txt`. On a clean machine these need **network** (80–370 MB of
model weights, plus Chroma's ONNX embedder) on a replay that is advertised as
offline. `ch03/fix_retrieval.py` also `shutil.rmtree`s and rebuilds `.chroma/`
— a "replay" that mutates the repository.

**`spacy` is not installed** and is not needed; ch10 substitutes a regex and says
so. No issue.

**`sweep.py` and `run_all.py` both register all nine chapters.** Nothing is
missing. But `report/sweep_results.json` covers only **five** (ch02, 03, 05, 08,
09) and predates ch04/06/07/10. In it:

- **`gpt-5-mini`: 0 of 14 scripts succeeded.** Twelve died on
  `Response hit max_tokens=… and was cut off mid-output`. `REASONING_HEADROOM`
  of 8,000 is not enough, and every `max_tokens` budget in the repo is tuned to
  Haiku's verbosity.
- `claude-opus-5`: 11 ok, 3 failed. `gpt-4.1-mini`: 12 ok, 2 failed.

Two consequences. First, `README.md`'s *"nobody has run that sweep for you"* is
false — it has been run, it is in `report/`, and it contains the repo's only
replication evidence. Second, that evidence contradicts published claims: ch05's
"dose ranges, no change" is **9/11 → 10/11 on opus**, and ch08's placement error
is **0/33 on two of three models**.

Also: `shared/llm.py:279` reports `max_tokens={max_tokens}` in the truncation
error, but the request was sent with `max_tokens + REASONING_HEADROOM`. The
diagnostic names a number that was never used.

**`report/` is stale.** The PDF and `experiments.html` cover six chapters, say
*"Six failure patterns"*, and carry superseded numbers.

**Documented numbers that no longer match the code.** Whether from re-recording
or from stale docs, these disagree today:

| claim | documents say | code prints |
|---|---|---|
| ch03 soft-inference fabrication | 90% (43/48) | **92% (44/48)** |
| ch03 neutral, answerable | 100% (24/24) | **96% (23/24)** |
| ch09 fixed recall | 96% (23/24) | **92% (22/24)** |
| ch09 fields nulled by code | 11 | **13** |
| ch06 Furosemide / Sertraline label age | 226 / 215 days | **225 / 214** |

---

## What I could NOT verify

1. **Whether the committed run is representative for ch02, ch03, ch04, ch06 and ch07.** I re-sampled ch05, ch08, ch09 and ch10 three times each. The other five would cost roughly $3 to do properly. **Settle it:** add `--repeat N` writing `fixtures/run{N}/`, commit three runs, and report every headline as a range. This is the highest-value change available to the repo and it is maybe forty lines.
2. **Whether ch04's asserted noise floor (94/96 then 93/96) ever happened.** Only one fixture set is committed and there is no log. It is consistent with everything I measured, but it is an unverifiable assertion in prose.
3. **Whether ch03's Sonnet judge is accurate.** No ground truth for it exists. **Settle it:** hand-label 30 of the 144 baseline answers as ASSERTED/DECLINED and report agreement. An hour of work, and it underwrites the repo's flagship number.
4. **The corrected effect size for ch06 after fixing the `mL` bug.** I could not re-record offline. My estimate is 2/37 rather than 4/39, which would put Fisher near 0.49.
5. **Whether ch08 would ever produce a real placement error.** Zero in 33 rows at any sane window means the chapter has no positive class. **Settle it:** an adversarial corpus, or many more documents. As it stands ch08 cannot demonstrate the failure it is named after.
6. **Whether `ch07`'s book-specified defence works.** The chapter's *"an eight-line regex beat the model classifier"* rests on a regex the same author wrote against the same author's payloads — four of its eight patterns are dead code and two match nothing except one of the author's own strings. **The book's actual named defence (LLM Guard, Azure Content Safety) was never run.** The finding that survives is only the negative one: `inj_spanish` walked past both.
7. **Whether the Chroma scripts work with no network on a clean machine.** The ONNX embedder was already cached here. **Settle it:** move `~/.cache/chroma` aside and re-run with networking off.
8. **Whether the manuscript cites the numbers I am disputing.** I audited `code/` only. Before anything ships, grep `draft/ebook.html` for `83%`, `18%`, `one time in five`, `64% (7/11)`, `52 losses`, `0 in baseline`, `96% (23/24)` and `90%`.
9. **Cross-model reproduction for ch04, ch06, ch07, ch10.** No fixtures exist and they are not in `sweep_results.json`.

---

## What I changed in the repo

`FINDINGS.md` and `FIX_STATUS.md` were rewritten to cover all nine chapters and
to correct the factual errors listed above. No chapter code, no chapter README,
and no fixture was edited. `shared/llm.py` was not touched.

**One thing to know.** During this review, 593 fixtures were written for
**non-default models** (`gpt-5-mini` 347, `claude-sonnet-5` 216,
`claude-opus-5` 30) at an estimated **$4.12** of API spend — a delegated
cross-model probe that ran past the $1 budget I set. **Zero default-model
(Haiku 4.5) fixtures were written or overwritten**, and every committed Haiku
number reproduces byte-identically after the fact; I re-ran all nine chapters to
confirm. My own noise measurement cost $0.55 and wrote only to a scratch
directory that has been deleted. This repo is not under version control, so
there is nothing to revert to — the additions are new cache keys and are safe to
delete with `prune_fixtures.py` once `fix_judge.py` can replay again.

---

## If you fix five things, fix these

1. **Make `ch09`'s provenance check non-circular**, or state plainly that on this corpus it is the answer key. As written it is the repo's most-quoted result and it cannot fail.
2. **Add `--repeat N` and report every headline as a range.** Six of the nine chapters have a headline inside the spread I measured in one evening for fifty cents.
3. **Fix the three reference regexes** (`ch05/RANGE_RE`, `ch06/DOSE`, `ch10/DOSE`) so a unit-bearing rate, an eGFR threshold and an age band stop counting as doses. The `VKORC1` fix patched two shapes; this is the class.
4. **Raise `ch08`'s locate window or require a margin between best and second-best section** — and delete the hardcoded `pct(0, …)`. Then say that ch08 measured zero placement errors, which is a publishable null result and currently reads as a fix that worked.
5. **Reconcile the self-assessment claim.** Fix `canonical_section`, add ch02's clean-vs-damaged control, settle the count, and drop the two instances that measure nothing. The thesis is right; two of its five legs do not hold weight.
