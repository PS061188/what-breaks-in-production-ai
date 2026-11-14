"""Chapter 4, fix 2 as the chapter actually describes it: three different
systems voting, not three prompts on one model.

Members:
  A  Claude Haiku 4.5, the shipped template (replayed from shipped_prompt.py)
  B  GPT-4.1-mini, the one-line prompt — a second provider
  C  facebook/bart-large-mnli, zero-shot, run locally on CPU — no API at all

C's candidate labels are the category descriptions in common.py ("This text
is about {description}."), the same definitions A and B read in their prompts.
Bare section names ("This text is from the {name} section of a drug label.")
score 41% instead of 59%; ZS_LABELS=names runs that version. The book's
Table 4-2 is the descriptions run.

Majority label wins; when all three disagree the passage goes to review.
Three runs: A and B are sampled three times (A's are already recorded), C is
deterministic and runs once.

    python model_ensemble.py --live            # ~$0.30 for B, plus a 1.6 GB model download
    python model_ensemble.py                   # replay: Table 4-2
    ZS_LABELS=names python model_ensemble.py   # replay with bart on bare names
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import CATEGORIES, NAIVE_SYSTEM, blank_row, build_cases, correct, label_only_schema  # noqa: E402
from shipped_prompt import classify_shipped  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
from shared.scoring import pct, rule, table  # noqa: E402

HERE = Path(__file__).parent
import os
from common import CATEGORY_DESCRIPTIONS  # noqa: E402
DESC = os.environ.get("ZS_LABELS", "descriptions") != "names"
ZS_CACHE = HERE / "fixtures" / ("zeroshot_bart_large_mnli_desc.json" if DESC else "zeroshot_bart_large_mnli.json")
PRETTY = {c: (CATEGORY_DESCRIPTIONS[c] if DESC else c.replace("_", " ")) for c in CATEGORIES}


def classify_gpt(llm, case, sample):
    result = llm.json(system=NAIVE_SYSTEM, user=f"<passage>\n{case['passage']}\n</passage>",
                      schema=label_only_schema(), max_tokens=60, sample=sample)
    row = blank_row(case); row["classification"] = result["classification"]; return row


def zero_shot_rows(cases, live):
    cache = json.loads(ZS_CACHE.read_text()) if ZS_CACHE.exists() else {}
    missing = [c for c in cases if c["case_id"] not in cache]
    if missing:
        if not live:
            raise SystemExit(f"{len(missing)} zero-shot results not recorded; run with --live")
        from transformers import pipeline
        clf = pipeline("zero-shot-classification", model="facebook/bart-large-mnli", device=-1)
        labels = [PRETTY[c] for c in CATEGORIES]
        for k, c in enumerate(missing, 1):
            out = clf(c["passage"][:1800], candidate_labels=labels,
                      hypothesis_template=("This text is about {}." if DESC else "This text is from the {} section of a drug label."))
            best = out["labels"][0]
            cache[c["case_id"]] = next(cat for cat, p in PRETTY.items() if p == best)
            if k % 20 == 0:
                print(f"  zero-shot {k}/{len(missing)}", flush=True)
        ZS_CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))
    rows = []
    for c in cases:
        r = blank_row(c); r["classification"] = cache[c["case_id"]]; rows.append(r)
    return rows


def vote(a, b, c):
    votes = Counter([a["classification"], b["classification"], c["classification"]])
    label, n = votes.most_common(1)[0]
    return (label if n >= 2 else None), n


def main():
    parser = base_args(__doc__)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    haiku = LLM(HERE, model="claude-haiku-4-5", live=args.live)
    gpt = LLM(HERE, model="gpt-4.1-mini", live=args.live)

    for position, label in (("first", "opening passages"), ("middle", "body passages")):
        cases = build_cases(limit=args.limit, position=position)
        rule(f"{label}: {len(cases)} passages")
        zs = zero_shot_rows(cases, args.live)
        out = []
        for k in range(1, args.runs + 1):
            A = map_parallel(lambda c: classify_shipped(haiku, c, k), cases)
            B = map_parallel(lambda c: classify_gpt(gpt, c, k), cases)
            C = zs
            acc = lambda rows: sum(correct(r) for r in rows)
            shipped = review = wrong_shipped = fixed_from_A = 0
            agree3 = sum(1 for a, b, c in zip(A, B, C) if a["classification"] == b["classification"] == c["classification"])
            for a, b, c, case in zip(A, B, C, cases):
                lab, n = vote(a, b, c)
                if lab is None:
                    review += 1; continue
                shipped += 1
                if lab != case["true_category"]:
                    wrong_shipped += 1
                elif a["classification"] != case["true_category"]:
                    fixed_from_A += 1
            out.append([f"run {k}", pct(acc(A), len(A)), pct(acc(B), len(B)), pct(acc(C), len(C)),
                        f"{pct(shipped - wrong_shipped, shipped)} ({shipped - wrong_shipped}/{shipped})",
                        review, wrong_shipped, fixed_from_A, pct(agree3, len(cases))])
        table(["run", "A Haiku shipped", "B GPT-4.1-mini one-line", "C bart zero-shot",
               "ensemble: accuracy of what shipped", "sent to review", "wrong labels shipped",
               "Haiku errors the vote corrected", "all three agreed"], out)
    haiku.report(); gpt.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
