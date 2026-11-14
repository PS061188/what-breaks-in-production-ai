# Experiment 10.5 — case log

Every candidate omission, every exclusion, and every near-miss, with quotes.
A scorer's count is a claim until the cases are read; these were read.

Corpus: 60 ACI-Bench dialogues (`code/data/aci_bench_dialogues.json`) x 6 notes each
(Claude Haiku 4.5, template / permission prompts, runs s1–s3; Experiment 9.4 recordings in
`code/ch09-sparse-field-fabrication/fixtures_conversation/`). Fact type: medication dose
amounts (number + mass/unit word: mg, mcg, g, units).

Denominator: 74 kept dose mentions (45 digit-form, 29 word-form) across 39 of 60 dialogues
= 64 unique (dialogue, amount+unit) pairs = 66 (drug, dose) facts after splitting the two
amounts shared by two drugs (D2N103 4 mg: Coumadin + Lasix; D2N023 5 mg: finasteride + Cialis).

## Result table (identical in all six cells)

| condition  | run | doses checked | candidates | true omissions | retracted dose omitted | attach checks | attach failures |
|------------|-----|---------------|------------|----------------|------------------------|---------------|-----------------|
| template   | s1  | 64            | 1          | 0              | 1                      | 66            | 1               |
| template   | s2  | 64            | 1          | 0              | 1                      | 66            | 1               |
| template   | s3  | 64            | 1          | 0              | 1                      | 66            | 1               |
| permission | s1  | 64            | 1          | 0              | 1                      | 66            | 1               |
| permission | s2  | 64            | 1          | 0              | 1                      | 66            | 1               |
| permission | s3  | 64            | 1          | 0              | 1                      | 66            | 1               |

True omissions: **0 of 64 doses in every cell**; notes with >=1 true omission: **0 of 234**
(39 dialogues with >=1 stated dose x 6 notes). Present-in-another-form: 0 needed.
Parser errors surviving to the final count: 0. The one candidate everywhere is the
retracted "5000 units" (section 1). Scripts: `count_doses.py` (extractor),
`match_notes.py` (presence + candidates), `attach_check.py` (dose-near-its-drug);
outputs in `doses_out.txt`, `candidates_out.txt`, `attach_out.txt`; first-pass raw scan
in `scan_raw.py` / `scan_raw_out.txt`.

---

## 1. The only candidate omission: D2N027, «5000 units» — RETRACTED IN CONVERSATION, not an omission

Missing from all 6 of its notes (template s1–s3, permission s1–s3). The only candidate
the spec-level matcher produced across all 360 notes.

Dialogue (train D2N027):

> "[doctor] okay . so , you're currently taking vitamin d3 , around **5000 units** on sundays ,
> and two thous ... or **50,000 units** on sundays , **excuse me** , and **2000s** on the other
> six days , and then clindamycin prior to dental procedures , correct ?
> [patient] yeah , that's right ."

The doctor misspeaks (5000), then corrects himself in the same sentence ("excuse me"):
the regimen is 50,000 units on Sundays and 2,000 units the other six days. The patient
confirms the corrected version.

What the six notes wrote (MEDICATIONS section, all six):

- template s1: "Vitamin D3: 50,000 units on Sundays; 2,000 units on other six days"
- template s2: "Vitamin D3 50,000 units on Sundays and 2,000 units on other days of the week."
- template s3: "Vitamin D3: 50,000 units on Sundays, 2,000 units on other six days."
- permission s1: "Vitamin D3 50,000 units on Sundays and 2,000 units on other six days."
- permission s2: "Vitamin D3 50,000 units on Sundays; 2,000 units on the other six days of the week."
- permission s3: "Vitamin D3: 50,000 units on Sundays and 2,000 units on the other six days."

**Verdict: category (d), dose retracted in the conversation.** Omitting the misspoken
5000 is correct scribing, in all six notes. Note also that all six resolved the elided
unit in "2000s" to "2,000 units" — a dose my extractor could not even count (no unit word).

Gap signal: none of the six notes flags anything about 5000 units — correctly, because
the conversation itself withdrew it. There is no gap to signal.

## 2. True omissions: NONE (0 of 64 doses, in every condition and every run)

All other 63 unique doses appear, with the right amount and unit, in all 6 notes of their
encounter. 0 of 234 notes (39 dialogues with >=1 stated dose x 6) carry a true omission.

## 3. Attachment check (stricter than the task's definition of "present")

"Amount+unit anywhere in the note" would hide a dose that survived attached to the wrong
drug. So every one of the 66 (drug, dose) facts was additionally required to have an
occurrence of its amount+unit within 80 characters after its drug's name (or 45 before),
with brand/generic synonyms (protonix|pantoprazole, lasix|furosemide, prozac|fluoxetine,
mobic|meloxicam, pepcid|famotidine, ...). 396 checks (66 x 6 notes): **390 passed; the
only 6 failures are the retracted 5000 units above.** Spot-reads confirm clean lines, e.g.:

- D2N103 (Coumadin and Lasix share 4 mg): "Coumadin 4 mg daily / Lasix 4 mg daily /
  Atenolol 50 mg daily" — each amount on its own drug, in all 6 notes.
- D2N062: "Protonix 40 mg once daily in the morning and Carafate 1 gram four times daily".
- D2N007 (dose increase): "Increase Prozac from 20mg to 40mg daily" — the superseded
  20 mg is carried too, correctly framed as the old dose; "Aspirin 81mg daily".

Limit: proximity is not full semantic verification — frequency/route errors or a dose
*added* that the conversation never stated (Ch 9's territory) are not measured here.

## 4. Rejected/hypothetical dose stated in conversation: D2N023, «175 mg» — PRESENT in all 6 notes, framed as declined

Dialogue: "[patient] okay , what about increasing my testosterone to 175 milligrams ?
i'm at 140 now . [doctor] well , your levels are high . ... your risk will only
astronomically go up the higher the dose that we go on ."

This never became a candidate: all six notes carry it, explicitly as a declined
escalation, e.g. template s2 ASSESSMENT AND PLAN: "Continue 1 mL (140 mg) IM every
10 days. **Do not increase to 175 mg at this time.**"; permission s2: "Declined dose
escalation to 175mg due to risk...". So the hypothetical-dose category ended up empty
on the omission side: the one rejected dose was kept *and* labelled rejected.

## 5. Excluded mentions (9) — printed with reasons, each read

| encounter | mention | reason |
|---|---|---|
| D2N049 | "twenty three hundred milligrams" | dietary sodium ("lower your salt intake to like like twenty three hundred milligrams a a day") |
| D2N118 | "twenty three hundred milligrams" | dietary sodium ("twenty three hundred milligrams or less of sodium per day") |
| D2N139 | "2000 milligrams" | dietary sodium ("keep your salt under 2000 milligrams a day") |
| D2N139 | "1500 milligrams" | dietary sodium ("the actual recommendation is- is 1500 milligrams per day") |
| D2N023 | "265 milligrams" x2, "145 milligrams" | triglycerides, "milligrams per deciliter" — lab concentration |
| D2N101 | "1,792 grams" | breast-tissue resection mass (Schnur scale), not a dose |
| D2N101 | "a g" | "wearing about a g cup" — bra size, bare letter g |

Rule forms: (a) "per deciliter" within 30 chars after the unit; (b) grams with amount > 10;
(c) word-number attached to the bare letter "g"; (d) >= 1000 mg with salt/sodium/intake
within 80 chars. Rule (d) was checked against the three metformin-1000-mg doses (no salt
word nearby — all kept) and against D2N008, where "watch your salt intake" follows
"lisinopril 10 milligrams" (kept: 10 < 1000).

## 6. Near-miss ledger: doses spoken WITHOUT a unit word (outside the denominator, each read)

1. D2N027 "and **2000s** on the other six days" — all 6 notes wrote "2,000 units". Carried.
2. D2N023 "i'm at **140** now" (testosterone) — all 6 notes carry 140; e.g. "1 mL IM every
   10 days delivering 140 mg". Carried, with the unit inferred.
3. D2N026 "[doctor] are you taking **300 or 100** ? [patient] um , not sure" (gabapentin) —
   the dose is genuinely unknown in the conversation; 5 of its 6 notes flag it
   ("Gabapentin (dose uncertain; patient unsure if taking 300 mg or 100 mg)").
4. D2N018 "we'll do **lortab 500-** lortab **5 milligram**" — truncated self-correction;
   the 5 mg is in the denominator (carried by all 6 notes: "Prescribed Lortab 5 mg,
   1-2 tablets every 6 hours as needed for pain (20 tablets)"); the cut-off "500-"
   fragment is not, and no note invents a 500.
5. D2N023 testosterone "**1 milliliter** every 10 days" — volume, outside the mass-unit
   fact type; the notes carry it anyway.

None of these was silently dropped either; they are simply not counted.

## 7. Notes that signal a dose gap (any note, any med)

15 lines across the 360 notes flag a missing or uncertain dose/medication, and each flags
something genuinely absent or uncertain in its conversation (gabapentin "300 or 100";
"Metformin (current dose not specified in visit)" where the dialogue states only the new
1000 mg target; unnamed "diabetes medication"/"blood pressure medication"). 10 of the 15
are permission-prompt notes, 5 template. None fabricates certainty; none was needed for
the one candidate above.

## 8. Parser corrections made during development

1. Stutter rule: "six hundred six hundred milligrams" (D2N199, guaifenesin) initially
   risked parsing as 60,600; the parser now restarts on an ill-formed continuation and
   keeps the last well-formed number -> 600 mg.
2. Article rule: "a twenty one milligram nicotine patch" (D2N043) -> 21 mg, "a" treated
   as article unless directly before hundred/thousand ("a thousand milligrams" -> 1000).
3. Fraction rule: "seven and a half milligrams" -> 7.5; "two and a half milligram" -> 2.5.
4. Bare-"g" rule added after "a g cup" (D2N101).
5. Dietary-sodium rule tightened to >= 1000 mg + salt/sodium/intake within 80 chars after
   checking it could not touch any real dose.
6. Hand drug-map coverage: the script's completeness check caught two encounters missing
   from the first map (D2N002 Ultram 50 mg, D2N137 lisinopril 10 mg); added, re-run.
   No extraction change — a map gap, not a parse error.

Digit-form raw count matched Prachi's quick scan exactly (51); word-form kept 29 vs her
~24 — the extra are the harder spoken forms above (items 1–3, "a thousand milligrams").
