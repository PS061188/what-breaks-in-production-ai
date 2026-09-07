# Chapter 5 — Extraction and normalisation quality loss

> Nothing was fabricated. Nothing was dropped. The content is less specific
> than the source.

## What this measures

The source is the DOSAGE AND ADMINISTRATION section of a real FDA label. That
text is written to be precise: ranges rather than points ("5 mg to 60 mg"),
conditions on when to adjust, words that narrow a dose — *initial*,
*maintenance*, *individualized*, *gradually*, *not to exceed*.

Both scripts ask for the same four fields and return the same JSON schema. The
only differences are the prompt and what runs after the call.

Three deterministic checks, all ordinary string matching against the source:

| metric | what it asks |
|---|---|
| **Values still findable in the source** | Is the stored value something you can locate in the document, or did the model rewrite it on the way out? |
| **Qualifier retention** | Of the narrowing words present in this document, how many survive into the stored value? |
| **Dose ranges preserved** | The source says 5 mg to 60 mg. Does the output still contain a range, or a point? |

The qualifier vocabulary is in `common.py`. It was built by grepping the corpus
for the hedges that are actually there, not by guessing, and only terms found
in a given source count towards that source's score.

**The checks deliberately ignore `source_quote`.** Both scripts must return
one, and a long enough quote would let an output score well on specificity it
never actually captured. The stored value is the thing under test.

## Run it

```bash
python broken.py     # one prompt that extracts and normalises
python fixed.py      # capture verbatim, then normalise in code
python normalise.py  # the normaliser's own unit tests
```

## What `fixed.py` changes

1. **The prompt stops normalising.** Capture the value as written, capture the
   qualifiers attached to it, copy a source quote character-for-character.
   *"Converting, standardising or tidying a value is a failure mode."*
2. **`normalise.py` does the conversion**, in code you can read and test. It
   holds two rules from the chapter:
   - the raw text is stored next to the derived value, so a bad mapping is
     re-derivable without going back to the source document;
   - when the target shape cannot hold something, the mapping *records that it
     discarded it*.

That discard log is the output worth looking at. In `broken.py` the same losses
happen inside the model call, where nothing records them. In `fixed.py` they
are rows you can query — which is the difference between a lossy mapping you
find in a month and one you find in two years.

## The bug in normalise.py, left in the git history on purpose

The first version of the frequency parser reported every *twice daily* dose as
*once daily*, because `\bdaily\b` matched before the twice-daily pattern did.
The unit test at the bottom of `normalise.py` caught it in seconds.

That is the whole argument for moving normalisation out of the prompt. The same
bug inside a prompt produces the same wrong answer, and there is no test you
can run against it.

## What this does not test

The chapter's other half — **normalisation stripping**, where a mapping table
discards a qualifier the target schema cannot hold (`Type 1 diabetes,
well-controlled` → `E10.9`) — needs a coding table this corpus does not have.
The discard log demonstrates the logging behaviour; it does not demonstrate a
lossy ICD-10 mapping row.

## Corpus

`data/labels.json` — FDA drug labels from the openFDA API (public domain).
Dosing text is truncated to 3,500 characters per drug so every document in the
experiment is the same size.
