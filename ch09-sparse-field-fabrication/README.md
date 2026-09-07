# Chapter 9 — Sparse field fabrication

> A blank the system will not accept is a blank the model will fill.

## What this measures

Six fields are requested from every drug label. The model is given two sections
— indications and usage, dosage and administration — so two of the six fields
have source content and four do not. Nothing about that is arranged: the
pediatric-use section is genuinely missing from Prednisone's label, the
pregnancy section from Sertraline's. Real documents, real gaps.

For the four unsupported fields, **the correct answer is nothing**.

**Fabrication rate** = the share of unsupported fields that came back with a
value anyway.

The scripts also report **recall on the two supported fields**. A sparse-field
fix that works by nulling everything is not a fix, and that number is there to
catch it.

## Run it

```bash
python broken.py     # every field required, "N/A" offered as the escape hatch
python fixed.py      # nullable fields + quote verification in code
```

## What `broken.py` does wrong

The schema declares all six fields as required strings. The prompt offers
`"N/A"` for anything not stated, which *sounds* like a licensed empty state and
is not one — the model still has to produce a string, and a plausible string
beats `"N/A"` by every instinct it has.

It also asks for a `source_quote` on every field, and the run shows what that
buys: asking for a quote does not produce a quote. It produces a quote-shaped
string. `broken.py` reports how many fabrications arrived with a quote that
does not appear anywhere in the document.

## What `fixed.py` changes

Four things:

1. **The schema permits null, with no default value.** No `""`, no `"N/A"`.
   Chapter 9: a default is an escape hatch for fabrication, and an empty string
   is indistinguishable from real data downstream.
2. **The prompt says so** — the chapter's sparse-field protocol, including the
   list of filler phrases that are fabrication indicators.
3. **Every source quote is verified against the document** with fuzzy matching
   (RapidFuzz `partial_ratio > 85`, per the book; `shared/scoring.py` falls back
   to a difflib equivalent if RapidFuzz is not installed). A field whose quote
   is not in the document is set to null before storage, whatever the model
   claimed.
4. **Every quote must come from a section that can support the field.** Not in
   the book as written; added because check 3 turned out not to be enough. See
   below.

`fixed.py` also prints the **null rate per field**, which is the chapter's
monitoring signal. A field that is structurally sparse should show a high null
rate; if that rate starts falling without the input data getting richer, the
model has started filling it.

## Two corrections to the book's fix, both found by running it

### `partial_ratio > 85` does not work on long quotes

Chapter 9 gives the verification rule as `rapidfuzz.fuzz.partial_ratio > 85`
and says nothing about quote length. Applied literally, to the whole quote, it
does not work — and the reason is not obvious from reading it.

`partial_ratio` scores the needle against the best-matching window of the
haystack *of the needle's own length*, so its tolerance for small differences
shrinks as the quote grows. The model returns quotes of 240–720 characters that
are near-verbatim with a few words elided. Those score in the 60s and 70s and
get rejected.

Measured on this corpus, sweeping how much of the quote is verified:

| verified | recall (fields with source) | fabrication (fields without) |
|---|---|---|
| whole quote — the book's rule | **54%** | 14% |
| first 80 chars | **95%** | 22% |
| first 150 chars | 83% | 22% |
| first 200 chars | 66% | 18% |

Verifying whole quotes buys 8 points of fabrication for 42 points of recall.
That is not a trade most pipelines should take, and nothing in the chapter warns
you that you are making it.

`shared/scoring.py` verifies the first 80 characters by default
(`VERIFY_WINDOW`). An invented quote does not match on its opening either, so
the check still does its job.

### A quote can be real and still not support the field

With the window fixed, the quote check stopped rejecting anything at all — and
the fabrication rate barely moved. Reading the rows explains why.

Asked for `pediatric_dosage` on a label with no pediatric section, the model
returns pediatric text lifted out of the **indications** section — *"Acute
leukemia of childhood..."* — and attaches a quote that is genuinely in the
document. Quote-existence verification passes it, because the quote is real.

That is Chapter 3's source-tracking failure appearing inside Chapter 9's fix:
content that exists somewhere in the context gets attributed to the wrong
source. The chapter's own prevention table distinguishes *"does this content
point at a passage?"* from *"is the content actually supported by that
passage?"* — and the code fix in the chapter only implements the first.

`fixed.py` adds the second: the model must name the section its quote came
from, and `SUPPORTING_SECTIONS` in the code says which sections can support
which field. A pediatric dose sourced from the indications section is nulled,
whatever the quote says.

The mapping is a design decision the team has to make. The model is never told
it.

## How "the model declined" is decided

Deterministically, by `is_absent_answer()` in `common.py`. A value counts as a
decline if it is boilerplate filler (`N/A`, `none`, `unknown`, `to be
determined`, ...) or contains an explicit statement of absence (`not specified`,
`does not`, `no information`, ...).

Both lists are in `common.py` and both are deliberately generous: anything
ambiguous is scored in the model's favour, so **the fabrication rate reported
is a floor, not a ceiling**. Every unsupported field's value is printed in the
per-field table, so you can audit the calls rather than trust the predicate.

## Corpus

`data/labels.json` — FDA drug labels from the openFDA API (public domain).
Run `python ../fetch_data.py --show` to see which sections each label is
missing; those gaps are the ground truth.
