"""Chapter 2's prompt template, run verbatim against the damaged corpus.

The chapter gives an INPUT QUALITY PROTOCOL: the model inspects its own input
for corruption signals, reports a quality grade and a confidence-to-proceed, and
aborts rather than extracting from a document it judges severely corrupted.

It had never been run. The baseline measured elsewhere in this chapter uses a
plain extraction instruction — a demonstration of the failure, not the chapter's
fix — so the protocol had no number attached to it.

The interesting question is not only whether it catches damage. It is whether
`confidence_to_proceed` ever comes back LOW, because the equivalent construct in
Chapter 4 returned LOW zero times in 192 classifications.

    python3 book_prompt.py            # replay
    python3 book_prompt.py --live     # re-record
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases, validate  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

# Verbatim from the book, reflowed only where the page measure forced a wrap.
SYSTEM = """You are an extraction engine. Before extracting any data, you MUST
perform an input quality check.

INPUT QUALITY PROTOCOL:
Step 1 - Scan the input for these corruption signals:
  - Sequences of garbled characters (e.g., "???", "####", encoding artifacts)
  - Words that are clearly OCR artifacts ("rn" where "m" is expected, "0" for "O")
  - Truncation: text that ends mid-sentence, missing closing brackets, or field
    values that cut off abruptly
  - Required fields that are entirely absent from the input

Step 2 - Report your quality assessment BEFORE extraction:
{
  "input_quality": "CLEAN | DEGRADED | SEVERELY_CORRUPTED",
  "corruption_signals": ["list each signal found, or empty array if none"],
  "missing_required_fields": ["field names that appear absent"],
  "confidence_to_proceed": "HIGH | MEDIUM | LOW"
}

Step 3 - If input_quality is SEVERELY_CORRUPTED or confidence_to_proceed is LOW:
Do NOT attempt extraction. Return:
{ "status": "EXTRACTION_ABORTED", "reason": "<specific reason>" }

Step 4 - If proceeding, extract the starting dose. For any field where the source
text is ambiguous due to corruption, annotate with:
  "field_confidence": "LOW", "raw_source": "<exact corrupted text>"

<text>
{text}
</text>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "input_quality": {"type": "string",
                          "enum": ["CLEAN", "DEGRADED", "SEVERELY_CORRUPTED"]},
        "corruption_signals": {"type": "array", "items": {"type": "string"}},
        "confidence_to_proceed": {"type": "string",
                                  "enum": ["HIGH", "MEDIUM", "LOW"]},
        "status": {"type": "string", "enum": ["PROCEEDED", "EXTRACTION_ABORTED"]},
        "starting_dose": {"type": ["string", "null"]},
    },
    "required": ["input_quality", "corruption_signals", "confidence_to_proceed",
                 "status", "starting_dose"],
    "additionalProperties": False,
}


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    # 700 was not enough: on some damaged documents the model returns a long
    # corruption_signals list and the response is cut off mid-JSON. Intermittent,
    # so it survived two clean runs before appearing.
    results = map_parallel(
        lambda c: llm.json(system=SYSTEM.replace("{text}", c["text"]),
                           user="Report the input quality, then the starting dose.",
                           schema=SCHEMA, max_tokens=1400),
        cases,
    )

    clean = [(c, r) for c, r in zip(cases, results) if c["mode"] == "clean"]
    damaged = [(c, r) for c, r in zip(cases, results) if c["mode"] != "clean"]

    flagged = lambda r: r["input_quality"] != "CLEAN"          # noqa: E731
    aborted = lambda r: r["status"] == "EXTRACTION_ABORTED"    # noqa: E731

    rule("Chapter 2's prompt, by damage type")
    modes = sorted({c["mode"] for c, _ in damaged})
    table(
        ["damage", "flagged as not CLEAN", "aborted", "said LOW confidence"],
        [[m,
          pct(sum(1 for c, r in damaged if c["mode"] == m and flagged(r)),
              sum(1 for c, _ in damaged if c["mode"] == m)),
          pct(sum(1 for c, r in damaged if c["mode"] == m and aborted(r)),
              sum(1 for c, _ in damaged if c["mode"] == m)),
          pct(sum(1 for c, r in damaged if c["mode"] == m
                  and r["confidence_to_proceed"] == "LOW"),
              sum(1 for c, _ in damaged if c["mode"] == m))]
         for m in modes],
    )

    headline("Damaged documents the prompt flagged as not CLEAN",
             pct(sum(1 for _, r in damaged if flagged(r)), len(damaged)),
             "The code gate stopped 85% of these, for no model call at all.")
    headline("Damaged documents the prompt refused to extract from",
             pct(sum(1 for _, r in damaged if aborted(r)), len(damaged)),
             "Flagging is not refusing. Step 3 only fires on SEVERELY_CORRUPTED "
             "or LOW confidence.")
    headline("Clean documents wrongly flagged",
             pct(sum(1 for _, r in clean if flagged(r)), len(clean)),
             "The gate's equivalent cost was 17%.")
    headline("Times confidence_to_proceed came back LOW",
             pct(sum(1 for _, r in zip(cases, results)
                     if r["confidence_to_proceed"] == "LOW"), len(cases)),
             "Chapter 4's three-level self-report returned LOW zero times in 192 "
             "classifications. This is the same construct.")

    both = sum(1 for c, r in damaged if flagged(r) and validate(c["text"]))
    only_prompt = sum(1 for c, r in damaged if flagged(r) and not validate(c["text"]))
    only_gate = sum(1 for c, r in damaged if not flagged(r) and validate(c["text"]))
    neither = sum(1 for c, r in damaged if not flagged(r) and not validate(c["text"]))
    rule("Prompt against the code gate, on the same 41 damaged documents")
    table(["caught by", "count"],
          [["both", both], ["prompt only", only_prompt],
           ["code gate only", only_gate], ["neither", neither]])

    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
