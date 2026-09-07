"""Chapter 6, the fix: truncate at the last semantic boundary before the budget.

The chapter: *"Instead of naively truncating conversation history at N tokens,
identify natural breakpoints (topic shifts, intent changes) before truncating
... preventing mid-fact truncation where a key piece of context is cut off
mid-sentence."*

The boundaries used here are the document's own: a subsection heading is a topic
shift, a sentence end is the weaker fallback. `boundary_cut` takes whichever is
closest to the budget without exceeding it. At the NEAR budget that removes the
dangling heading — the model is left with no cue that the topic exists, rather
than with a cue and no content.

Everything else is identical to broken.py. Same cases, same budgets, same
prompt, same schema, same scorers — `run()` and `report()` live in common.py so
the two scripts cannot drift. The only difference is the function passed in.

    python fixed.py             # replay the recorded run, free
    python fixed.py --live      # re-run against the API
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import boundary_cut, build_cases, report, run  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import rule  # noqa: E402


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    rule("Truncation policy: back off to the last topic or sentence boundary")
    rows = run(llm, cases, boundary_cut)
    report(rows)

    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
