"""Does asking the same question several times expose fabrication?

Every grounding fix in this chapter compares the model's answer to a source it
was given. That leaves nothing to compare against when there is no source.
Self-consistency is the usual proposal for that case: sample the same prompt
N times and treat disagreement between the draws as the signal, since a model
reciting something it knows tends to repeat it and a model inventing tends to
invent differently each time.

This probe measures the cheapest version of that idea on the chapter's own
corpus, where the ground truth is already known — so the signal can be scored
rather than assumed. The plain instruction (no grounding rules at all) is put
to each question N times, each draw is classified by the same judge the chapter
uses, and the question is: how often do the N draws disagree with each other,
and how often would a single draw have given the wrong impression?

Two numbers matter. The first is how many unanswerable questions a single draw
called safe that fabricated on a later draw — those are the cases resampling
catches that one production call cannot. The second is how many fabricated on
every draw — those are the cases resampling can never catch, because a
confident, repeatable invention is indistinguishable from a recalled fact
without a source to check against.

    python3 probe_selfconsistency.py             # replay committed fixtures
    python3 probe_selfconsistency.py --live      # record, about $1.85 at N=5
    python3 probe_selfconsistency.py --samples 3 --limit 4 --live
"""

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broken import NEUTRAL, SCHEMA  # noqa: E402
from common import build_cases, judge_asserted  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import headline, note, pct, rule, table  # noqa: E402


def main() -> int:
    parser = base_args(__doc__)
    parser.add_argument("--samples", type=int, default=5, help="draws per question (default 5)")
    args = parser.parse_args()
    n = args.samples

    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    # The chapter's scorable set: contaminated questions are answerable from
    # the supplied text after all, so an assertion there is not fabrication.
    cases = [c for c in build_cases(limit=args.limit) if not c.get("contaminated")]

    jobs = [(case, i) for case in cases for i in range(1, n + 1)]

    def one(job):
        case, i = job
        result = llm.json(
            system=NEUTRAL.format(context=case["context"]),
            user=case["question"],
            schema=SCHEMA,
            max_tokens=800,
            sample=i,  # nonzero: each draw gets its own fixture, never a replay of the last
        )
        return result["answer"], judge_asserted(llm, case["question"], result["answer"])

    draws = collections.defaultdict(list)
    for (case, i), (answer, asserted) in zip(jobs, map_parallel(one, jobs)):
        draws[id(case)].append((i, asserted, answer))

    rows = []
    unans = {"always_declines": 0, "always_fabricates": 0, "split": 0, "missed_by_first_draw": 0}
    ans = {"always_answers": 0, "declined_on_some_draw": 0}
    split_examples = []

    for case in cases:
        seq = sorted(draws[id(case)])
        k = sum(1 for _, a, _ in seq if a)
        first_asserted = seq[0][1]
        if case["answerable"]:
            if k == n:
                ans["always_answers"] += 1
                verdict = "answered every draw"
            else:
                ans["declined_on_some_draw"] += 1
                verdict = f"declined on {n - k} of {n}"
        else:
            if k == 0:
                unans["always_declines"] += 1
                verdict = "declined every draw"
            elif k == n:
                unans["always_fabricates"] += 1
                verdict = "FABRICATED every draw"
            else:
                unans["split"] += 1
                verdict = f"SPLIT: fabricated on {k} of {n}"
                if len(split_examples) < 2:
                    split_examples.append((case, seq))
            if not first_asserted and k > 0:
                unans["missed_by_first_draw"] += 1
        rows.append(
            [
                case["drug"][:22],
                case["needed_section"],
                "answerable" if case["answerable"] else "NOT in context",
                "".join("A" if a else "." for _, a, _ in seq),
                verdict,
            ]
        )

    rule(f"Per question — {n} draws each, plain instruction (A = asserted an answer, . = declined)")
    table(["drug", "section needed", "ground truth", "draws", "verdict"], rows)

    for case, seq in split_examples:
        rule(f"A split question, all {n} draws — {case['drug']}: {case['question']}")
        for i, a, answer in seq:
            tag = "ASSERTED" if a else "declined"
            print(f"  draw {i} [{tag}]  {answer[:150].replace(chr(10), ' ')}")

    n_un = sum(1 for c in cases if not c["answerable"])
    n_an = len(cases) - n_un

    rule("Summary")
    headline(
        f"Unanswerable questions where the {n} draws disagree with each other",
        pct(unans["split"], n_un),
        "On these, whether the model fabricates depends on the draw. One production "
        "call tells you nothing reliable about the next.",
    )
    headline(
        "Unanswerable questions a single draw called safe that fabricated on retry",
        pct(unans["missed_by_first_draw"], n_un),
        "The first draw declined; at least one later draw invented an answer. "
        "These are what resampling catches and a single call cannot.",
    )
    headline(
        "Unanswerable questions that fabricated on every draw",
        pct(unans["always_fabricates"], n_un),
        "Consistent invention. Without a source to check against, this is "
        "indistinguishable from a recalled fact — resampling cannot see it.",
    )
    headline(
        "Answerable questions that declined on at least one draw",
        pct(ans["declined_on_some_draw"], n_an),
        "The recall side of the same instability.",
    )
    note(
        f"{unans['always_declines']} of {n_un} unanswerable questions declined on every "
        f"draw. The plain instruction fabricates on 11% of single draws; across {n} draws "
        f"the share of questions it fabricated on at least once is "
        f"{pct(unans['split'] + unans['always_fabricates'], n_un)}."
    )
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
