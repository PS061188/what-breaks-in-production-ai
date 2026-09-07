# Chapter 6 — State mismatch failures

> The model answered correctly. The thing it read had stopped being true.

## What this measures

Chapter 6 lives in the integration layer, so none of its four fixes is a prompt
change and one of them cannot be tested with an API call at all. Each is
measured separately, and the headline pair — `broken.py` / `fixed.py` — is the
one nobody had tested: **conversation history truncation**.

| script | the book's fix | what it measures |
|---|---|---|
| `broken.py` / `fixed.py` | 3 — history management with semantic boundary detection | naive character cut vs boundary-aware cut, at the same budget |
| `fix_freshness.py` | 1 — metadata-filtered retrieval with freshness scoring | the book's filter as literally written, freshness ranking, and a filter whose flag is stale |
| `fix_monitoring.py` | 2 — retrieval freshness monitoring | 398 weekly runs, alert at 70% top-k overlap. No model calls |
| `fix_prompt.py` | the chapter's prompt template | the staleness protocol vs a neutral prompt, on honestly-labelled stale documents |
| — | 4 — session isolation at the infrastructure layer | **not implemented as written.** See below |

```bash
python broken.py         # naive truncation
python fixed.py          # boundary-aware truncation
python fix_freshness.py
python fix_monitoring.py # no API key needed, no fixtures, ~3s
python fix_prompt.py
```

All of it replays from `fixtures/` for free. `--live` re-records.

## How ground truth is derived

Nothing here is annotated and no model decides whether an answer is right.

**Every dose value in the corpus is found by one regex.** `DOSE` in `common.py`
matches `500 mg`, `1.6 mcg/kg/day`, `15 mL`. From that one function everything
else is set arithmetic:

* the values a truncated context contains,
* the values truncation removed,
* the values an answer asserted,
* and therefore **the values an answer asserted that were not in front of it**.

**The cut points come from the documents.** An FDA dosing section is a sequence
of headed subsections — `2.3 Dosage Adjustment in Patients with Renal
Impairment`, `Pediatric Patients:`, `Major Depressive Disorder –`. Those
headings are in the labels as filed. `common.headings()` finds them, and the
budgets are computed from them:

| regime | where the budget lands | correct answer |
|---|---|---|
| **MIDFACT** | inside the sentence stating a dose, on the digit | no dose — the value is provably absent |
| **NEAR** | between a heading and its first word of content | no dose — the subsection is absent |
| **CONTROL** | 200 characters into the *next* subsection | the dose — it is complete under both policies |

A subsection is only used when it states at least one dose value that appears
nowhere earlier in the section. Metformin and Atorvastatin are excluded by that
rule, because their labels repeat every dose in the highlights block at the top:
a model answering with one of those values would be reading, not fabricating,
and the case would prove nothing.

**The question is derived too.** It is built from the subsection's own heading
(`common.question()`), so it is identical in both scripts and nobody wrote it.

18 subsections across 6 drugs; 39 mid-fact cut points; 75 calls per script.

## Fix 3 — history truncation. What happened

Both scripts share `run()` and `report()` in `common.py`. They differ by one
argument: `naive_cut` or `boundary_cut`.

```
naive_cut(text, 262)     -> "... Adults: The usual initial dose of furosemide tablets is 20 to "
boundary_cut(text, 262)  -> "... to determine the minimal dose needed to maintain that response."
```

| metric | naive cut | boundary cut |
|---|---|---|
| MIDFACT: asserted a dose not in the excerpt | **10%** (4/39) | **0%** (0/39) |
| MIDFACT: declined to give a dose | 36% (14/39) | 41% (16/39) |
| NEAR: asserted a dose not in the excerpt | 0% (0/18) | 0% (0/18) |
| CONTROL: recall where the answer is complete | 78% (14/18) | 78% (14/18) |
| characters discarded, mean per call | 0 | 123 |

**Read the sample size before the numbers.** Four failures out of 39 against
zero out of 39 is Fisher p = 0.12. The mechanism is visible in the transcripts;
the rate is not established, and one more run at default temperature could
plausibly return three or five.

### The failure has a specific shape: severed ranges and severed tables

All four failures are the same thing. The cut landed inside a numeric range or
inside a table row, and the fragment left behind reads like a finished fact.

| excerpt ends | truth | answer |
|---|---|---|
| `...the usual initial dose of furosemide tablets is 20 to ` | 20 **to 80** mg | "The usual initial dose … is **20 mg**" |
| `...Titrate dosage by 12.5 to ` | 12.5 **to 25** mcg | "**12.5 mcg**" |
| `...creatinine clearance <` (inside Gabapentin's renal table) | 15 mL/min | a **reconstructed renal dosing table** — seven values, none in the excerpt |
| `...a creatinine clearance of ` (the same table, 114 chars later) | 7.5 mL/min | the table again, seven values |

The Furosemide answer even says *"the excerpt is incomplete"* in the same
sentence as the wrong dose. Flagging the truncation and completing it anyway are
not mutually exclusive.

### Null result: cutting at a heading produced nothing at all

The NEAR regime — where the excerpt ends on a dangling heading with no content
under it — produced **zero** unsupported answers in either arm, out of 36 calls.
Haiku recognises that shape and says so: *"the section begins with 'Dosage in
Adult Patients' but the text is incomplete and does not state a specific dose."*

That is worth stating plainly because it narrows the fix. A truncation that ends
on a structural marker is self-announcing. A truncation that ends mid-clause is
not, and mid-clause is where the whole risk sits.

### One answer declined in the schema and fabricated in the prose

3% (1/39) of naive-cut answers returned `dose: null` — the field a code check
would read — while the free-text `answer` laid out a renal dosing table with
seven values that are not in the excerpt. A validator inspecting the structured
field passes it. Chapter 9's fix would pass it. The text the user reads is the
fabrication.

### The counter-metric

Boundary-aware truncation throws away up to a full sentence more context — 123
characters per call here. CONTROL recall is **78% in both arms**, so on this
corpus it cost nothing. It is not free in principle: on two of eighteen control
cases the naive cut retained a dose value from the next subsection that the
boundary cut discarded.

## Fix 1 — metadata filtering and freshness scoring

Chapter 3's `fix_retrieval.py` already measured `status == "ACTIVE"` on this
corpus (83% of unfiltered retrievals were superseded, every answer changed).
`fix_freshness.py` measures the three things it did not.

| what | result |
|---|---|
| **The book's filter as written**, `status == ACTIVE AND last_verified > now() - 90d`, returns **nothing** | **33%** (2/6 drugs) |
| Of those, answers that stated a dose anyway | 0% (0/2) |
| Freshness scoring (rank the hits by recency, take the newest) picks a different document from the hard filter | **50%** (3/6) |
| A correct-looking `status` filter over an index last ingested 7 months ago serves a superseded label | **100%** (6/6) |
| Answers that changed when that stale index was used | **100%** (6/6) |
| Oldest label the stale index served | 579 days |

Three findings, in descending order of how much the book needs them.

**The 90-day clause can empty your result set, silently.** `status == ACTIVE`
and `last_verified > now() - 90d` are joined by AND, and a document can be the
newest label in existence and still be more than 90 days old. Furosemide's
current label is 226 days old; Sertraline's is 215. Both drugs return zero
documents. There is no exception, no error, no empty-result branch — the prompt
is built from an empty string and the model answers. It answered safely here (it
said it had nothing, 0/2 fabricated), so the production symptom is a silent
denial of service on a third of queries rather than a wrong answer. Nobody is
paged for either.

**Freshness scoring is not a substitute for the filter.** Ranking the top-k by
recency picks a different document from the hard filter on half the drugs — not
because the ranking is wrong but because *the ACTIVE document is not in the
top-k to be ranked*. A re-rank cannot recover a document similarity search never
returned. Soft ranking is attractive because it does not depend on the status
flag being right; it is weaker for exactly the reason the chapter's filter is
strong, which is that a `where` clause runs before the ranking.

**The filter can be right and stale.** An index whose last ingest was seven
months ago serves a superseded label for every drug in the corpus, with a
`status` field that says ACTIVE, because it did say ACTIVE when it was written.
Every answer changes. This is Chapter 6's own failure appearing inside Chapter
6's fix, and it is the reason the fix is an *ingest* discipline rather than a
query-time one.

## Fix 2 — retrieval freshness monitoring

The book: *"Run canonical queries weekly, record top-k document IDs, alert when
overlap with the previous week drops below 70%."* Run for real — 398 weeks × 6
drugs, real filing dates, no model calls.

| metric | result |
|---|---|
| Weeks a new current label arrived **and the monitor alerted** | **50%** (20/40) |
| Weeks nothing changed and the monitor alerted anyway | **0%** (0/1381) |
| Weeks with no alert | 99% (1401/1421) |

**The monitor detects retrieval churn, not staleness.** Half the time a new
current label was filed, the top-3 overlap stayed at **100%** and the monitor
said nothing — because the new document did not rank into the top 3. It is in
the index. `status == "ACTIVE"` will hand it to the model. The monitor cannot
see it, because top-k overlap only moves when the *ranking* moves.

Those two failure modes are not the same event, and the book's wording — *"a
drop signals that fresh documents are not being ingested"* — claims the monitor
covers the second when it only covers the first. Zero false alarms is the good
half of the news: the threshold is not noisy, it is just blind to half of what
it was bought for.

A monitor with the same shape that would work: record the **maximum
`last_verified` in the index per canonical query**, and alert when it stops
advancing. That is a one-line change to the same weekly job and it does not
depend on ranking at all. Untested here.

## The chapter's prompt template

`fix_prompt.py` runs the staleness protocol as printed against unfiltered
retrieval with honest metadata headers, and compares it with a neutral prompt.
Same retrieval, same headers, same schema.

| metric | neutral | staleness protocol |
|---|---|---|
| Declared a SUPERSEDED document usable | 83% (5/6) | **33%** (2/6) |
| Answered with a dose only a superseded label states | 67% (4/6) | **33%** (2/6) |
| Refused every document | 0/6 | 2/6 |

The prompt roughly halves both numbers, which supports the book's framing of it
as a real second line of defence. Two limits, both measured:

* **An ACTIVE document was in the top-3 at all for only 50% of drugs.** No
  prompt can rescue a retrieval that never returned the current document. That
  is the ceiling on this fix, and it is why the chapter is right to call the
  filter primary.
* **It still used stale content on 2 of 6 drugs.** On Prednisone, with no ACTIVE
  document in the top-3, it declared one SUPERSEDED document usable anyway and
  answered from it — having been told in the system prompt not to.

The 90-day rule in the prompt has the same defect as the 90-day clause in the
filter: applied literally it disqualifies current labels. Two of six answers
refused everything.

## Fix 4 — session isolation. Not implemented as written

The book: *"a separate database per customer, and credentials that reach only
that customer's data. Then a forgotten check returns an error instead of the
other hospital's conversation."*

**This is not testable with an API call and nothing here pretends otherwise.**
The claim is that a credential boundary fails closed where an application-level
filter fails open. Demonstrating it requires two provisioned tenants with
separate credentials and a deliberately omitted filter — infrastructure, not
model behaviour. A mock would only prove that the mock was written correctly.

The claim is also not in dispute, which is the honest reason not to spend a
fixture on it: a query that cannot reach another tenant's rows cannot return
them. What is worth flagging is that the chapter's second sentence on this fix
*is* implementable and is the part teams skip — *"log the session ID and the
context-window hash on every model call."* `shared/llm.py` hashes the full
request (system + user + schema + model) to address its fixtures. That hash is
exactly the artefact the chapter asks for, and it is the reason every number in
this repo can be traced to the bytes that produced it. If you want the chapter's
fix in your own pipeline, that half costs one column.

## A bug in this chapter's own code, and how it surfaced

The fixtures for `fix_freshness.py` stopped replaying after a change that could
not possibly have affected them: moving the Chroma index directory.

Chapter 3 hit half of this and fixed half of it — two queries over the same
index can return the same top-k in a different **order**, so it sorts documents
by id before building the prompt. That is not the whole problem. Rebuilding the
index also changed the top-3 **membership** for one drug in six. The label
versions are filed by different repackagers and many are near-identical text, so
several documents sit at effectively the same distance and an approximate index
breaks the tie however it likes.

The symptom was `FixtureMissing` on a replay, which is a good symptom — a
content-addressed cache is an equality check on the prompt, so it fails loudly
when retrieval quietly changes. Without it the run would have produced slightly
different numbers and said nothing.

`common.stable_top_k()` fixes it: over-fetch past the size of the filtered set
so the candidate list is complete, then sort on `(distance, id)`. Both are the
caller's job. The vector store promises neither, and a freshness monitor built
on top-k identity — which is exactly what Fix 2 is — will alert on churn that
never happened if you skip it.

## What the book needs

1. **Fix 1: drop the `AND last_verified > now() - 90d` clause, or make it a
   warning rather than a filter.** As a conjunction it removes current documents
   and empties the result set — 2 of 6 drugs here — with no error. The rule the
   evidence supports is `status == "ACTIVE"`, plus *surfacing* the age of what
   was returned. Chapter 3's version of this fix does not carry the second
   clause; the two chapters should agree.

2. **Fix 2: say what top-k overlap actually detects.** It detects ranking churn.
   It missed 50% of the weeks a new current label arrived, because a new
   document that does not enter the top-k moves no overlap. The sentence *"a
   drop signals that fresh documents are not being ingested"* is not supported.
   Recommend tracking the maximum `last_verified` per canonical query alongside
   it.

3. **Fix 3: narrow the claim to mid-clause cuts.** Boundary-aware truncation did
   nothing on cuts that land at a structural marker — 0% either way — because
   the model recognises a dangling heading and says the text is incomplete. All
   four measured failures were cuts inside a numeric range or a table row. That
   is a sharper and more defensible version of the same advice: the risk is not
   truncation, it is truncation that leaves a fragment reading as complete.

4. **Add the stale-flag case to the chapter.** The chapter tells you to write
   `status` at index time and filter on it, and never says the flag is itself a
   snapshot with an age. On this corpus an index seven months out of date served
   a superseded label for 100% of drugs with a filter that passed. The
   chapter's own thesis applies to its own fix and the text does not close that
   loop.

5. **The prompt's 90-day rule inherits the filter's defect.** Two of six answers
   refused every document because the current label is more than 90 days old.
   Same correction as (1).

## Honest limits

- **One model, one run, default temperature.** Nothing here is pinned to
  temperature 0 — `shared/llm.py` does not expose it, and the same script run
  twice returns slightly different counts. The Fix 3 result in particular
  (4/39 vs 0/39) is a mechanism demonstration, not an established rate.
- **Six drugs.** The version corpus has six; the truncation corpus has six of
  the twelve labels. Prednisone, Lisinopril and Omeprazole have no detectable
  subsection headings — their dosing sections are continuous prose. Metformin
  and Atorvastatin repeat every dose value in the highlights block at the top,
  so nothing under a heading is novel. Albuterol states no dose values under a
  heading at all; it is measured in inhalations.
- **A dosing section is not a conversation.** Fix 3 tests the truncation
  mechanic — a long prior context cut to a budget — on documents. It does not
  test topic-shift detection across turns, intent changes, or the summarise-old,
  keep-recent strategy that `ConversationSummaryBufferMemory` and `mem0`
  implement. Those need a conversation corpus this repo does not have.
- **`now()` is frozen** at the corpus's retrieval date (2026-08-22) so replays
  a year from now report the recorded numbers. Re-fetch the corpus and the
  freshness results move.

## Corpus

`data/label_versions.json` — 48 real FDA labels, 6 drugs, filed by different
repackagers across seven years, each with its real `effective_time`. Newest per
drug is ACTIVE; the rest are genuine superseded versions. Rebuild with
`python ../fetch_data.py --versions`.

`data/labels.json` — 12 labels with named sections; the dosing sections are what
Fix 3 truncates.
