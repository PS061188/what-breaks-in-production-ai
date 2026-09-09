"""Why does the model never issue the bottom grade?

Chapter 2 records that `confidence_to_proceed` came back LOW zero times and
`input_quality` came back SEVERELY_CORRUPTED zero times, and concludes the abort
branch was unreachable. That is an observation, not an explanation, and there are
three candidate reasons. This separates them.

  A  grade + consequence   the chapter's prompt: the bottom grade triggers an abort
  B  grade only            identical wording, with the abort instruction removed
  C  destroyed input       the same prompt as A, over documents that are genuinely
                           unusable rather than merely damaged

If B produces bottom grades and A does not, the consequence was suppressing the
grade. If neither does, the scale itself is the problem. If C produces them, the
grade is reachable and the corpus was simply never severe enough - which would
make the chapter's "unreachable" claim too strong.

    python3 why_no_low.py --live
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

REPORT = """You are an extraction engine. Before extracting any data you must
inspect the input and report its condition.

Scan for corruption signals: characters that do not belong in an English
document, garbled sequences indicating an encoding fault, words with digits
welded into them or letter pairs a scanner confuses, and text that stops
mid-sentence.

Then return:
{
  "input_quality": "CLEAN | DEGRADED | SEVERELY_CORRUPTED",
  "confidence_to_proceed": "HIGH | MEDIUM | LOW",
  "starting_dose": "<the starting dose, or null>"
}
"""

WITH_CONSEQUENCE = REPORT + """
If input_quality is SEVERELY_CORRUPTED or confidence_to_proceed is LOW, do NOT
attempt extraction: return null for starting_dose and stop.

<text>
{text}
</text>"""

GRADE_ONLY = REPORT + """
Grade the document on its own terms. Extract the dose in every case regardless
of the grade you assign; the grade is recorded, not acted on.

<text>
{text}
</text>"""

SCHEMA = {
    "type": "object",
    "properties": {
        "input_quality": {"type": "string",
                          "enum": ["CLEAN", "DEGRADED", "SEVERELY_CORRUPTED"]},
        "confidence_to_proceed": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "starting_dose": {"type": ["string", "null"]},
    },
    "required": ["input_quality", "confidence_to_proceed", "starting_dose"],
    "additionalProperties": False,
}


def destroy(text: str) -> str:
    """Genuinely unusable, not merely damaged: mojibake over 10% of the text."""
    keep = text[: max(120, int(len(text) * 0.10))]
    return keep.encode("utf-8").decode("latin-1", errors="replace")


def run(llm, system, cases, label):
    outs = map_parallel(
        lambda c: llm.json(system=system.replace("{text}", c["text"]),
                           user="Report the condition, then the dose.",
                           schema=SCHEMA, max_tokens=900),
        cases,
    )
    q = [o["input_quality"] for o in outs]
    c = [o["confidence_to_proceed"] for o in outs]
    return [label, len(cases),
            f"{q.count('CLEAN')}/{q.count('DEGRADED')}/{q.count('SEVERELY_CORRUPTED')}",
            f"{c.count('HIGH')}/{c.count('MEDIUM')}/{c.count('LOW')}",
            q.count("SEVERELY_CORRUPTED") + c.count("LOW")]


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)
    wrecked = [dict(c, text=destroy(c["text"])) for c in cases if c["mode"] != "clean"]

    rows = [run(llm, WITH_CONSEQUENCE, cases, "A  grade + abort consequence"),
            run(llm, GRADE_ONLY, cases, "B  grade only, no consequence"),
            run(llm, WITH_CONSEQUENCE, wrecked, "C  destroyed input, A's prompt")]

    rule("Bottom-grade usage under three conditions")
    table(["condition", "docs", "quality  CLEAN/DEG/SEVERE",
           "confidence  HIGH/MED/LOW", "bottom grades"], rows)

    headline("Bottom grades issued with the abort consequence attached",
             str(rows[0][4]), "The chapter's prompt.")
    headline("Bottom grades issued once the consequence is removed",
             str(rows[1][4]),
             "Identical wording otherwise. A difference here means the model was "
             "avoiding the outcome, not unable to make the judgement.")
    headline("Bottom grades issued on genuinely unusable input",
             str(rows[2][4]),
             "If this is also zero, the bottom of the scale is unreachable in "
             "practice and no prompt should depend on it.")
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
