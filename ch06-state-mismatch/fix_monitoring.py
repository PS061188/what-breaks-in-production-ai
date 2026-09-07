"""Chapter 6, engineering fix 2: retrieval freshness monitoring.

The book: *"Run a set of representative canonical queries weekly, record top-k
retrieved document IDs, and alert when overlap with the previous week drops
below 70%. A drop signals that fresh documents are not being ingested or stale
ones are not being expired."*

This runs that monitor for real, week by week, over a corpus whose ingest dates
are real. No model calls — the monitor never asks a model anything, which is
part of why it is worth having.

**How a week is simulated.** Every label version carries the date it was filed.
An index "as of" a Monday is the set of versions filed on or before it, which
one `where` clause expresses exactly. Rebuilding the index 390 times would
measure Chroma, not the monitor.

**What is being checked.** The monitor's claim is that a top-k overlap drop
tells you the index has gone stale. So the weeks are split by a fact derived
from the corpus, not from the monitor: in a given week, did a drug's newest
label change? Those are the weeks the monitor exists to catch. Every other week
is a week it should stay quiet.

    python fix_monitoring.py
"""

import datetime
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import load_versions, stable_top_k  # noqa: E402
from shared import bench  # noqa: E402
from shared.llm import base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

INDEX_DIR = Path(__file__).parent / ".chroma" / "monitor"
TOP_K = 3
ALERT_THRESHOLD = 0.70  # the book's number
FIRST_MONDAY = "20190107"
LAST_DAY = "20260822"


def build_index(versions: list):
    from shared.deps import require

    require("chromadb", "chromadb", "building the retrieval index")
    import chromadb
    from chromadb.config import Settings

    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR)
    client = chromadb.PersistentClient(
        path=str(INDEX_DIR), settings=Settings(anonymized_telemetry=False)
    )
    collection = client.create_collection("freshness_monitor")
    collection.add(
        ids=[v["set_id"] for v in versions],
        documents=[v["text"] for v in versions],
        metadatas=[
            {"drug": v["drug"], "effective_int": int(v["effective_time"])} for v in versions
        ],
    )
    return collection


def weeks(first: str, last: str) -> list:
    fmt = "%Y%m%d"
    day = datetime.datetime.strptime(first, fmt)
    end = datetime.datetime.strptime(last, fmt)
    out = []
    while day <= end:
        out.append(int(day.strftime(fmt)))
        day += datetime.timedelta(days=7)
    return out


def overlap(previous: list, current: list) -> float:
    """Share of last week's top-k that is still in this week's top-k."""
    if not previous:
        return 1.0
    return len(set(previous) & set(current)) / len(set(previous))


def main() -> int:
    args = base_args(__doc__).parse_args()
    versions = load_versions()
    drugs = sorted({v["drug"] for v in versions})
    if args.limit:
        drugs = drugs[: args.limit]

    # Derived from the corpus: for each drug, the newest label as of any date.
    filings = {
        drug: sorted(
            (int(v["effective_time"]), v["set_id"]) for v in versions if v["drug"] == drug
        )
        for drug in drugs
    }

    def newest_as_of(drug: str, when: int):
        candidates = [set_id for time, set_id in filings[drug] if time <= when]
        return candidates[-1] if candidates else None

    with bench.stage("build index"):
        collection = build_index(versions)

    schedule = weeks(FIRST_MONDAY, LAST_DAY)

    rows = []
    per_drug = {}
    true_change = alerted_on_change = 0
    no_change = alerted_on_no_change = 0
    missed_examples = []

    # The retrieval result depends only on which documents exist by that Monday,
    # and that set changes on the eight weeks a label was filed — not on the
    # other 390. Memoising on the eligible set gives the identical answer for
    # 48 queries instead of 2,388, and the difference is 98 seconds.
    cache = {}

    def top_k(drug: str, monday: int) -> list:
        eligible = len([time for time, _ in filings[drug] if time <= monday])
        key = (drug, eligible)
        if key not in cache:
            # `stable_top_k`, not `collection.query`. An approximate index that
            # picks differently between two near-identical documents would make
            # this monitor alert on churn that never happened, which is a worse
            # failure than the one it is looking for.
            result = stable_top_k(
                collection,
                f"recommended starting dose of {drug}",
                {"$and": [{"drug": drug}, {"effective_int": {"$lte": monday}}]},
                TOP_K,
            )
            cache[key] = sorted(result["ids"][0])
        return cache[key]

    with bench.stage("weekly queries"):
        for drug in drugs:
            previous_ids, previous_newest = [], None
            drug_alerts = drug_changes = drug_caught = 0
            for monday in schedule:
                current_ids = top_k(drug, monday)
                current_newest = newest_as_of(drug, monday)
                if previous_newest is None and current_newest is None:
                    continue

                score = overlap(previous_ids, current_ids)
                alerted = score < ALERT_THRESHOLD
                changed = (
                    previous_newest is not None and current_newest != previous_newest
                )

                if previous_ids:
                    drug_alerts += int(alerted)
                    if changed:
                        true_change += 1
                        drug_changes += 1
                        alerted_on_change += int(alerted)
                        drug_caught += int(alerted)
                        if not alerted:
                            missed_examples.append(
                                [drug[:22], str(monday), f"{score:.0%}", "new label, no alert"]
                            )
                    else:
                        no_change += 1
                        alerted_on_no_change += int(alerted)

                previous_ids, previous_newest = current_ids, current_newest
            per_drug[drug] = (drug_changes, drug_caught, drug_alerts)

    for drug in drugs:
        changes, caught, alerts = per_drug[drug]
        rows.append([drug[:22], str(changes), str(caught), str(alerts)])

    rule(
        f"{len(schedule)} weekly runs per drug, top-{TOP_K}, "
        f"alert when overlap < {ALERT_THRESHOLD:.0%}"
    )
    table(
        ["drug", "weeks the current label changed", "of those, alerted", "total alerts"],
        rows,
    )

    if missed_examples:
        rule("Weeks where the current label changed and the monitor stayed quiet")
        table(["drug", "week", "top-k overlap", "what happened"], missed_examples[:12])

    headline(
        "Weeks where a new current label arrived and the monitor alerted",
        pct(alerted_on_change, true_change),
        "This is the monitor's recall against the event it exists to detect.",
    )
    headline(
        "Weeks where nothing changed and the monitor alerted anyway",
        pct(alerted_on_no_change, no_change),
        "False alarms.",
    )
    headline(
        "Weeks with no alert at all",
        pct(
            (true_change - alerted_on_change) + (no_change - alerted_on_no_change),
            true_change + no_change,
        ),
        "A monitor that is quiet 99% of the time is a monitor nobody checks the "
        "wiring of. The failure it cannot see is an index that stopped ingesting "
        "— which looks exactly like a quiet week.",
    )

    print()
    bench.report(f"{len(versions)} documents, {len(cache)} distinct retrievals covering {len(schedule) * len(drugs)} weekly runs, no model calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
