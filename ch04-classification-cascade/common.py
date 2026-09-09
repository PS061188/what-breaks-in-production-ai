"""Corpus, category taxonomy, and the shared scoring for Chapter 4.

**Where the ground truth comes from.** An FDA label is already partitioned into
named sections by the people who wrote it. Take a passage out of one of those
sections, remove the header, and the section it came from *is* its class. No one
labelled anything. If a passage sits in ADVERSE REACTIONS, its category is
adverse_reactions, and there is nothing to argue with — the same property
Chapter 9 uses when it treats a missing section as the correct answer being
nothing.

That gives a 10-way classification task over 96 passages from 12 real documents,
with a distribution nobody chose: 12 dosage passages, 7 contraindication
passages, and no geriatric passage at all for four of the drugs.

**Why the header has to come off.** Every section in this corpus opens by
restating its own name — `4 CONTRAINDICATIONS Metformin ... is contraindicated
in patients with:`. Left in, the task is a string match and measures nothing.
`strip_header()` removes the leading number and the section title. It cannot
remove cross-references in the body (`[see Warnings and Precautions (5.1)]`),
and those are real text, so they stay; `leak_rate()` counts how many passages
still name their own category somewhere, and both scripts print it. Read the
accuracy against that number.

**The cascade.** Classification is not the interesting part on its own. Each
passage is then handed to a second model call — an extraction stage whose task
is chosen by the label. A passage classified `contraindications` goes to the
contraindication extractor. When the label is wrong, the wrong extractor runs,
and the question this chapter exists to answer is whether it notices. It is
given an explicit escape hatch (return null) so that it can.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.llm import LLM, load_labels  # noqa: E402
from shared.scoring import normalise_ws, pct, table  # noqa: E402

# The ten label sections used as categories. Chosen for coverage — every one of
# these appears in at least 7 of the 12 labels with enough text to chunk — not
# for how easy they are to tell apart. pediatric_use and geriatric_use are
# near-neighbours and stay in for that reason: real taxonomies have them.
CATEGORIES = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "adverse_reactions",
    "drug_interactions",
    "overdosage",
    "how_supplied",
    "description",
    "pediatric_use",
    "geriatric_use",
]

# What each category means, for the prompt. These are descriptions of the
# section, not hints about the corpus.
CATEGORY_DESCRIPTIONS = {
    "indications_and_usage": "the conditions the drug is approved to treat",
    "dosage_and_administration": "how much to give, how often, and by what route",
    "contraindications": "situations in which the drug must not be used at all",
    "adverse_reactions": "side effects and reactions observed in patients",
    "drug_interactions": "effects of taking this drug alongside other drugs or foods",
    "overdosage": "signs of overdose and how to manage one",
    "how_supplied": "dosage forms, strengths, packaging and storage",
    "description": "chemical name, structure, formulation and inactive ingredients",
    "pediatric_use": "what is known about use in children",
    "geriatric_use": "what is known about use in patients 65 and older",
}

# The downstream stage the label selects. This is the cascade: the classifier
# picks one of these, and whichever it picks runs on the passage.
DOWNSTREAM_TASKS = {
    "indications_and_usage": (
        "indication_extraction",
        "List every condition this drug is indicated to treat.",
    ),
    "dosage_and_administration": (
        "dosing_extraction",
        "State the recommended dose, frequency and route of administration.",
    ),
    "contraindications": (
        "contraindication_extraction",
        "List every situation in which this drug must not be used.",
    ),
    "adverse_reactions": (
        "adverse_event_extraction",
        "List every adverse reaction reported for this drug.",
    ),
    "drug_interactions": (
        "interaction_extraction",
        "List every drug, food or substance that interacts with this drug.",
    ),
    "overdosage": (
        "overdose_protocol",
        "State how an overdose of this drug presents and how it should be managed.",
    ),
    "how_supplied": (
        "packaging_extraction",
        "State the dosage forms, strengths and package sizes this drug is supplied in.",
    ),
    "description": (
        "composition_extraction",
        "State the chemical name, molecular formula and inactive ingredients.",
    ),
    "pediatric_use": (
        "pediatric_extraction",
        "State what is known about the use of this drug in pediatric patients.",
    ),
    "geriatric_use": (
        "geriatric_extraction",
        "State what is known about the use of this drug in patients 65 and older.",
    ),
}

# Header text that appears at the top of a section in this corpus, longest
# first so "indications and usage" is stripped before "indications". Furosemide
# heads its geriatric section "Geriatric Population" rather than "Geriatric
# Use"; Metformin heads packaging "HOW SUPPLIED/STORAGE AND HANDLING". These
# are the actual strings in the data, checked by test_strip_header().
HEADER_ALIASES = {
    "indications_and_usage": ["indications and usage", "indications & usage", "indications"],
    "dosage_and_administration": ["dosage and administration", "dosage & administration", "dosage"],
    "contraindications": ["contraindications"],
    "adverse_reactions": ["adverse reactions", "adverse events"],
    "drug_interactions": ["drug interactions", "drug/laboratory test interactions"],
    "overdosage": ["overdosage", "overdose"],
    "how_supplied": [
        "how supplied/storage and handling",
        "how supplied and storage and handling",
        "how supplied",
        "storage and handling",
    ],
    "description": ["description"],
    "pediatric_use": ["pediatric use", "pediatric patients", "use in children"],
    "geriatric_use": ["geriatric use", "geriatric population", "use in the elderly", "elderly"],
}

# For the leakage count only: the section's actual title, not the loose
# fallbacks above. `dosage_and_administration` is not "leaking" because its body
# contains the word *dosage* — every dosing passage does. It leaks when the body
# contains the section title, which is what a classifier could match on without
# reading anything.
LEAK_PHRASES = {
    "indications_and_usage": ["indications and usage", "indications & usage"],
    "dosage_and_administration": ["dosage and administration", "dosage & administration"],
    "contraindications": ["contraindications", "contraindicated"],
    "adverse_reactions": ["adverse reactions"],
    "drug_interactions": ["drug interactions"],
    "overdosage": ["overdosage"],
    "how_supplied": ["how supplied"],
    "description": ["description"],
    "pediatric_use": ["pediatric use"],
    "geriatric_use": ["geriatric use"],
}

MIN_SECTION_CHARS = 200
TARGET_CHUNK_CHARS = 700

# Filler and absence phrases, so "the downstream stage declined" is decided by
# code and not by reading. Lifted from ch09's is_absent_answer() — the same
# predicate, because it is answering the same question and the two chapters'
# numbers should be comparable. Deliberately generous: anything ambiguous is
# scored as an answer, so the cascade rate reported is a floor, not a ceiling.
FILLER = {
    "n/a", "na", "none", "null", "unknown", "not applicable", "not specified",
    "not stated", "not provided", "not mentioned", "not included", "not available",
    "not addressed", "not found", "not discussed", "not described", "not documented",
    "no information", "to be determined", "tbd", "-", "",
}

ABSENCE_MARKERS = [
    "not specified", "not stated", "not provided", "not mentioned", "not included",
    "not available", "not addressed", "not found", "not discussed", "not described",
    "not contain", "does not", "do not contain", "no information", "no specific",
    "cannot be determined", "this passage does not", "the passage does not",
]


def is_absent_answer(value) -> bool:
    """True when the downstream stage returned nothing, filler, or an explicit 'not here'."""
    if value is None:
        return True
    text = normalise_ws(str(value)).rstrip(".")
    if text in FILLER:
        return True
    return any(marker in text for marker in ABSENCE_MARKERS)


def strip_header(section: str, text: str) -> str:
    """Remove the leading section number and title.

    `4 CONTRAINDICATIONS Metformin ... ` -> `Metformin ... `

    Without this the classification task is a string match on the first three
    words and every prompt scores 100%. With it, the model has to read.
    """
    out = re.sub(r"^\s*\d+(\.\d+)*\s+", "", text.strip())
    for alias in HEADER_ALIASES.get(section, []):
        if out[: len(alias)].lower() == alias:
            out = out[len(alias) :]
            break
    return out.lstrip(" :.—-\n").strip()


def chunk(text: str, target: int = TARGET_CHUNK_CHARS) -> list:
    """Split into passages at sentence boundaries, ~`target` characters each."""
    pieces = re.split(r"(?<=[.;:])\s+", text)
    out, current = [], ""
    for piece in pieces:
        current = f"{current} {piece}".strip() if current else piece
        if len(current) >= target:
            out.append(current)
            current = ""
    if current:
        if out and len(current) < target // 3:
            out[-1] = f"{out[-1]} {current}"
        else:
            out.append(current)
    return out


def build_cases(limit: int = 0, position: str = "first") -> list:
    """One passage per (label, section), derived from the corpus.

    `position` selects which chunk of the section is used. The default is the
    first, which is the obvious choice and also the most self-identifying one —
    a section's opening sentences tend to restate its purpose. So the accuracy
    reported by default is the friendly case. `--chunk middle` re-runs against
    passages taken from the body of each section; the README reports both, and
    the gap between them is worth more than either number alone.
    """
    labels = load_labels()
    if limit:
        labels = labels[:limit]
    cases = []
    for label in labels:
        for category in CATEGORIES:
            raw = label["sections"].get(category) or ""
            if len(raw.strip()) < MIN_SECTION_CHARS:
                continue
            body = strip_header(category, raw)
            pieces = chunk(body)
            if not pieces:
                continue
            index = {
                "first": 0,
                "middle": len(pieces) // 2,
                "last": len(pieces) - 1,
            }[position]
            cases.append(
                {
                    "case_id": f"{label['drug'][:18]}::{category}",
                    "drug": label["drug"],
                    # Derived from the corpus. This is the ground truth and
                    # nobody wrote it down.
                    "true_category": category,
                    "passage": pieces[index][:2400],
                    # Checked, and it does not bite: old-format labels nest
                    # pediatric_use, geriatric_use and drug_interactions inside
                    # precautions, so seven of these passages sit under two
                    # headings at once. `precautions` is not one of the ten
                    # categories the model may choose, so it can never be given
                    # as an answer, and no passage here appears verbatim under a
                    # second selectable category. The ground truth is single-valued.
                }
            )
    return cases


def names_own_category(case: dict) -> bool:
    """Does the passage still contain the title of its own section?

    Cross-references survive header stripping — `[see Warnings and Precautions]`
    — and some of them point at the section the passage is already in. Those
    passages are easier than the rest, and this counts them so the accuracy
    number can be read with that in mind.
    """
    text = normalise_ws(case["passage"])
    return any(phrase in text for phrase in LEAK_PHRASES[case["true_category"]])


def leak_rate(cases: list) -> str:
    return pct(sum(names_own_category(c) for c in cases), len(cases))


# --- the calls ---------------------------------------------------------------
#
# Both scripts import these rather than defining their own copies, and that is
# not tidiness. fixed.py's ensemble uses the book-prompt classifier as one of
# its members; because the prompt string, schema and token budget are the same
# object, the request hashes to the same fixture broken.py recorded. The
# ensemble's first vote is *literally the baseline's answer*, not a re-run of
# something similar. Whatever the two scripts report differently is therefore
# the code around the call.

CATEGORY_BLOCK = "\n".join(f"- {name}: {CATEGORY_DESCRIPTIONS[name]}" for name in CATEGORIES)

# Classifier A. What a classification step looks like when nobody has thought
# about uncertainty yet: baseline in broken.py, ensemble member in fixed.py.
NAIVE_SYSTEM = f"""You are a document classifier in a drug-label processing
pipeline. Assign the passage to exactly one category.

CATEGORIES:
{CATEGORY_BLOCK}

Return the category name."""

# Classifier B. Chapter 4's prompt template, adapted only in that the categories
# are this corpus's categories. The chain-of-thought steps, the confidence
# bands, the runner-up and the requires_human_review rule are the book's words.
BOOK_SYSTEM = f"""You are a document classifier. Classification errors propagate
to extraction, routing, and downstream processing - so accuracy and honest
uncertainty are required.

CATEGORIES:
{CATEGORY_BLOCK}

CHAIN-OF-THOUGHT REQUIRED:
Before stating your classification:
1. List the 3 most prominent features of this document that inform classification.
2. Consider which 2 categories are most plausible and why.
3. State which one wins and why the other was ruled out.
4. Assign a confidence score: HIGH (>90%), MEDIUM (70-90%), LOW (<70%)

OUTPUT FORMAT (strict JSON):
{{
  "reasoning": "<your step-by-step analysis>",
  "classification": "<CATEGORY>",
  "confidence": "HIGH | MEDIUM | LOW",
  "alternative_considered": "<second most likely category>",
  "requires_human_review": <true if confidence is LOW or MEDIUM>
}}

IMPORTANT: If confidence is LOW or MEDIUM, set requires_human_review to true.
Do not force a classification when the evidence is weak."""

# Classifier C. Third ensemble member, used only by fixed.py. Same model, a
# different question — which printed heading this text sat under — with the
# category list in the opposite order, since option order is a known lever on
# an LLM's choice. See the README on why an ensemble of prompts is a weaker
# thing than the ensemble of *models* the chapter describes.
HEADING_SYSTEM = """This text was printed in an FDA drug label, underneath one of
the headings listed below. The heading itself has been removed. Decide which
heading this text was printed under.

HEADINGS:
{block}

Answer with the heading name and nothing else.""".format(
    block="\n".join(f"- {name}: {CATEGORY_DESCRIPTIONS[name]}" for name in reversed(CATEGORIES))
)

# The downstream stage. It is told which category it is processing and it is
# given an explicit way out — return null if the passage does not contain what
# it was asked for. Without that escape hatch the cascade rate would be 100% by
# construction and would measure nothing.
DOWNSTREAM_SYSTEM = """You are the {task} stage of a drug-label processing
pipeline. The passage below has already been classified as {category}
({description}).

{instruction}

If the passage does not contain that information, return null for value.

<passage>
{passage}
</passage>"""


def label_only_schema() -> dict:
    return {
        "type": "object",
        "properties": {"classification": {"type": "string", "enum": CATEGORIES}},
        "required": ["classification"],
        "additionalProperties": False,
    }


def book_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string"},
            "classification": {"type": "string", "enum": CATEGORIES},
            "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
            "alternative_considered": {"type": "string", "enum": CATEGORIES},
            "requires_human_review": {"type": "boolean"},
        },
        "required": [
            "reasoning",
            "classification",
            "confidence",
            "alternative_considered",
            "requires_human_review",
        ],
        "additionalProperties": False,
    }


def downstream_schema() -> dict:
    return {
        "type": "object",
        "properties": {"value": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
        "required": ["value"],
        "additionalProperties": False,
    }


def blank_row(case: dict) -> dict:
    """The record schema both scripts fill in. Documented below."""
    return {
        "case_id": case["case_id"],
        "drug": case["drug"],
        "true_category": case["true_category"],
        "classification": None,
        "confidence": "n/a",
        "alternative_considered": "n/a",
        "requires_human_review": False,
        # Ensemble bookkeeping. Present in both scripts' records so the two
        # share one schema; broken.py has one classifier and leaves them empty.
        "votes": [],
        "agreeing": 0,
        "naive_label": None,
        "book_label": None,
        "majority_label": None,
        "routed": "auto",
        "route_reason": "",
        "downstream_task": None,
        "downstream_answer": None,
        "downstream_declined": None,
    }


def classify_naive(llm: LLM, case: dict) -> dict:
    result = llm.json(
        system=NAIVE_SYSTEM,
        user=f"<passage>\n{case['passage']}\n</passage>",
        schema=label_only_schema(),
        max_tokens=200,
    )
    row = blank_row(case)
    row["classification"] = result["classification"]
    return row


def classify_book(llm: LLM, case: dict) -> dict:
    result = llm.json(
        system=BOOK_SYSTEM,
        user=f"<passage>\n{case['passage']}\n</passage>",
        schema=book_schema(),
        max_tokens=1200,
    )
    row = blank_row(case)
    row["classification"] = result["classification"]
    row["confidence"] = result["confidence"]
    row["alternative_considered"] = result["alternative_considered"]
    row["requires_human_review"] = result["requires_human_review"]
    return row


def classify_heading(llm: LLM, case: dict) -> dict:
    result = llm.json(
        system=HEADING_SYSTEM,
        user=f"<passage>\n{case['passage']}\n</passage>",
        schema=label_only_schema(),
        max_tokens=200,
    )
    row = blank_row(case)
    row["classification"] = result["classification"]
    return row


def run_downstream(llm: LLM, case: dict, row: dict) -> dict:
    """Whatever the label says, that extractor runs. That is the cascade."""
    category = row["classification"]
    task, instruction = DOWNSTREAM_TASKS[category]
    result = llm.json(
        system=DOWNSTREAM_SYSTEM.format(
            task=task,
            category=category,
            description=CATEGORY_DESCRIPTIONS[category],
            instruction=instruction,
            passage=case["passage"],
        ),
        user=f"Run the {task} stage on this passage.",
        schema=downstream_schema(),
        max_tokens=900,
    )
    row = dict(row)
    row["downstream_task"] = task
    row["downstream_answer"] = result["value"]
    row["downstream_declined"] = is_absent_answer(result["value"])
    return row


# --- the shared result record ------------------------------------------------
#
# broken.py and fixed.py both produce a list of these, and both are scored by
# the functions below. The scripts differ in the prompt and in the code around
# the call — never in what they hand the scorer.
#
#   case_id, drug, true_category   from the corpus
#   classification                 what the pipeline decided
#   confidence                     HIGH | MEDIUM | LOW | n/a
#   alternative_considered         the model's runner-up, or "n/a"
#   requires_human_review          what the model said about itself
#   routed                         "auto" | "review"   (what the code did)
#   downstream_task                which extractor ran, or None
#   downstream_answer              what it returned, or None
#   downstream_declined            bool, or None if the stage did not run


def correct(row: dict) -> bool:
    return row["classification"] == row["true_category"]


def per_category_f1(rows: list) -> list:
    """Precision, recall and F1 per category. Ordinary counting, no model.

    Fix 3 in the chapter is a holdout set with a per-category F1 gate, on the
    argument that aggregate accuracy hides category-level degradation. This is
    the smallest honest version of that: the corpus is the holdout set, the
    ground truth is derived, and the table shows whether the argument holds
    here.
    """
    out = []
    for category in CATEGORIES:
        support = sum(r["true_category"] == category for r in rows)
        predicted = sum(r["classification"] == category for r in rows)
        hit = sum(
            r["true_category"] == category and r["classification"] == category for r in rows
        )
        precision = hit / predicted if predicted else 0.0
        recall = hit / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out.append(
            {
                "category": category,
                "support": support,
                "predicted": predicted,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
    return out


def report_classification(rows: list, cases: list) -> None:
    """The block both scripts print, so the two runs are read the same way."""
    total = len(rows)
    right = sum(correct(r) for r in rows)

    errors = [r for r in rows if not correct(r)]
    if errors:
        print()
        table(
            ["drug", "true category", "classified as", "conf", "runner-up", "routed"],
            [
                [
                    r["drug"][:18],
                    r["true_category"],
                    r["classification"],
                    r["confidence"],
                    r["alternative_considered"],
                    r["routed"],
                ]
                for r in errors
            ],
        )

    print(f"\n>> Classification accuracy: {pct(right, total)}")
    print(f"   Passages that still name their own section somewhere: {leak_rate(cases)}")
    print("   (Those are the easy ones. The accuracy above includes them.)")


def report_confidence(rows: list) -> None:
    """Does self-reported confidence predict correctness?

    This is the number Fix 1 stands on. Confidence-gated routing assumes a LOW
    or MEDIUM stamp identifies the errors; if the errors arrive stamped HIGH,
    the gate routes the wrong cases to the humans and lets the wrong labels
    through, at full cost.
    """
    graded = [r for r in rows if r["confidence"] in ("HIGH", "MEDIUM", "LOW")]
    if not graded:
        return
    print()
    table(
        ["self-reported confidence", "cases", "share of all", "accuracy"],
        [
            [
                level,
                str(len(bucket)),
                pct(len(bucket), len(graded)),
                pct(sum(correct(r) for r in bucket), len(bucket)),
            ]
            for level in ("HIGH", "MEDIUM", "LOW")
            for bucket in [[r for r in graded if r["confidence"] == level]]
            if bucket
        ],
    )
    errors = [r for r in graded if not correct(r)]
    if errors:
        stamped_high = sum(r["confidence"] == "HIGH" for r in errors)
        print(f"\n>> Errors that arrived stamped HIGH: {pct(stamped_high, len(errors))}")
        print("   Every one of those is a wrong label a confidence gate waves through.")
    else:
        print("\n>> No misclassifications, so nothing to say about which ones felt uncertain.")
    disagree = sum(
        r["requires_human_review"] != (r["confidence"] in ("MEDIUM", "LOW")) for r in graded
    )
    print(
        f">> Self-consistency: requires_human_review disagreed with the model's own "
        f"confidence on {pct(disagree, len(graded))}"
    )
    print("   The prompt states the rule explicitly. This is the model applying it to itself.")


def report_audit_trail(rows: list) -> None:
    """Fix 4: log the runner-up, then query for cases where it was right.

    Nothing is inferred here — `alternative_considered` is in the record, the
    true category is derived from the corpus, and this compares two strings.
    """
    errors = [r for r in rows if not correct(r)]
    if not errors:
        print("\n>> Audit trail: no misclassifications to query.")
        return
    recoverable = sum(r["alternative_considered"] == r["true_category"] for r in errors)
    print(
        f"\n>> Audit trail: misclassifications whose alternative_considered was the "
        f"true category: {pct(recoverable, len(errors))}"
    )
    print(
        "   The ceiling on what the chapter's weekly query can recover. The rest are "
        "errors where the model never considered the right answer at all."
    )


def report_cascade(rows: list) -> None:
    """The chapter's central claim, measured.

    Cascade = the label was wrong, the wrong extractor ran, and it returned a
    confident answer instead of noticing. The counter-metric underneath is the
    same stage's answer rate when the label was *right* — without it, a low
    cascade rate could just mean the extractor declines on everything.
    """
    ran = [r for r in rows if r["downstream_declined"] is not None]
    wrong = [r for r in ran if not correct(r)]
    right = [r for r in ran if correct(r)]

    if wrong:
        print()
        table(
            ["drug", "true category", "extractor that ran", "downstream output (first 60)"],
            [
                [
                    r["drug"][:18],
                    r["true_category"],
                    r["downstream_task"],
                    ("DECLINED" if r["downstream_declined"] else str(r["downstream_answer"] or "")[:60])
                    .replace("\n", " "),
                ]
                for r in wrong
            ],
        )

    cascaded = sum(not r["downstream_declined"] for r in wrong)
    print(
        f"\n>> Cascade rate: {pct(cascaded, len(wrong)) if wrong else 'n/a (no misclassifications reached a downstream stage)'}"
    )
    print(
        "   Share of wrong labels where the downstream stage produced a confident "
        "answer for the wrong category rather than declining."
    )
    served = sum(not r["downstream_declined"] for r in right)
    print(f">> Counter-metric — downstream answer rate when the label was right: {pct(served, len(right))}")
    print("   If this were low, the cascade rate above would mean nothing.")


def report_f1_gate(rows: list, threshold: float = 0.80) -> None:
    scores = per_category_f1(rows)
    print()
    table(
        ["category", "support", "predicted", "precision", "recall", "F1", f"gate @ {threshold:.2f}"],
        [
            [
                s["category"],
                s["support"],
                s["predicted"],
                f"{s['precision']:.2f}",
                f"{s['recall']:.2f}",
                f"{s['f1']:.2f}",
                "pass" if s["f1"] >= threshold else "FAIL",
            ]
            for s in scores
            if s["support"]
        ],
    )
    failing = [s["category"] for s in scores if s["support"] and s["f1"] < threshold]
    right = sum(correct(r) for r in rows)
    print(f"\n>> Aggregate accuracy: {pct(right, len(rows))}")
    if failing:
        print(f">> Categories below F1 {threshold:.2f}: {', '.join(failing)}")
        print("   A deployment gate on aggregate accuracy alone ships all of them.")
    else:
        print(f">> No category is below F1 {threshold:.2f}. The gate would not fire on this corpus.")
