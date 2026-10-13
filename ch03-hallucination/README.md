# Chapter 3 — Hallucinations and confident fabrication

> The most dangerous hallucinations in production are not the dramatic ones.
> They are the plausible ones.

## What this measures

Six questions about a drug, all of which sound equally answerable. The model is
given only two sections of the label: **indications and usage**, and **dosage
and administration**. Two of the six questions can be answered from those
sections. Four cannot — they need the adverse reactions, pediatric use,
pregnancy, or drug interactions section, and those were not supplied.

Whether a question is answerable is therefore decided by the documents rather
than by a label somebody wrote, with one correction. The ground-truth audit
(`shared/contamination.py`, FINDINGS §G) removes 16 of the 48 unanswerable
questions, because the supplied text covers their topic anyway: Levothyroxine's
dosing section, for example, carries a paediatric dosing table under its own
heading. 32 remain.

**Fabrication rate** = the share of those 32 questions the model answered
anyway.

## Run it

```bash
python broken.py                  # the three baseline prompts, replayed from fixtures, free
python fixed.py                   # grounded prompt + citation enforcement
python fix_similarity.py          # engineering fix 2: similarity check, runs locally
python fix_judge.py               # engineering fix 3: a second model as judge
python fix_retrieval.py           # engineering fix 4: version-locked retrieval
python probe_selfconsistency.py   # five draws per question (Experiment 3.4)
python probe_logprobs.py          # token log-probabilities, GPT-4.1-mini (Experiment 3.5)
```

Add `--live` to re-run against the API. `--model claude-opus-5` to see whether
the failure still reproduces on a stronger model.

## The three baselines, and why there are three

`broken.py` runs the same questions through three prompts. Fabricated, of the 32
unanswerable questions, in the recorded run recounted on 29 Sep 2026:

| prompt | what it says | fabricated |
|---|---|---|
| `neutral` | Supplies the source, says to use it, says nothing about what to do when the source does not cover the question. | 1 of 32 |
| `soft-words` | The soft vocabulary — "be helpful and complete", "the relevant clinical guidance" — with no permission to leave the source. | 2 of 32 |
| `soft-inference` | The same, plus "drawing on standard pharmacology where the excerpt is thin". | 29 of 32 |

The second is the language Chapter 3 warns about. It is not a strawman — it is
where a prompt lands after one round of *the assistant is being unhelpful*
feedback from users.

Running all three is the finding. On a current model the neutral prompt
declines on its own, the soft words alone add one fabrication, and the permission
clause produces the failure. The gap between the last two rows, 27 questions of
32, is the chapter's argument stated as a number.

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
model; the citation check does not. On these labels, though, the check rejected
0 of 72 answers on every model: the prompt did all the work. It fabricated on 0 of
32 questions on Claude Haiku 4.5, Claude Opus 5, GPT-5-mini and GPT-4.1-mini,
against 29, 32, 32 and 30 of 32 with the `soft-inference` prompt.

`fixed.py` also reports **recall on the two answerable questions**. A grounding
fix that stops answering answerable questions has not improved anything, and
that number is there to catch it. Of the 24 answerable questions it answered 21,
22, 23 and 24 on the same four models.

## The other fixes and probes, recounted on 29 Sep 2026

- **Similarity check** (`fix_similarity.py`). The cross-encoder at 0.3 caught all
  29 answers that asserted something on an unanswerable question, with 3 false
  alarms among the 24 answerable ones; from 0.4 up it gives 5.
- **A second model as judge** (`fix_judge.py`). In the one run whose answers were
  kept, it caught 29 of 29, with 6 false alarms of 24. Over four runs the false
  alarms were 4, 5, 4 and 6 of 24.
- **Five draws per question** (`probe_selfconsistency.py`). Of 32 unanswerable
  questions, 30 declined on every draw, 2 split, and none fabricated on every
  draw. A fabrication repeated on every draw would not be flagged this way; that
  holds by design, but it was not observed here.
- **Token log-probabilities** (`probe_logprobs.py`, GPT-4.1-mini). In runs 3 and
  4, a cut at −0.20 and −0.18 caught 11 of 11 and 7 of 7 fabrications and flagged
  3 of 24 correct answers each time, but also 16 of 21 and 17 of 25 correct
  refusals.

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
The ground truth here is which sections were supplied to the model, as described
in [What this measures](#what-this-measures).
