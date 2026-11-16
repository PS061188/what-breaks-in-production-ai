# Chapter 8 — Routing and placement errors

Three boxes filled from three sections of an FDA label; the question is whether
content lands in the right box. `broken.py` is the plain prompt, `fixed.py` adds
the constrained prompt and a rules engine that locates each quote in the
document, `book_prompt.py` is the chapter's fuller prompt with a confidence grade.
Results and corrections are in `../FINDINGS.md` (§3, §10, and the 24 Sep 2026 entry).

## Probe: the rules engine on planted misplacement

`probe_planted.py` (replay only, no model calls). Swaps quote and value between
two boxes in every recorded output, every pair once: 66 planted misplacements,
33 untouched boxes. As shipped (80-char locator): 65/66 caught, 1/33 false
rejection. At 200 chars: 66/66, 4 false. Whole quote: 66/66, 6 false. Every
rejection named the section the quote really came from.


## Probe: the prompt with the headings removed

`probe_hardcorpus.py` (`--live` to re-record; three draws per prompt). Sections
split into sentences and shuffled; plain vs Prompt 8-1. Real misplacements 0/33
in every run for both prompts; the scorer's flags are the boilerplate artefact
and unfindable joined quotes. Write-up in `../FINDINGS.md`.

## Demonstration: the provenance record

`demo_provenance.py` (no model calls). Plants a merge fault, a generator fault, a
duplicate and a missing record per label and runs the chapter's diagnosis. Holds
by construction; the point is what the quote check alone cannot tell apart.


## Probe: placement by convention (generated shipping documents)

`probe_convention.py` (`--live` to re-record; three draws per prompt, ~$0.60).
48 generated documents, four levels, three prompts. Misplaced 0 at every level
where a label or an order line says which address is which; at the fourth level
(no labels, no line, half the documents recipient-first) both prompts assume
sender-first — plain 12, 12, 12 of 36 a run, Prompt 8-1 12, 15, 11 with null on
4, 2, 5 — and the graded prompt flags every record. An earlier "empty fields"
result was a company-only scorer artefact and is withdrawn. A fourth prompt asks per field whether the document
states the role: "not stated" on all 108 unlabelled fields, and on 29 labelled
ones that were all correct. Write-up in
`../FINDINGS.md`.


## Probe: placement on real clinical notes (Experiment 8.6)

`probe_clinical.py` (`--live` to re-record; four prompts × three draws over 60
ACI-Bench notes, 720 calls, ~$2; `NOTES=2` for a smoke test). Headings removed,
sentences shuffled, the model files each sentence under history / exam / results
/ assessment-and-plan. Misplaced of 2,070: plain 375, 366, 381; with section
definitions 286, 268, 256; with a confidence grade 271, 266, 269; with each
sentence's section tag kept 1, 0, 1. The grade: error rate 10% among HIGH, 39%
MEDIUM, 63% LOW, but 560 of 806 misplaced sentences graded HIGH. Corpus and
division rule documented in the script's docstring and `../data/aci_bench_notes.json`.
Write-up in `../FINDINGS.md`.


## Probe: what the schema guarantees (Experiment 8.7)

`probe_schema.py` (`--live missing`; ~$0.40). Plain prompt over the 60 notes, one
draw: no schema / schema / schema + Pydantic validator with re-ask. The model
invented no keys and no IDs in any condition; the schema dropped more sentences
(33) than the free call (8); the validator loop removed every duplicate and
omission with 13 re-asks; misplacement was the same in all three. Write-up in
`../FINDINGS.md`.

`probe_instructor.py` runs the Instructor library itself (1.17.0, its own
environment; setup at the top of the script) with the same validator on the
first ten notes, Claude Haiku 4.5 with thinking off. 9 of
10 ended valid after 16 calls. The tenth wrote each sentence's text after its ID
in all three replies; the validator's error never said that only the IDs were
wanted. Replays from `fixtures_instructor/` with no key.
