"""Corpus, cut-point derivation, and the deterministic scorers for Chapter 6.

Chapter 6's third engineering fix is about *conversation history management*:
truncate at a semantic boundary rather than at N tokens, so a fact is never cut
in half. This corpus has no conversation transcripts. What a history is,
mechanically, is a long string of prior context that has to be cut to fit a
budget — and a long FDA dosing section is exactly that string, with the
advantage that its contents are checkable.

So the experiment is built on real dosing sections, and the cut point is
derived from the document rather than chosen:

* A dosing section is a sequence of headed subsections — `2.3 Dosage
  Adjustment in Patients with Renal Impairment`, `Pediatric Patients:`,
  `Major Depressive Disorder –`. Those headings are in the labels; nobody added
  them.
* The MIDFACT budget lands inside the sentence that states a dose, on the digit
  itself, so a naive cut ends on a dangling clause: *"the usual initial dose of
  furosemide tablets is 20 to"*. That is the cut that turns out to matter.
* The NEAR budget lands immediately after a heading and before its first word of
  content, so a naive cut leaves a heading with nothing under it. Structural,
  self-announcing, and — measured — harmless.
* The CONTROL budget lands 200 characters into the *following* subsection, so
  the target subsection is complete under both cut policies. That is the
  counter-metric: it says whether backing off to a boundary throws away an
  answer that was already there.

Ground truth is derived twice over and never annotated:

* Every dose value in the corpus is found by one regex (`DOSE`). The set of
  values visible in a given truncated context is therefore computable, and so
  is the set that truncation removed.
* An answer is unsupported when it contains a dose value that does not appear
  in the context the model was actually given. No judgement, no second model.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.retrieval import stable_top_k  # noqa: E402,F401  (re-exported)

DATA = Path(__file__).resolve().parent.parent / "data"

# One regex finds every dose value in the corpus. Everything downstream — what
# the context contains, what truncation removed, what the answer asserted — is a
# set operation over its output, which is why no part of this chapter needs an
# answer key.
DOSE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(mg/kg/day|mcg/kg/day|mg/kg|mcg/kg|mg/day|mcg/day|mg|mcg|mL|units|mEq)\b",
    re.IGNORECASE,
)

# Three heading shapes, all of them present in the labels as filed.
NUMBERED = re.compile(r"(?:(?<=\s)|^)(\d+\.\d+)\s+(?=[A-Z][A-Za-z])")
COLON = re.compile(r"(?:(?<=\.\s)|(?<=\.\n))([A-Z][a-z]+(?:[ \-][A-Za-z()\-]+){0,5})\s*[:]\s")
DASHED = re.compile(r"([A-Z][a-z]+(?:[ \-][A-Za-z()\-]+){1,4})\s*[–—]\s*(?=[A-Z])")

# Lower-case words that can sit inside a title without ending it.
TITLE_STOPWORDS = {
    "in", "with", "of", "for", "and", "to", "the", "due", "or", "a", "an",
    "on", "from", "by", "at", "as", "between", "use", "using", "per",
}

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

MAX_CASES_PER_DRUG = 5
CONTROL_OVERSHOOT = 200  # how far into the next subsection the control budget lands


def dose_values(text: str) -> set:
    """Every dose value in `text`, normalised to '500 mg' form."""
    return {f"{m.group(1)} {m.group(2).lower()}" for m in DOSE.finditer(text or "")}


def _numbered_title(text: str, start: int):
    """Split '2.3 Dosage Adjustment in Renal Impairment Dosage adjustment in...'.

    The labels are filed as flat text with no line breaks, so the boundary
    between a heading and its first sentence has to be inferred. A title runs
    until a capitalised word that is followed by an ordinary lower-case word —
    that capitalised word is the start of the body sentence, not part of the
    heading.
    """
    match = re.match(r"(\d+\.\d+)\s+", text[start:])
    tokens = text[start + match.end():start + match.end() + 400].split()
    kept = []
    for i, token in enumerate(tokens):
        if len(kept) >= 10:
            break
        following = tokens[i + 1] if i + 1 < len(tokens) else ""
        if (
            kept
            and token[:1].isupper()
            and following[:1].islower()
            and following.strip(".,;:").lower() not in TITLE_STOPWORDS
        ):
            break
        kept.append(token)
    title = " ".join(kept).strip(" ,;:")
    return title, start + match.end() + len(title)


def headings(text: str) -> list:
    """(heading_start, body_start, title) for every heading in the section."""
    found = []
    for match in NUMBERED.finditer(text):
        title, body_start = _numbered_title(text, match.start())
        if title:
            found.append((match.start(), body_start, title))
    for match in COLON.finditer(text):
        found.append((match.start(1), match.end(), match.group(1).strip(" ()")))
    for match in DASHED.finditer(text):
        found.append((match.start(1), match.end(), match.group(1).strip(" ()")))
    found.sort()

    clean = []
    for heading in found:
        if clean and heading[0] < clean[-1][1]:
            continue
        clean.append(heading)
    return clean


def boundaries(text: str, limit: int) -> list:
    """Every semantic boundary at or before `limit`.

    A subsection heading is a topic shift — the thing Chapter 6 asks you to
    truncate at. A sentence end is the weaker fallback. Both are here because a
    real implementation would take whichever is closer to the budget.
    """
    marks = [0]
    marks += [start for start, _, _ in headings(text) if start <= limit]
    marks += [match.start() for match in SENTENCE_END.finditer(text) if match.start() + 1 <= limit]
    return marks


def naive_cut(text: str, budget: int) -> str:
    """Truncate at exactly N characters. The baseline."""
    return text[:budget]


def boundary_cut(text: str, budget: int) -> str:
    """Truncate at the last topic or sentence boundary at or before N characters."""
    return text[: max(boundaries(text, budget))].rstrip()


def load_labels() -> list:
    return json.loads((DATA / "labels.json").read_text())["labels"]


def load_versions() -> list:
    path = DATA / "label_versions.json"
    if not path.is_file():
        raise SystemExit("Run `python fetch_data.py --versions` first.")
    return json.loads(path.read_text())["versions"]


MIN_CLAUSE = 40      # keep this much of the subsection before a mid-fact cut
MIN_CUT_GAP = 60     # and this much between two cut points in the same subsection
MAX_MIDFACT_CUTS = 5


def _midfact_budgets(text: str, body_start: int, end: int, novel: set) -> list:
    """Where to cut so the sentence stating a dose is severed before the number.

    Each cut lands on the first digit of a dose value that appears nowhere
    earlier in the section, so the naive arm ends on a dangling clause — *"the
    usual initial dose of furosemide tablets is 20 to"* — and the value itself
    is provably absent from what the model was handed.

    `MIN_CLAUSE` keeps some of the subsection before the cut. Without it a
    subsection whose first word is a number would produce a cut identical to the
    NEAR one, and the two regimes would not be measuring different things.
    Several cuts per subsection, each on a different value, because one cut per
    subsection is eighteen observations and that is not enough to see a rate.
    Thirty-nine is not really enough either — see the README.
    """
    budgets = []
    for match in DOSE.finditer(text, body_start):
        if match.start() >= end:
            break
        value = f"{match.group(1)} {match.group(2).lower()}"
        if value not in novel or match.start() - body_start < MIN_CLAUSE:
            continue
        if budgets and match.start() - budgets[-1] < MIN_CUT_GAP:
            continue
        if value in dose_values(text[: match.start()]):
            continue
        budgets.append(match.start())
        if len(budgets) >= MAX_MIDFACT_CUTS:
            break
    return budgets


def build_cases(limit: int = 0) -> list:
    """Derive the truncation cases from the corpus.

    A subsection qualifies when it states at least one dose value that does not
    already appear earlier in the section. That condition is what makes the
    scoring airtight: if every value in a subsection were also printed in the
    highlights block at the top of the label — which is what happens on
    Metformin and Atorvastatin — then a model answering with one of those values
    would be reading, not fabricating, and the case would prove nothing.
    """
    cases = []
    for label in load_labels():
        text = label["sections"].get("dosage_and_administration", "")
        found = headings(text)
        if len(found) < 2:
            continue

        taken = 0
        for i, (heading_start, body_start, title) in enumerate(found[:-1]):
            if taken >= MAX_CASES_PER_DRUG:
                break
            next_start = found[i + 1][0]
            body = text[body_start:next_start]
            if len(body) < 150:
                continue

            hidden = dose_values(body)
            visible_before = dose_values(text[:body_start])
            novel = hidden - visible_before
            if not novel:
                continue

            midfact = _midfact_budgets(text, body_start, next_start, novel)
            if not midfact:
                continue

            cases.append(
                {
                    "drug": label["drug"],
                    "topic": title,
                    "text": text,
                    "heading_start": heading_start,
                    # MIDFACT: the cut lands inside the sentence that states the
                    # dose, immediately before the number. The excerpt ends
                    # "...the usual initial dose of furosemide tablets is 20 to".
                    "midfact_budgets": midfact,
                    # NEAR: the cut lands between the heading and its content.
                    "near_budget": body_start,
                    # CONTROL: the cut lands inside the *next* subsection, so
                    # the target subsection survives both cut policies.
                    "control_budget": min(next_start + CONTROL_OVERSHOOT, len(text)),
                    "hidden": sorted(hidden),
                    "novel": sorted(novel),
                    # The first dose value stated under the heading. Used only
                    # for the control-regime recall check.
                    "first_hidden": next(
                        (f"{m.group(1)} {m.group(2).lower()}" for m in DOSE.finditer(body)), None
                    ),
                }
            )
            taken += 1

        if limit and len({c["drug"] for c in cases}) >= limit:
            break
    return cases


def question(case: dict) -> str:
    """Derived from the document's own heading. Identical across both scripts."""
    return (
        f"Based only on the excerpt above, what is the recommended dosage of "
        f"{case['drug']} for: {case['topic']}?"
    )


def score(answer_text: str, context: str) -> dict:
    """Deterministic. Which dose values did the answer assert, and were they there?

    `unsupported` is the whole finding: a dose value in the answer that does not
    appear in the text the model was handed. There is no interpretation step and
    no second model call.
    """
    asserted = dose_values(answer_text)
    visible = dose_values(context)
    return {
        "asserted": sorted(asserted),
        "unsupported": sorted(asserted - visible),
    }


# --- the run, shared by broken.py and fixed.py -------------------------------

# Deliberately neutral. Chapter 6's own staleness-protocol prompt is tested
# separately in fix_freshness.py; putting it here would confound the truncation
# policy with a prompt change, and the point of this pair is that the two
# scripts differ by one function.
SYSTEM = """You are a clinical information assistant. Answer the question using
the drug label excerpt below.

<label_excerpt>
{context}
</label_excerpt>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "dose": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "the dosage stated for this topic, or null if the excerpt does not state one",
        },
    },
    "required": ["answer", "dose"],
    "additionalProperties": False,
}

REGIMES = [
    # (name, where the budget lands)
    ("MIDFACT", "inside the sentence that states the dose"),
    ("NEAR", "between the heading and its content"),
    ("CONTROL", "past the end of the subsection"),
]

FAILURE_REGIMES = ["MIDFACT", "NEAR"]


def jobs_for(case: dict) -> list:
    """(regime, budget) for one case. MIDFACT contributes several cut points."""
    out = [("MIDFACT", budget) for budget in case["midfact_budgets"]]
    out.append(("NEAR", case["near_budget"]))
    out.append(("CONTROL", case["control_budget"]))
    return out


def run(llm, cases: list, cut) -> list:
    """One row per (case, regime). `cut` is the only thing broken/fixed differ by.

    The row schema is defined here rather than in either script, so the two
    cannot drift apart. Every field is either copied from the corpus or computed
    by `score()`; nothing on this path calls a model to decide anything.
    """
    from shared.llm import map_parallel

    jobs = [(case, regime, budget) for case in cases for regime, budget in jobs_for(case)]

    def one(job):
        case, regime, budget = job
        context = cut(case["text"], budget)
        result = llm.json(
            system=SYSTEM.format(context=context),
            user=question(case),
            schema=SCHEMA,
            max_tokens=600,
        )
        answer_text = f"{result['answer']} {result['dose'] or ''}"
        scored = score(answer_text, context)
        hidden = set(case["hidden"])
        return {
            "drug": case["drug"],
            "topic": case["topic"],
            "regime": regime,
            "budget": budget,
            "context_chars": len(context),
            "discarded": budget - len(context),
            # Read off the structured field, not off the prose. An answer whose
            # text explains that the excerpt is truncated while mentioning a
            # dose in passing has still declined, and the schema is where it
            # said so.
            "declined": result["dose"] is None,
            "asserted": scored["asserted"],
            "unsupported": scored["unsupported"],
            # Of the unsupported values, which ones are the text truncation
            # removed? Those were not invented — they were completed.
            "from_cut_text": sorted(set(scored["unsupported"]) & hidden),
            "recalled": bool(set(scored["asserted"]) & hidden),
            "answer": result["answer"],
        }

    return map_parallel(one, jobs)


def report(rows: list) -> None:
    """Identical output for both scripts."""
    from shared.scoring import headline, pct, rule, table

    for regime, where in REGIMES:
        if regime not in FAILURE_REGIMES:
            continue
        subset = [r for r in rows if r["regime"] == regime]
        rule(f"{regime} — the budget lands {where}")
        table(
            ["drug", "topic", "cut at", "gave a dose?", "unsupported values", "from the cut text"],
            [
                [
                    r["drug"][:18],
                    r["topic"][:30],
                    r["budget"],
                    "declined" if r["declined"] else "ANSWERED",
                    ", ".join(r["unsupported"])[:32] or "-",
                    ", ".join(r["from_cut_text"])[:24] or "-",
                ]
                for r in subset
            ],
        )

    for regime in FAILURE_REGIMES:
        subset = [r for r in rows if r["regime"] == regime]
        unsupported = sum(1 for r in subset if r["unsupported"])
        completed = sum(1 for r in subset if r["from_cut_text"])
        headline(
            f"{regime}: answers asserting a dose the excerpt does not contain",
            pct(unsupported, len(subset)),
            "The value is provably not in the text the model was handed.",
        )
        headline(
            f"{regime}: of those, values matching the text the cut removed",
            pct(completed, unsupported) if unsupported else "n/a",
            "Not invented — completed. The model finished the sentence the cut "
            "started.",
        )
        headline(
            f"{regime}: answers that declined to give a dose",
            pct(sum(1 for r in subset if r["declined"]), len(subset)),
            "The correct outcome for every one of these.",
        )
        headline(
            f"{regime}: declined in the schema field, asserted in the prose",
            pct(sum(1 for r in subset if r["declined"] and r["unsupported"]), len(subset)),
            "The `dose` field is null and the answer text states doses that are "
            "not in the excerpt. A check reading the field passes it.",
        )

    control = [r for r in rows if r["regime"] == "CONTROL"]
    headline(
        "CONTROL: recall where the subsection is complete under both policies",
        pct(sum(1 for r in control if r["recalled"]), len(control)),
        "The counter-metric. A truncation policy that answers nothing is not a "
        "fix, and this is the number that would show it.",
    )
    discarded = [r["discarded"] for r in rows]
    headline(
        "Characters discarded by the cut policy, mean per call",
        f"{sum(discarded) / max(len(discarded), 1):.0f}",
        "What the policy costs in context.",
    )
