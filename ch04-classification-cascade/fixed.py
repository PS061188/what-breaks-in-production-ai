"""Chapter 4, the fix: three classifiers vote, and the router — not the model —
decides what proceeds.

The four engineering fixes from the chapter, in the book's order:

1. **Confidence-gated routing.** `if confidence != "HIGH": route to review`. The
   check runs in code. The chapter's own line is that a classifier cannot be
   trusted to police its own confidence, so nothing here asks the model whether
   it would like to be reviewed — its `requires_human_review` flag is recorded
   and ignored, and the run reports how often the two would have differed.
2. **Ensemble with majority vote.** Three classifiers over the same passage; the
   majority label wins and a three-way split goes to review. One of the three is
   the baseline's own book-prompt call, byte for byte, so the ensemble's first
   vote is the number broken.py reported rather than a re-run of it.
3. **Per-category F1 gate.** Computed over the labels that shipped, against the
   ground truth derived from the corpus.
4. **Audit trail.** Every record carries its classification, confidence and
   runner-up; the run queries for errors whose runner-up was the true category.

Same output record as broken.py, from `common.blank_row()`. The only difference
between the two scripts is what the router does with it.

    python fixed.py                   # replay the recorded run, free
    python fixed.py --live            # re-run against the API
    python fixed.py --chunk middle    # the harder half of the corpus
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broken import add_chunk_args, banner, positions  # noqa: E402
from common import (  # noqa: E402
    build_cases,
    classify_book,
    classify_heading,
    classify_naive,
    correct,
    report_audit_trail,
    report_cascade,
    report_classification,
    report_f1_gate,
    run_downstream,
)
from shared.llm import LLM, FixtureMissing, base_args, map_parallel  # noqa: E402
from shared.scoring import pct, rule, table  # noqa: E402


class Reuse:
    """Replay a call if the baseline already recorded it; only pay for what is new.

    Two of the three ensemble members are calls broken.py owns. Re-running them
    under --live would re-sample them, and at temperature 1 that moves the
    answer: the same book prompt over the same 96 passages scored 94/96 on one
    run and 93/96 on the next. If fixed.py re-sampled them, the two scripts
    would report different numbers for the same call and the comparison between
    them would be measuring the sampler.

    So fixed.py tries the fixture first and falls back to the API only when
    there is nothing recorded. The ensemble's first two votes are the baseline's
    answers, not a re-run of them. Re-record the chapter with
    `broken.py --live && fixed.py --live`, in that order.
    """

    def __init__(self, chapter_dir: Path, model: str, live: bool):
        self.replay = LLM(chapter_dir, model=model, live=False)
        self.fresh = LLM(chapter_dir, model=model, live=live)

    def __call__(self, fn, *args):
        try:
            return fn(self.replay, *args)
        except FixtureMissing:
            return fn(self.fresh, *args)

    def report(self) -> None:
        self.replay.report("reused from broken.py")
        if self.fresh.calls or self.fresh.replayed:
            self.fresh.report("new to fixed.py")


def vote(rows: list) -> tuple:
    """Majority label, or None when all three members disagree."""
    counts = Counter(r["classification"] for r in rows)
    label, n = counts.most_common(1)[0]
    return (label if n >= 2 else None), n


def route(members: list) -> dict:
    """Fixes 1 and 2, in the order the pipeline applies them.

    `members` is [naive, book, heading]. The book-prompt member is the one
    carrying a confidence grade, so it is the one the gate reads — and it is the
    same call broken.py made.
    """
    naive_row, book_row, heading_row = members
    majority, agreeing = vote(members)

    row = dict(book_row)
    row["classification"] = majority or book_row["classification"]
    row["votes"] = [m["classification"] for m in members]
    row["agreeing"] = agreeing
    # Kept separately so the policy table can score each router against the
    # label *that router would actually have shipped*. An earlier version scored
    # every policy against the ensemble majority, including the row labelled
    # "no gate (baseline)" — which made the baseline look like it had already
    # had fix 2 applied to it, and understated the ensemble by 7 errors on the
    # middle-chunk run. See the README.
    row["naive_label"] = naive_row["classification"]
    row["book_label"] = book_row["classification"]
    row["majority_label"] = majority

    if majority is None:
        row["routed"] = "review"
        row["route_reason"] = "ensemble split three ways"
    elif book_row["confidence"] != "HIGH":
        row["routed"] = "review"
        row["route_reason"] = f"confidence {book_row['confidence']}"
    else:
        row["routed"] = "auto"
        row["route_reason"] = f"{agreeing}/3 agree, HIGH"
    return row


# --- fix 1 + fix 2, evaluated as router policies -----------------------------
#
# Each policy is a pair: which label it would ship, and whether it ships at all.
# All of them are scored from the same recorded votes, so the table compares
# routers rather than runs.

POLICIES = [
    # name, label it ships, does it ship
    ("book prompt alone — broken.py", "book_label", lambda r: True),
    ("naive prompt alone", "naive_label", lambda r: True),
    ("fix 1 — book label, confidence HIGH only", "book_label", lambda r: r["confidence"] == "HIGH"),
    ("fix 2 — ensemble majority", "majority_label", lambda r: r["agreeing"] >= 2),
    (
        "fix 1 + fix 2",
        "majority_label",
        lambda r: r["agreeing"] >= 2 and r["confidence"] == "HIGH",
    ),
    ("strict — unanimous ensemble", "majority_label", lambda r: r["agreeing"] == 3),
]


def report_policies(rows: list) -> None:
    body = []
    for name, label_key, ships in POLICIES:
        shipped = [r for r in rows if ships(r)]
        held = [r for r in rows if not ships(r)]
        wrong_shipped = [r for r in shipped if r[label_key] != r["true_category"]]
        right_held = [r for r in held if r[label_key] == r["true_category"]]
        body.append(
            [
                name,
                pct(len(held), len(rows)),
                pct(len(shipped) - len(wrong_shipped), len(shipped)) if shipped else "n/a",
                str(len(wrong_shipped)),
                str(len(right_held)),
            ]
        )
    table(
        [
            "router policy",
            "sent to review",
            "accuracy of what shipped",
            "wrong labels shipped",
            "correct labels sent to review",
        ],
        body,
    )
    print(
        "\n   The last two columns are the trade. A gate that moves the fourth column "
        "\n   without moving the fifth is free; one that moves both is buying accuracy "
        "\n   with human time, and you need the exchange rate before you ship it."
    )


def report_self_report_gap(rows: list) -> None:
    """Does the confidence grade find the errors it is supposed to find?

    Scored against the **book-prompt label**, because that is the label the
    confidence grade describes. Scoring it against the ensemble majority instead
    would credit the confidence gate with errors the ensemble had already
    removed, which is how a confidence gate comes to look useful in a report
    when it is not.
    """
    flagged = [r for r in rows if r["confidence"] != "HIGH"]
    errors = [r for r in rows if r["book_label"] != r["true_category"]]
    print(f"\n>> Book-prompt labels graded below HIGH: {pct(len(flagged), len(rows))}")
    print(f">> Book-prompt labels that were wrong:   {pct(len(errors), len(rows))}")
    if errors:
        caught = sum(r["confidence"] != "HIGH" for r in errors)
        print(f"\n>> Errors the confidence grade flagged: {pct(caught, len(errors))}")
        print("   Everything else was wrong and stamped HIGH.")
    if flagged:
        wasted = sum(r["book_label"] == r["true_category"] for r in flagged)
        print(f">> Flagged cases that were already right: {pct(wasted, len(flagged))}")
        print("   That is the human-review queue, and that is how much of it is wasted.")
    disagree = sum(
        r["requires_human_review"] != (r["confidence"] in ("MEDIUM", "LOW")) for r in rows
    )
    print(
        f">> requires_human_review disagreed with the model's own confidence on "
        f"{pct(disagree, len(rows))}"
    )


def run_position(args, call, position: str) -> None:
    cases = build_cases(limit=args.limit, position=position)
    banner(position)

    rule(f"Ensemble — three classifiers over {len(cases)} passages (chunk={position})")
    naive_rows = map_parallel(lambda c: call(classify_naive, c), cases)
    book_rows = map_parallel(lambda c: call(classify_book, c), cases)
    heading_rows = map_parallel(lambda c: call(classify_heading, c), cases)

    members = {
        "A — naive prompt": naive_rows,
        "B — book prompt (broken.py's baseline 2)": book_rows,
        "C — heading prompt, reversed options": heading_rows,
    }
    table(
        ["ensemble member", "accuracy on its own"],
        [[name, pct(sum(correct(r) for r in rs), len(rs))] for name, rs in members.items()],
    )

    unanimous = sum(
        len({a["classification"], b["classification"], c["classification"]}) == 1
        for a, b, c in zip(naive_rows, book_rows, heading_rows)
    )
    print(f"\n>> All three members agreed on: {pct(unanimous, len(cases))}")
    print(
        "   An ensemble only pays when its members fail differently. Three prompts "
        "against one model is not three independent classifiers, and this number "
        "says how far from independent they were."
    )

    rows = [
        route([a, b, c]) for a, b, c in zip(naive_rows, book_rows, heading_rows)
    ]

    rule("Fix 1 and fix 2 as router policies, scored on the same votes")
    report_policies(rows)

    rule("What the model would have gated on, versus what the code gated on")
    report_self_report_gap(rows)

    auto = [r for r in rows if r["routed"] == "auto"]
    review = [r for r in rows if r["routed"] == "review"]
    auto_ids = {r["case_id"] for r in auto}

    rule("What shipped — the labels that reached a downstream stage")
    report_classification(auto, [c for c in cases if c["case_id"] in auto_ids])
    print(f"   Sent to human review instead: {pct(len(review), len(rows))}")
    if review:
        table(
            ["drug", "true category", "shipped label", "why held", "was it already right?"],
            [
                [
                    r["drug"][:18],
                    r["true_category"],
                    r["classification"],
                    r["route_reason"],
                    "yes — the queue did not need it" if correct(r) else "no",
                ]
                for r in review
            ],
        )

    report_audit_trail(rows)

    rule("Per-category F1 on the labels that shipped — Chapter 4 fix 3")
    report_f1_gate(auto)

    rule("The cascade, after the gates")
    by_id = {c["case_id"]: c for c in cases}
    auto = map_parallel(lambda r: call(run_downstream, by_id[r["case_id"]], r), auto)
    report_cascade(auto)


def main() -> int:
    args = add_chunk_args(base_args(__doc__)).parse_args()

    call = Reuse(Path(__file__).parent, model=args.model, live=args.live)
    for position in positions(args.chunk):
        run_position(args, call, position)

    call.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
