# Chapter 9 — Sparse field fabrication

> A blank the system will not accept is a blank the model will fill.

That is the chapter's claim. On these 12 drug labels, with Claude Haiku 4.5, it
did not hold: see [Result](#result).

## What this measures

Six fields are requested from every drug label. The model is given two sections
— indications and usage, dosage and administration — so two of the six fields
have source content. The other four count as unanswerable, because the section
that would answer them was not supplied. Most labels do carry those sections
(pediatric use in 8 of 12, pregnancy in 7 of 12, overdosage and drug
interactions in 10 of 12), so the test asks whether an answer goes beyond the
supplied text. It does not test gaps in the labels themselves (FINDINGS §15).

For an unanswerable field, **the correct answer is nothing**, unless the
supplied text covers the topic anyway. The ground-truth audit
(`shared/contamination.py`, FINDINGS §G) removes 15 of the 48 unanswerable
fields because the supplied text covers their topic anyway, usually under its
own heading. 33 remain.

**Fabrication rate** = the share of those 33 fields that came back with a value
the supplied text does not support.

The scripts also report **recall on the two supported fields**. A sparse-field
fix that works by nulling everything is not a fix, and that number is there to
catch it.

## Result

Recorded run, plain prompt (`broken.py`); every case read in full and recounted
on 29 Sep 2026 (FINDINGS, *Chapter 9 re-read* and *Chapter 3 re-read*):

| measure | result |
|---|---|
| fields filled, of the 33 counted as not covered | 1 of 33 |
| of that 1, a correct reading of the supplied text | 1 of 1 |
| **fabrications** | **0 of 33** |
| fields answered "N/A", of the other 32 | 32 of 32 |
| fields filled, of the 15 the audit removed (all correct values) | 11 of 15 |
| supported fields correctly filled | 23 of 24 |

The filled field, and the case the audit now removes:

- **Furosemide, `drug_interactions`**: cut the dose of other blood-pressure
  drugs by at least 50 percent. The supplied dosing section says "the dosage of
  other agents should be reduced by at least 50 percent when furosemide tablets
  are added to the regimen". The sentence has no heading of its own and matches
  none of the audit's fixed patterns, so the audit could not detect it.
- **Omeprazole, `pediatric_dosage`**: "children under 18 years of age: ask a
  doctor", word for word from the supplied over-the-counter directions. It was
  counted as a second fabrication until the audit gained a rule for this line;
  the audit now removes it.

**The failure did not reproduce.** The figures published earlier (29%, or 14 of 48;
re-samples of 13, 12 and 12 of 48; then 6%, or 2 of 35) counted fields filled, and are
withdrawn as fabrication rates. So is "every fabrication carried a real quote"
(14 of 14, then 2 of 2): the quotes were real because the values were correct.
The failure needs a form that asks for more than the source contains, such as a
visit note written from a conversation. That test, on ACI-Bench's doctor–patient
dialogues with a full note template, ran as Experiment 9.4 (`probe_conversation.py`):
a heading template wrote "No known drug allergies" into 4, 3 and 4 of 58 notes where
allergies never came up.

## Run it

```bash
python broken.py              # every field required, "N/A" offered for anything not stated
python fixed.py               # nullable fields + quote verification + section check in code
python fixed_noncircular.py   # the section check with four sections supplied (Experiment 9.3)
python fix_provenance.py      # the book's embedding check, scored on broken.py's output
```

## What `broken.py` does

The schema declares all six fields as required strings, and the prompt offers
`"N/A"` for anything not stated. The chapter predicts that a model made to write
a string will write a plausible one. On these labels it wrote `"N/A"` on all 33
fields the supplied text did not cover.

It also asks for a `source_quote` on every field, and reports whether each quote
appears in the document.

## What `fixed.py` changes

Four things:

1. **The schema permits null, with no default value.** No `""`, no `"N/A"`.
   Chapter 9: a default value lets a field be filled without evidence, and an
   empty string is indistinguishable from real data downstream. This change was never
   measured on its own.
2. **The prompt says so** — the chapter's sparse-field protocol, including the
   list of filler phrases that are fabrication indicators. The chapter also
   describes a code validator that rejects those phrases; it was never built.
3. **Every source quote is verified against the document** with fuzzy matching
   (RapidFuzz `partial_ratio > 85`, per the book, over the first 80 characters
   of the quote; `shared/scoring.py` falls back to a difflib equivalent if
   RapidFuzz is not installed). A field whose quote is not in the document is
   set to null before storage, whatever the model claimed.
4. **Every quote must come from a section that can support the field.** Not in
   the book as written; added by this repo. Its fabrication result is forced in
   both designs: see below.

`fixed.py` also prints the **null rate per field**, which is the chapter's
monitoring signal. A field that is structurally sparse should show a high null
rate; if that rate starts falling without the input data getting richer, the
model has started filling it. It was never tested as a monitor here. The "0% vs
100%" split between the two scripts compares two schemas: `broken.py` cannot
return null (it writes "N/A"), and the nulls `fixed.py` returns on withheld
fields are forced by the code check.

## What running the fixes found

### `partial_ratio > 85` discards correct quotes when they are long

Chapter 9 gives the verification rule as `rapidfuzz.fuzz.partial_ratio > 85`
and says nothing about quote length. Applied literally, to the whole quote, it
discards correct extractions — and the reason is not obvious from reading it.

`partial_ratio` scores the needle against the best-matching window of the
haystack *of the needle's own length*, so its tolerance for small differences
shrinks as the quote grows. The model returns quotes of 153–1,072 characters that
are near-verbatim with a few words left out. Those score in the 60s and 70s and
get rejected.

Measured on these labels, sweeping how much of the quote is verified:

| verified | plain prompt | Prompt 9-1 |
|---|---|---|
| whole quote — the book's rule | **39%** (9/23) | **48%** (11/23) |
| first 80 chars | **100%** (23/23) | **100%** (23/23) |
| first 150 chars | 83% (19/23) | 87% (20/23) |
| first 200 chars | 61% (14/23) | 65% (15/23) |

Verifying whole quotes discards half or more of the correct extractions, and
nothing in the chapter warns that it will. The effect on fabrication could not
be measured, because no fabrication occurred.

`shared/scoring.py` verifies the first 80 characters by default
(`VERIFY_WINDOW`). The right window depends on the job: reused unchanged in
Chapter 8's placement check, 80 characters produced that chapter's only
"error", and it was a false one.

### The section check: forced to zero, and the map was wrong for these labels

`fixed.py` makes the model name the section its quote came from, and
`SUPPORTING_SECTIONS` in the code says which section can support which field. A
children's dose is accepted only from `pediatric_use`. The mapping is a design
decision the team has to make. The model is never told it.

- **`fixed.py` (Experiment 9.2).** Only two sections are supplied, and neither
  is the permitted section for any of the four withheld fields. The check nulls
  all of them whatever the model writes, so its 0% is arithmetic (FINDINGS §1).
  The model itself returned null on all 33 fields. Recall fell from 23 of 24 to
  22 of 24.
- **`fixed_noncircular.py` (Experiment 9.3).** Four sections are supplied where
  the label has them. The fabrication side is still forced: each field has one
  permitted section, and the six unanswerable fields are exactly those whose
  section is missing from that label, so 0 of 6 is arithmetic. Recall is 32 of
  42 as scored, and at least 33 of 40 answerable fields once the ten losses are
  read.

The one real measurement is a cost. The check rejected **5 correct children's
doses** out of 40 answerable fields (Metformin, Atorvastatin, Albuterol,
Gabapentin, Furosemide), because each quote sits in `dosage_and_administration`.
FDA labels print children's doses there by regulation: 21 CFR 201.57(c)(9)(iv)
says "appropriate pediatric dosage information must be given under the 'Dosage
and Administration' section". The map was wrong for this kind of document.

An earlier version of this README said the model lifts paediatric text from the
wrong section and attaches a real quote to it, so a check that a quote exists
cannot catch it. That is withdrawn: no such case is in the recorded run, and the
filled field in [Result](#result) is a correct reading.

### The embedding check measured nothing

`fix_provenance.py` scores how similar each value is to the document, using
text embeddings, as the book's embedding-provenance fix does. All 12 values it
treats as fabrications are correct: the 11 filled fields among the 15 the audit
removed, and the one in [Result](#result). Its threshold sweep compares correct values with correct
values, and is withdrawn as evidence.

## How "the model declined" is decided

Deterministically, by `is_absent_answer()` in `common.py`. A value counts as a
decline if it is boilerplate filler (`N/A`, `none`, `unknown`, `to be
determined`, ...) or contains an explicit statement of absence (`not specified`,
`does not`, `no information`, ...).

Both lists are deliberately generous: anything ambiguous is scored as a decline,
which can only lower the fabrication count. The ground truth erred the other
way: it counted the correct reading in [Result](#result) as a fabrication, and
Omeprazole's children's line too until the audit gained a rule for it.
The same generosity can also cost recall: in Experiment 9.3 a complete
interaction list for Gabapentin was scored as declined because it contains
"does not". Every unsupported field's value is printed in the per-field table,
so you can audit the calls rather than trust the predicate.

## Corpus

`data/labels.json` — FDA drug labels from the openFDA API (public domain).
Run `python ../fetch_data.py --show` to see which sections each label carries.
The ground truth here is which sections were supplied to the model, as described
in [What this measures](#what-this-measures).
