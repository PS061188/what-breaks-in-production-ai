"""Chapter 9, the fix: a licensed empty state, then a check that enforces it.

Three changes, in order of how much they matter:

1. The schema lets a field be null, and there is no default value. Nothing
   downstream needs a string.
2. The prompt says returning null is the correct answer for a field with no
   source content, and requires a quotable source for anything else.
3. After the call, every source_quote is checked against the document with
   fuzzy matching. A field whose quote is not in the document is set to null
   before it is stored — whatever the model claimed.

Step 3 is the one that survives a model swap. Run with --model claude-opus-5
and the first two do more of the work; the check does not care either way.

    python fixed.py             # replay the recorded run, free
    python fixed.py --live      # re-run against the API
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import FIELD_LIST, FIELDS, build_cases, is_absent_answer  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, note, pct, quote_supported, rule, table  # noqa: E402

# Adapted from the Chapter 9 prompt template.
SYSTEM = """You are an extraction assistant. Your ONLY job is to extract what is
explicitly present in the source document. You are NOT a writer, summariser, or
content generator.

SPARSE FIELD PROTOCOL — THE MOST IMPORTANT RULE:
If a field's information is not clearly present in the source text:
  - Return null for that field. Do NOT invent, infer, or approximate.
  - Do NOT use "common sense" to fill in what "probably" belongs.
  - A null field is a correct answer, not a failure.

BEFORE FILLING ANY FIELD, ask yourself:
  "Can I quote the source text that justifies this value?"
  If NO  -> return null.
  If YES -> include "source_quote" copied exactly from the document.

FABRICATION PATTERNS TO AVOID:
Do not use phrases like "as needed", "per standard protocol", "to be determined"
or "N/A" unless those exact words appear in the source. These are fabrication
indicators. Return null instead.

If value is null, source_quote must also be null.
source_section must name the [section] header the quote was taken from, exactly
as it appears in the document. Use "none" when the value is null.

<source_document>
{context}
</source_document>"""

# Which section of a label can support which field. This is the part a team has
# to decide; the model is never told it. Chapter 3's prevention rule — label a
# piece of content with its source when it enters the pipeline, and carry that
# label — is what makes the check below possible at all.
SUPPORTING_SECTIONS = {
    "indications": {"indications_and_usage"},
    "adult_dosage": {"dosage_and_administration"},
    "pediatric_dosage": {"pediatric_use"},
    "pregnancy_guidance": {"pregnancy"},
    "overdose_management": {"overdosage"},
    "drug_interactions": {"drug_interactions"},
}


def schema() -> dict:
    nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    props = {
        name: {
            "type": "object",
            "properties": {
                "value": nullable_string,
                "source_quote": nullable_string,
                # Plain string, not nullable: the API caps a schema at 16
                # union-typed parameters and six fields x three nullables is 18.
                # "none" is the sentinel, and the enforcement below treats it
                # like any other section that cannot support the field.
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


def enforce(name: str, field: dict, case: dict):
    """Three checks, none of which asks the model's permission.

    The third one is the one this corpus needs. A quote can be real and still
    not support the field it was attached to — pediatric dosing pulled out of
    the indications section is a quote that verifies perfectly. That is
    Chapter 3's source-tracking failure showing up inside Chapter 9's fix, and
    quote existence alone does not catch it.

    Note *how* the third check establishes the section. An earlier version
    trusted the `source_section` the model reported. Chapter 8 then measured how
    often that self-report is wrong — about one time in five — so this locates
    the quote in each section independently and uses where it was actually
    found. The model's claim is recorded and compared, never relied upon.
    """
    if field["value"] is None:
        return None, "null"

    context = case["context"]
    if not quote_supported(field["source_quote"], context):
        return None, "NULLED quote not in document"

    located = None
    for section, text in case["section_texts"].items():
        if quote_supported(field["source_quote"], text):
            located = section
            break

    allowed = SUPPORTING_SECTIONS.get(name, set())
    if located not in allowed:
        return None, f"NULLED quote sits in {located or 'no known section'}, not a supporting one"

    return field["value"], "kept"


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    rows = []
    fabricated = absent_total = 0
    covered_total = covered_filled = 0
    recalled = present_total = 0
    nulled_by_code = 0
    null_counts = {name: 0 for name, _ in FIELDS}
    field_totals = {name: 0 for name, _ in FIELDS}

    for case in cases:
        result = llm.json(
            system=SYSTEM.format(context=case["context"]),
            user=f"Extract the following fields: {FIELD_LIST}",
            schema=schema(),
            max_tokens=2000,
        )
        for name, _ in FIELDS:
            value, reason = enforce(name, result[name], case)
            nulled_by_code += int(reason.startswith("NULLED"))
            field_totals[name] += 1
            null_counts[name] += int(value is None)

            declined = value is None or is_absent_answer(value)

            if case["present"][name]:
                present_total += 1
                recalled += int(not declined)
            elif case["covered_anyway"][name]:
                covered_total += 1
                covered_filled += int(not declined)
                rows.append(
                    [
                        case["drug"][:20],
                        name,
                        "covered anyway" if not declined else "declined",
                        reason,
                        str(result[name]["value"] or "")[:44].replace("\n", " "),
                    ]
                )
            else:
                absent_total += 1
                fabricated += int(not declined)
                rows.append(
                    [
                        case["drug"][:20],
                        name,
                        "FABRICATED" if not declined else "declined",
                        reason,
                        str(result[name]["value"] or "")[:44].replace("\n", " "),
                    ]
                )

    rule("Fields with no source content (the correct answer is nothing)")
    table(["drug", "field", "outcome", "code check", "model's value (first 44)"], rows)

    rule("Null rate per field — Chapter 9's monitoring signal")
    table(
        ["field", "null rate", "expected"],
        [
            [
                name,
                pct(null_counts[name], field_totals[name]),
                "high (no source section)"
                if section not in ("indications_and_usage", "dosage_and_administration")
                else "low (section supplied)",
            ]
            for name, section in FIELDS
        ],
    )

    headline(
        "Fabrication rate on fields the document does not cover",
        pct(fabricated, absent_total),
        "Compare with broken.py.",
    )
    note(
        f"{covered_total} field-instances are excluded from that denominator: their "
        "section was withheld, but its topic carries its own heading inside the "
        f"supplied text. The model filled {covered_filled} of {covered_total}."
    )
    headline(
        "Recall on fields the document does cover",
        pct(recalled, present_total),
        "The number that stops you from declaring victory by nulling everything.",
    )
    headline(
        "Fields nulled by the code checks rather than by the model",
        str(nulled_by_code),
        "These are the ones the prompt alone would have stored.",
    )
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
