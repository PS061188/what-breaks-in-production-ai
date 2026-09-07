"""Chapter 9, the fix — on a corpus where the check can actually be wrong.

Why this file exists
--------------------
`fixed.py` reports 0% fabrication and that number is worthless. A review proved
it by enumeration: every field is supplied *or* not supplied uniformly across the
corpus, so "can this field's quote come from a permitted section" is bit-for-bit
identical to the ground-truth predicate. The check could not have failed on any
document, any model, any temperature. It was the answer key wearing a filter's
clothes.

The design flaw was in the corpus, not the idea. Fix the corpus and the idea
becomes testable.

What changed
------------
Four sections are now supplied instead of two — indications, dosage, paediatric
use, and drug interactions — **but only when the label actually has them**:

    pediatric_use       present in  8 of 12 labels
    drug_interactions   present in 10 of 12 labels

So `pediatric_dosage` is legitimately answerable for 8 drugs and unanswerable for
4, and the constraint has to *discriminate* rather than reject unconditionally. A
check that nulls everything now scores terribly on recall, and a check that
passes everything scores terribly on fabrication. Neither is free.

Ground truth is still derived and still not authored: a field is answerable
exactly when its supporting section exists in that label.

    python fixed_noncircular.py            # replay
    python fixed_noncircular.py --live     # re-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import is_absent_answer  # noqa: E402
from fixed import SUPPORTING_SECTIONS, SYSTEM  # noqa: E402
from shared.llm import LLM, base_args, load_labels, map_parallel  # noqa: E402
from shared.scoring import headline, pct, quote_supported, rule, table  # noqa: E402

# Four fields; each names the one section that can legitimately answer it.
FIELDS = [
    ("indications", "indications_and_usage"),
    ("adult_dosage", "dosage_and_administration"),
    ("pediatric_dosage", "pediatric_use"),
    ("drug_interactions", "drug_interactions"),
]
FIELD_LIST = ", ".join(name for name, _ in FIELDS)
SUPPLIED = [section for _, section in FIELDS]


def build_cases(limit: int = 0) -> list:
    cases = []
    for label in load_labels():
        # Supply whichever of the four sections this label actually carries.
        texts = {
            name: label["sections"][name][:2400]
            for name in SUPPLIED
            if label["sections"].get(name)
        }
        if "indications_and_usage" not in texts or "dosage_and_administration" not in texts:
            continue
        cases.append(
            {
                "drug": label["drug"],
                "context": "\n\n".join(f"[{n}]\n{t}" for n, t in texts.items()),
                "section_texts": texts,
                # Derived from the label: answerable iff its section is present.
                "present": {field: (section in texts) for field, section in FIELDS},
            }
        )
        if limit and len(cases) >= limit:
            break
    return cases


def schema() -> dict:
    nullable = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    props = {
        name: {
            "type": "object",
            "properties": {
                "value": nullable,
                "source_quote": nullable,
                "source_section": {"type": "string"},
            },
            "required": ["value", "source_quote", "source_section"],
            "additionalProperties": False,
        }
        for name, _ in FIELDS
    }
    return {
        "type": "object",
        "properties": props,
        "required": [name for name, _ in FIELDS],
        "additionalProperties": False,
    }


def enforce(field_name: str, field: dict, case: dict):
    """Locate the quote in the supplied sections; reject if it sits in the wrong one."""
    if field["value"] is None:
        return None, "null"
    if not quote_supported(field["source_quote"], case["context"]):
        return None, "NULLED quote not in document"

    located = None
    for section, text in case["section_texts"].items():
        if quote_supported(field["source_quote"], text):
            located = section
            break

    if located not in SUPPORTING_SECTIONS.get(field_name, set()):
        return None, f"NULLED quote sits in {located or 'no known section'}"
    return field["value"], "kept"


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    def one(case):
        return llm.json(
            system=SYSTEM.format(context=case["context"]),
            user=f"Extract the following fields: {FIELD_LIST}",
            schema=schema(),
            max_tokens=2500,
        )

    results = map_parallel(one, cases)

    rows = []
    fab = absent = recalled = present = nulled = 0
    for case, result in zip(cases, results):
        for name, _ in FIELDS:
            value, reason = enforce(name, result[name], case)
            nulled += int(reason.startswith("NULLED"))
            declined = value is None or is_absent_answer(value)
            if case["present"][name]:
                present += 1
                recalled += int(not declined)
                if declined:
                    rows.append([case["drug"][:18], name, "LOST", reason])
            else:
                absent += 1
                fab += int(not declined)
                if not declined:
                    rows.append([case["drug"][:18], name, "FABRICATED", reason])

    if rows:
        rule("Every case the check got wrong, in either direction")
        table(["drug", "field", "outcome", "why"], rows)

    headline(
        "Fabrication on fields with no supporting section",
        pct(fab, absent),
        f"{absent} such fields across {len(cases)} labels. Unlike the original "
        "design, the check CAN pass here — the supporting sections exist for "
        "other drugs in the same run.",
    )
    headline(
        "Recall on fields that do have a supporting section",
        pct(recalled, present),
        f"{present} such fields. This is what a check that nulls everything "
        "would destroy.",
    )
    headline("Fields nulled by code rather than declined by the model", str(nulled))
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
