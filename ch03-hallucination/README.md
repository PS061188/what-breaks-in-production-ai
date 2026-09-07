# Chapter 3 — Hallucinations and confident fabrication

> The most dangerous hallucinations in production are not the dramatic ones.
> They are the plausible ones.

## What this measures

Six questions about a drug, all of which sound equally answerable. The model is
given only two sections of the label: **indications and usage**, and **dosage
and administration**. Two of the six questions can be answered from those
sections. Four cannot — they need the adverse reactions, pediatric use,
pregnancy, or drug interactions section, and those were not supplied.

Whether a question is answerable is therefore a property of the corpus, not a
label somebody wrote. The section is either in the context or it is not.

**Fabrication rate** = the share of unanswerable questions the model answered
anyway.

## Run it

```bash
python broken.py     # both baseline prompts, replayed from fixtures, free
python fixed.py      # grounded prompt + citation enforcement
```

Add `--live` to re-run against the API. `--model claude-opus-5` to see whether
the failure still reproduces on a stronger model.

## The two baselines, and why there are two

`broken.py` runs the same questions through two prompts:

| prompt | what it says |
|---|---|
| `neutral` | Supplies the source, says to use it, says nothing about what to do when the source does not cover the question. |
| `soft-inference` | The same, plus "be helpful and complete", "the relevant clinical guidance", "drawing on standard pharmacology where the excerpt is thin". |

The second is the language Chapter 3 warns about. It is not a strawman — it is
where a prompt lands after one round of *the assistant is being unhelpful*
feedback from users.

Running both is the finding. On a current model the neutral prompt often
declines on its own, and it is the soft-inference wording that produces the
failure. The gap between the two rows is the chapter's argument, stated as a
number.

Read the answers, not only the rate. The characteristic shape is a caveat
followed by an assertion — *"the excerpt does not cover this, however..."* —
and the caveat is exactly what lets it through review.

## What `fixed.py` changes

Two things, and they are different kinds of thing.

1. **The prompt** (the chapter's grounding template): cite every claim, and
   `answerable: false` is a correct outcome.
2. **The code after the call**, which does not ask the model's permission:
   - an answer with no citations is rejected;
   - every citation quote is checked against the source with fuzzy matching,
     and an answer whose quotes are all unfindable is rejected.

The second half is the durable one. The prompt's contribution moves with the
model; the citation check does not.

`fixed.py` also reports **recall on the two answerable questions**. A grounding
fix that stops answering answerable questions has not improved anything, and
that number is there to catch it.

## The judge, and its limits

`broken.py` returns free text, so something has to decide whether the model
answered or declined. `common.py` uses a second model call with a two-value
enum for that.

It is a classifier, not a verifier. It never rules on whether an answer is
true, only on whether an assertion was made — which is the thing being counted.
Every judgement is written to `fixtures/` so you can read them and disagree.

`fixed.py` needs no judge: `answerable` is a field in the schema and the
citation check is code.

## Where this differs from the book

The book's engineering fix for this chapter is written with
`instructor` + `pydantic` + `openai`, against `gpt-4`. This repo uses the
Anthropic SDK's native structured outputs, which enforces the same contract —
a validated schema with a citations array and an `unverified_claims` field —
without the extra library.

The mechanism the chapter argues for is the schema and the code check around
it, not the specific library. If you are reproducing this on OpenAI, the
`instructor` snippet in the book is the equivalent.

## Corpus

`data/labels.json` — FDA drug labels from the openFDA API (public domain).
Real documents, real sections, real gaps.
