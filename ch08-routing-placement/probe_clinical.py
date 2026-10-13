"""Chapter 8, probe: placement on real clinical notes — the corpus the failure needs.

Every earlier Chapter 8 test gave the model a document whose sections differ
in meaning (FDA labels, with or without headings) or whose roles are stated by
a label (generated shipping documents), and nothing was misplaced. The failure
the case-study papers measure is content filed under the wrong heading of a
clinical note, where the same sentence can belong to two sections and a
convention decides which.

Corpus: ACI-Bench (Yim, Fu, Ben Abacha, Snider, Lin, Yetisgen; Nature
Scientific Data 2023; CC BY 4.0) — doctor-patient encounters with reference
visit notes checked and rewritten by medical scribes or physicians. Sixty notes,
twenty per subset, in data/aci_bench_notes.json (source, licence and the
selection rule are recorded in the file).

Each note is divided into four sections with the rule of the MEDIQA-Chat 2023
section tagger (scripts/sectiontagger.py in github.com/abachaa/MEDIQA-Chat-2023,
which ACI-Bench's own evaluation imports): the first heading of each kind opens
the division, which runs to the next such heading. Its header lists are
re-implemented below verbatim, and the re-implementation gives the same spans
as the original on all 207 notes of the corpus.

  subjective            chief complaint, history of present illness, review of
                        systems, and the history / medication / allergy blocks
                        that follow them
  objective_exam        physical exam
  objective_results     results / findings
  assessment_and_plan   assessment, plan, and the instructions that follow

Blocks headed VITALS are left out of the scoring: the tagger files them under
subjective by position (they sit between the review of systems and the exam),
the note's own heading makes them a section of their own, and clinical
convention calls them objective. That is a convention conflict — the chapter's
subject — but not one to score either way.

The note's sentences are shuffled, headings removed, and the model is asked to
file every sentence under one of the four headings. Ground truth is exact: the
division each sentence sits in, in the human-written note. A sentence whose
exact text appears in two divisions (the opening line is often restated under
the assessment; 50 pairs in the corpus) is correct under either.

Four prompts, three live draws each (the helper's `sample` index):
  plain     the four headings, nothing more
  defined   plus a definition of what each heading may contain — the chapter's
            first fix, "constrain fields to sections in the schema"
  graded    defined, plus placement_confidence HIGH/MEDIUM/LOW per sentence and
            requires_review — the fuller prompt of "What did not survive
            testing", on a set that has real errors for the grade to land on
  tagged    plain, but every sentence carries the heading it was written under:
            provenance kept through the merge step, measured live rather than
            by construction (demo_provenance.py)

Scored per sentence: correct; misplaced (filed under one heading, not its own);
duplicate (filed under two headings); missing (not filed); unknown (an ID that
was not in the input). The last three are the chapter's impossible states.

Usage:
  python probe_clinical.py           # replay
  python probe_clinical.py --live    # record three draws per prompt (~$3)
  NOTES=2 python probe_clinical.py   # first two notes only (smoke test)
"""

import collections
import json
import os
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from shared.llm import LLM, base_args, map_parallel  # noqa: E402

DATA = HERE.parent / "data" / "aci_bench_notes.json"
DIVISIONS = ("subjective", "objective_exam", "objective_results", "assessment_and_plan")
HEADING = {"subjective": "SUBJECTIVE", "objective_exam": "OBJECTIVE EXAM",
           "objective_results": "OBJECTIVE RESULTS", "assessment_and_plan": "ASSESSMENT AND PLAN"}
RUNS = (1, 2, 3)

# Header lists of the MEDIQA-Chat 2023 section tagger, in its order. An entry
# with a colon matches a line that starts with it (colon included) or a line
# that is exactly the words; an entry without a colon matches any line that
# starts with the words. Spaces match any run of whitespace. Case-insensitive.
DIVISION_HEADERS = {
    "subjective": ["cc :", "chief complaint :", "reason for visit :",
                   "history :", "history of present illness :", "history of present illness", "hpi :", "hpi",
                   "hpi notes :", "interval history :", "interval hx :", "subjective :",
                   "ros :", "review of system :", "review of systems :"],
    "objective_exam": ["physical exam :", "physical examination :", "pe :", "physical findings :", "examination :", "exam :"],
    "objective_results": ["results :", "findings :"],
    "assessment_and_plan": ["assessment :", "a:", "plan :", "plan of care :", "p:", "medical decision-making plan :",
                            "summary plan", "ap :", "a / p :", "assessment and plan :", "assessment & plan :",
                            "disposition / plan :"],
}


def _patterns():
    out = []
    for div, headers in DIVISION_HEADERS.items():
        for h in headers:
            words = r"\s*".join(re.escape(w) for w in h.split(" "))
            if h.endswith(":"):
                bare = r"\s*".join(re.escape(w) for w in h[:-1].strip().split(" "))
                out.append((div, re.compile(r"^\s*(?:" + words + r".*|" + bare + r"\s*)$", re.I)))
            else:
                out.append((div, re.compile(r"^\s*" + words + r".*$", re.I)))
    return out


PATTERNS = _patterns()


def header_division(line):
    for div, rx in PATTERNS:
        if rx.match(line):
            return div
    if re.match(r"\s*IMPRESSION", line):  # the tagger's special case: uppercase IMPRESSION opens the assessment
        return "assessment_and_plan"
    return None


def divide(note):
    """(division, start, end) spans, text offsets, header line excluded."""
    first = {}
    offset = 0
    for i, line in enumerate(note.split("\n")):
        div = header_division(line)
        if i == 0 and div is None:
            first["subjective"] = (0, 0)  # the tagger's headerless opening, relabelled subjective
        if div and div not in first:
            first[div] = (offset, offset + len(line))
        offset += len(line) + 1
    order = sorted(first.items(), key=lambda kv: kv[1][0])
    spans = []
    for k, (div, (start, header_end)) in enumerate(order):
        end = order[k + 1][1][0] if k + 1 < len(order) else len(note)
        spans.append((div, header_end, end))
    return spans


HEADER_LINE = re.compile(r"^[A-Z][A-Z0-9 /&,\-()]{1,50}:?$")


def units(note):
    """(sentence, division) for every scored sentence of the note, in note order."""
    out = []
    for div, start, end in divide(note):
        skipping = False
        for line in note[start:end].split("\n"):
            t = line.strip()
            if not t:
                continue
            if HEADER_LINE.match(t):
                skipping = t.startswith("VITALS")
                continue
            if skipping:
                continue
            for s in re.split(r"(?<=[.;])\s+(?=[A-Z•\d(])", t):
                s = s.strip()
                if len(s) >= 20:
                    out.append((s, div))
    return out


def build_cases():
    notes = json.loads(DATA.read_text(encoding="utf-8"))["notes"]
    limit = int(os.environ.get("NOTES", "0") or 0)
    cases = []
    for n in notes[: limit or None]:
        us = units(n["note"])
        where = collections.defaultdict(set)
        for s, div in us:
            where[s.lower()].add(div)
        order = list(range(len(us)))
        random.Random(n["encounter_id"]).shuffle(order)
        items = []
        for k, idx in enumerate(order, 1):
            s, div = us[idx]
            items.append({"id": f"S{k}", "text": s, "division": div, "truth": where[s.lower()]})
        cases.append({**n, "items": items})
    return cases


COMMON = ("You are assembling a clinical visit note. The sentences of one note are listed below in random order "
          "with their section headings removed. File every sentence under one of these four headings: SUBJECTIVE, "
          "OBJECTIVE EXAM, OBJECTIVE RESULTS, ASSESSMENT AND PLAN. In the JSON, the headings are the keys subjective, "
          "objective_exam, objective_results and assessment_and_plan. Return each sentence ID under exactly one "
          "heading. Do not leave any sentence out and do not invent IDs.")
DEFINITIONS = """

SECTION DEFINITIONS
- SUBJECTIVE: what the patient reports and the history taken before the examination: the reason for the visit, the history of the present illness, the review of systems, past medical, surgical, family and social history, current medications and allergies.
- OBJECTIVE EXAM: what the clinician found on physical examination at this visit, including vital signs measured at the visit.
- OBJECTIVE RESULTS: results of laboratory tests, imaging and other studies that were reviewed.
- ASSESSMENT AND PLAN: the clinician's diagnoses or impressions, the reasoning behind them, treatment decisions, prescriptions, orders, referrals, patient instructions and follow-up.
A sentence goes under the heading that names its role in the note, not its topic. A symptom the patient reports belongs under SUBJECTIVE even if the plan discusses it again; a sentence that restates a symptom or finding to justify a decision belongs under ASSESSMENT AND PLAN."""
GRADE = ("\n\nFor each sentence also give placement_confidence: HIGH, MEDIUM or LOW, meaning how sure you are that it "
         "belongs under that heading rather than another. If any sentence is LOW, set requires_review to true.")
TAGGED = ("You are assembling a clinical visit note. The sentences of one note are listed below in random order. Each "
          "sentence carries, in square brackets, the heading it was written under. File every sentence under that "
          "heading. In the JSON, the headings are the keys subjective, objective_exam, objective_results and "
          "assessment_and_plan. Return each sentence ID under exactly one heading. Do not leave any sentence out and "
          "do not invent IDs.")

PROMPTS = {"plain": (COMMON, False, False), "defined": (COMMON + DEFINITIONS, False, False),
           "graded": (COMMON + DEFINITIONS + GRADE, True, False), "tagged": (TAGGED, False, True)}


def listing(case, tagged):
    lines = []
    for it in case["items"]:
        tag = f" [{HEADING[it['division']]}]" if tagged else ""
        lines.append(f"{it['id']}{tag}: {it['text']}")
    return "\n\n<sentences>\n" + "\n".join(lines) + "\n</sentences>"


def schema(graded):
    if graded:
        item = {"type": "object",
                "properties": {"id": {"type": "string"},
                               "placement_confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]}},
                "required": ["id", "placement_confidence"], "additionalProperties": False}
    else:
        item = {"type": "string"}
    props = {d: {"type": "array", "items": item} for d in DIVISIONS}
    req = list(DIVISIONS)
    if graded:
        props["requires_review"] = {"type": "boolean"}
        req.append("requires_review")
    return {"type": "object", "properties": props, "required": req, "additionalProperties": False}


def score(case, result, graded):
    filed = collections.defaultdict(list)
    grade = {}
    for div in DIVISIONS:
        for item in result.get(div, []) or []:
            sid = (item["id"] if graded else item).strip().upper()
            filed[sid].append(div)
            if graded:
                grade[sid] = item["placement_confidence"]
    known = {it["id"] for it in case["items"]}
    counts = collections.Counter()
    confusion = collections.Counter()
    verdict = {}
    for it in case["items"]:
        f = filed.get(it["id"], [])
        if not f:
            v = "missing"
        elif len(f) > 1:
            v = "duplicate"
        elif f[0] in it["truth"]:
            v = "correct"
        else:
            v = "misplaced"
            confusion[("/".join(sorted(it["truth"])), f[0])] += 1
        counts[v] += 1
        verdict[it["id"]] = v
    counts["unknown"] = sum(1 for sid in filed if sid not in known)
    return counts, confusion, verdict, grade, bool(result.get("requires_review"))


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(HERE, model=args.model, live=args.live)
    cases = build_cases()
    n_units = sum(len(c["items"]) for c in cases)
    per_division = ", ".join(
        "%s: %d" % (d, sum(1 for c in cases for it in c["items"] if it["division"] == d)) for d in DIVISIONS)
    print(f"{len(cases)} ACI-Bench notes, {n_units} scored sentences ({per_division})\n")

    jobs = [(name, run, i) for name in PROMPTS for run in RUNS for i in range(len(cases))]

    def call(job):
        name, run, i = job
        system, graded, tagged = PROMPTS[name]
        return llm.json(system=system + listing(cases[i], tagged), user="File the sentences.",
                        schema=schema(graded), max_tokens=4000, sample=run)

    results = dict(zip(jobs, map_parallel(call, jobs, workers=8)))

    scored = {}
    for job in jobs:
        name, run, i = job
        scored[job] = score(cases[i], results[job], PROMPTS[name][1])

    print(f"{'prompt':8} {'run':>3} {'correct':>8} {'misplaced':>10} {'duplicate':>10} {'missing':>8} {'unknown':>8}   misplaced %   (of {n_units} sentences)")
    for name in PROMPTS:
        for run in RUNS:
            c = collections.Counter()
            for i in range(len(cases)):
                c.update(scored[(name, run, i)][0])
            print(f"{name:8} {run:>3} {c['correct']:>8} {c['misplaced']:>10} {c['duplicate']:>10} {c['missing']:>8} {c['unknown']:>8}   {100 * c['misplaced'] / n_units:6.1f}")
        print()

    print(">> Misplaced by subset, summed over the three runs (misplaced / sentences)")
    for name in PROMPTS:
        parts = []
        for ds in ("aci", "virtassist", "virtscribe"):
            m = n = 0
            for run in RUNS:
                for i, case in enumerate(cases):
                    if case["dataset"] != ds:
                        continue
                    m += scored[(name, run, i)][0]["misplaced"]; n += len(case["items"])
            parts.append(f"{ds} {m}/{n} ({100 * m / n:.1f}%)" if n else f"{ds} -")
        print(f"   {name:8} " + "   ".join(parts))
    print()

    print(">> Where misplaced sentences went (true section -> filed section), summed over runs")
    for name in ("plain", "defined"):
        conf = collections.Counter()
        for run in RUNS:
            for i in range(len(cases)):
                conf.update(scored[(name, run, i)][1])
        print(f"   {name:8} " + "; ".join(f"{a} -> {b}: {n}" for (a, b), n in conf.most_common(6)))
    print()

    print(">> Stability of the plain prompt: sentences misplaced in 3, 2, 1 of the 3 runs")
    tally = collections.Counter()
    for i, case in enumerate(cases):
        for it in case["items"]:
            k = sum(scored[("plain", run, i)][2].get(it["id"]) == "misplaced" for run in RUNS)
            if k:
                tally[k] += 1
    print(f"   in all 3 runs: {tally[3]}   in 2: {tally[2]}   in 1: {tally[1]}\n")

    print(">> Graded prompt: does the grade track the errors? (sentences, all runs)")
    g = collections.Counter()
    review = collections.Counter()
    for run in RUNS:
        for i, case in enumerate(cases):
            counts, _, verdict, grade, flagged = scored[("graded", run, i)]
            for it in case["items"]:
                v = verdict[it["id"]]
                if v in ("correct", "misplaced"):
                    g[(grade.get(it["id"], "?"), v)] += 1
            bad = any(v != "correct" for v in verdict.values())
            review[(flagged, bad)] += 1
    for lvl in ("HIGH", "MEDIUM", "LOW"):
        print(f"   {lvl:6}  on correct: {g[(lvl, 'correct')]:>5}   on misplaced: {g[(lvl, 'misplaced')]:>4}")
    print(f"   requires_review set: notes with an error {review[(True, True)]}, notes without {review[(True, False)]}; "
          f"not set: notes with an error {review[(False, True)]}, notes without {review[(False, False)]}\n")

    print(">> Examples: sentences the defined prompt misplaced in run 1 (true section -> filed)")
    shown = 0
    for i, case in enumerate(cases):
        counts, _, verdict, _, _ = scored[("defined", 1, i)]
        res = results[("defined", 1, i)]
        for it in case["items"]:
            if verdict[it["id"]] == "misplaced" and shown < 10:
                filed = next(d for d in DIVISIONS if it["id"] in [x.strip().upper() for x in res.get(d, [])])
                print(f"   [{'/'.join(sorted(it['truth']))} -> {filed}] {it['text'][:120]}")
                shown += 1
    print()
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
