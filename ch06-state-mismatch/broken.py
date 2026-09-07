"""Chapter 6, the baseline: history truncated at exactly N characters.

This is what "truncate at N tokens" does to a real document. The budget is
derived from the corpus so that it lands between a subsection heading and the
first word underneath it — the mid-fact cut the chapter warns about, in its most
literal form. The model is handed an excerpt that ends:

    ... 2.3 Dosage Adjustment in Patients with Renal Impairment

and is then asked what the dosage adjustment in renal impairment is.

The content under that heading is not in the excerpt. Any dose value in the
answer therefore came from somewhere else, and `common.score()` finds those
values with a regex rather than an opinion.

    python broken.py            # replay the recorded run, free
    python broken.py --live     # re-run against the API
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import build_cases, naive_cut, report, run  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import rule  # noqa: E402


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = build_cases(limit=args.limit)

    rule("Truncation policy: text[:budget] — a hard character cut")
    rows = run(llm, cases, naive_cut)
    report(rows)

    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
