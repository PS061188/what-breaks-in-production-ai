"""Does the model's own token probability separate fabricated answers from real ones?

Chapter 4 showed that asking a model to rate its confidence is worthless: LOW
was never issued once in 192 classifications. This probe measures something
mechanically different. Every token a model emits has a probability the model
assigned to it before choosing it. That number is not a self-report — the model
is never asked how sure it is — it is the spread of the distribution it actually
sampled from. The question is whether a fabricated answer is written from a
flatter distribution than a grounded one, and whether any cut on that number
would catch fabrication without also throwing away correct answers.

One hard constraint decides which model this runs on. Anthropic's Messages API
does not expose token log-probabilities at all, so this cannot be measured on
Claude Haiku 4.5, the model every other figure in this chapter comes from. It
runs on GPT-4.1-mini, which returns them on the same call at no extra cost. The
result is therefore an OpenAI-only finding: it cannot confirm or contradict the
Claude numbers, because on that model the signal does not exist to read.

The answer is JSON, and the scaffolding tokens — the braces, the key name, the
quotes — sit at probability one and would flatter any average. Only the tokens
between the opening of the answer value and its close are scored.

    python3 probe_logprobs.py                        # replay committed fixtures
    python3 probe_logprobs.py --live                 # record, about $0.35
    python3 probe_logprobs.py --model gpt-4.1-mini --limit 4 --live
    python3 probe_logprobs.py --live --sample 4       # a fresh run that keeps earlier fixtures
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broken import NEUTRAL, SCHEMA  # noqa: E402
from common import build_cases, judge_asserted  # noqa: E402
from shared.llm import LLM, base_args  # noqa: E402
from shared.scoring import headline, note, pct, rule, table  # noqa: E402

DEFAULT = "gpt-4.1-mini"


def answer_tokens(token_logprobs):
    """Log-probs of the answer's content tokens, scaffolding stripped.

    The output is `{"answer": "..."}`. Everything up to and including the first
    token that carries the colon is scaffolding; so are the closing quote and
    brace. What is left is the text the model actually composed.
    """
    if not token_logprobs:
        return []
    start = 0
    for i, (tok, _) in enumerate(token_logprobs):
        if ":" in tok:
            start = i + 1
            break
    body = token_logprobs[start:]
    while body and body[-1][0].strip() in ('"', "}", '"}', ""):
        body.pop()
    # OpenAI returns -9999.0 as a placeholder for a token it has no probability
    # for. It is not a probability, and one of them drags a 50-token mean to -200.
    return [lp for _, lp in body if lp > -9999.0]


def main() -> int:
    parser = base_args(__doc__)
    parser.set_defaults(model=DEFAULT)
    parser.add_argument(
        "--sample", type=int, default=0,
        help="run index folded into the fixture key, so a fresh --live run does not overwrite the last one",
    )
    args = parser.parse_args()
    if args.model.startswith("claude"):
        raise SystemExit(
            f"{args.model}: Anthropic's API does not expose token log-probabilities. "
            f"Run with --model {DEFAULT} (the default) or another gpt-* model."
        )

    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)
    cases = [c for c in build_cases(limit=args.limit) if not c.get("contaminated")]

    rows = []
    groups = {"fabricated": [], "correct decline": [], "correct answer": [], "missed": []}
    # Sequential on purpose: last_logprobs is read straight after each call.
    for case in cases:
        result = llm.json(
            system=NEUTRAL.format(context=case["context"]),
            user=case["question"],
            schema=SCHEMA,
            max_tokens=800,
            sample=args.sample,
            logprobs=True,
        )
        lps = answer_tokens(llm.last_logprobs)
        if not lps:
            raise RuntimeError(f"No token log-probabilities came back for {case['drug']}")
        mean_lp = statistics.fmean(lps)
        low_lp = sorted(lps)[max(0, len(lps) // 10)]  # 10th percentile: the shakiest stretch
        asserted = judge_asserted(llm, case["question"], result["answer"])

        if case["answerable"]:
            group = "correct answer" if asserted else "missed"
        else:
            group = "fabricated" if asserted else "correct decline"
        groups[group].append((mean_lp, low_lp))
        rows.append(
            [
                case["drug"][:22],
                case["needed_section"],
                group,
                f"{mean_lp:.3f}",
                f"{low_lp:.3f}",
                len(lps),
            ]
        )

    rule(f"Per question — plain instruction on {args.model}, answer tokens only")
    table(["drug", "section needed", "outcome", "mean logprob", "10th pct", "tokens"], rows)

    rule("Average by outcome (closer to 0 = the model was more sure of each token)")
    summary = []
    for name, vals in groups.items():
        if vals:
            summary.append(
                [name, len(vals),
                 f"{statistics.fmean(v[0] for v in vals):.3f}",
                 f"{statistics.fmean(v[1] for v in vals):.3f}"]
            )
    table(["outcome", "n", "mean logprob", "mean 10th pct"], summary)

    fab = [v[0] for v in groups["fabricated"]]
    good = [v[0] for v in groups["correct answer"]]
    if fab and good:
        headline("Mean token log-probability, fabricated answers",
                 f"{statistics.fmean(fab):.3f} (n={len(fab)})")
        headline("Mean token log-probability, correct answers",
                 f"{statistics.fmean(good):.3f} (n={len(good)})")

        # Sweep the cut the way fix_similarity does: a gate that flags anything
        # below t catches fabrications at the cost of correct answers below t.
        rule("Threshold sweep — flag any answer whose mean logprob is below the cut")
        sweep = []
        best = None
        for t in sorted(set(round(x, 2) for x in fab + good)):
            caught = sum(1 for x in fab if x < t)
            false = sum(1 for x in good if x < t)
            sweep.append([f"{t:.2f}", pct(caught, len(fab)), pct(false, len(good))])
            score = caught / len(fab) - false / len(good)
            if best is None or score > best[0]:
                best = (score, t, caught, false)
        table(["cut", "fabrications caught", "correct answers wrongly flagged"], sweep)
        _, t, caught, false = best
        declines = [v[0] for v in groups["correct decline"]]
        declines_flagged = sum(1 for x in declines if x < t)
        headline(
            "Best single cut on mean log-probability",
            f"below {t:.2f}: caught {pct(caught, len(fab))}, flagged {pct(false, len(good))} of correct answers, "
            f"flagged {declines_flagged}/{len(declines)} correct declines",
            "If the two groups overlap, no cut separates them and this is not a gate. "
            "That is a finding, not a tuning problem.",
        )
    else:
        note("Not enough fabricated or correct answers in this run to compare the two groups.")
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
