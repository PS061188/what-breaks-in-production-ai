"""Chapter 6, engineering fix 2, the alternative the book recommends but never ran.

fix_monitoring.py measures the top-k overlap monitor and finds it catches half
of the weeks a new current label arrives. The chapter then says: if what you
need is a staleness alarm, track the newest `last_verified` date across the
documents each canonical query returns, and alert when it stops advancing.

This script runs that monitor over the same 398 simulated weeks, same top-3,
same corpus, no model calls. Two questions, because "stops advancing" mixes
two different events:

  A. ARRIVAL   does the newest date among the top-3 advance in the week a new
               current label arrives? Recall against the 40 change weeks, false
               alarms against the quiet weeks. Same scoring as the overlap monitor.
  B. STALL     in healthy operation, how many weeks pass between one advance
               and the next? A stall alarm has to wait longer than the longest
               healthy gap or it fires during normal operation; and a stall is
               then invisible for at least that long.

    python fix_monitoring_date.py
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import load_versions, stable_top_k  # noqa: E402
from fix_monitoring import FIRST_MONDAY, LAST_DAY, TOP_K, build_index, weeks  # noqa: E402
from shared import bench  # noqa: E402
from shared.llm import base_args  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

WINDOWS = (4, 13, 26, 52)  # weeks of silence before a stall alarm fires


def main() -> int:
    args = base_args(__doc__).parse_args()
    versions = load_versions()
    by_id = {v["set_id"]: v for v in versions}
    drugs = sorted({v["drug"] for v in versions})
    if args.limit:
        drugs = drugs[: args.limit]
    filings = {
        d: sorted((int(v["effective_time"]), v["set_id"]) for v in versions if v["drug"] == d)
        for d in drugs
    }

    def newest_as_of(drug, when):
        c = [s for t, s in filings[drug] if t <= when]
        return c[-1] if c else None

    with bench.stage("build index"):
        collection = build_index(versions)
    schedule = weeks(FIRST_MONDAY, LAST_DAY)
    cache = {}

    def top_k(drug, monday):
        eligible = len([t for t, _ in filings[drug] if t <= monday])
        key = (drug, eligible)
        if key not in cache:
            r = stable_top_k(collection, f"recommended starting dose of {drug}",
                             {"$and": [{"drug": drug}, {"effective_int": {"$lte": monday}}]}, TOP_K)
            cache[key] = sorted(r["ids"][0])
        return cache[key]

    change_weeks = advanced_on_change = quiet_weeks = advanced_on_quiet = 0
    gaps, rows, missed = [], [], []
    stall_alarms = {w: 0 for w in WINDOWS}
    healthy_weeks = 0

    with bench.stage("weekly queries"):
        for drug in drugs:
            prev_newest_doc, prev_max_date, last_advance_week = None, None, None
            advances, changes, caught, drug_gaps = 0, 0, 0, []
            for idx, monday in enumerate(schedule):
                ids = top_k(drug, monday)
                newest_doc = newest_as_of(drug, monday)
                if newest_doc is None:
                    continue
                max_date = max(int(by_id[i]["effective_time"]) for i in ids)
                if prev_max_date is None:  # first week the drug exists
                    prev_newest_doc, prev_max_date, last_advance_week = newest_doc, max_date, idx
                    continue
                advanced = max_date > prev_max_date
                changed = newest_doc != prev_newest_doc
                if changed:
                    change_weeks += 1; changes += 1
                    advanced_on_change += int(advanced); caught += int(advanced)
                    if not advanced:
                        missed.append([drug[:22], str(monday), "new label filed, newest date among top-3 did not move"])
                else:
                    quiet_weeks += 1
                    advanced_on_quiet += int(advanced)
                if advanced:
                    advances += 1
                    drug_gaps.append(idx - last_advance_week)
                    last_advance_week = idx
                # stall alarms in healthy operation: silence longer than W weeks
                healthy_weeks += 1
                silence = idx - last_advance_week
                for w in WINDOWS:
                    if silence == w:  # fires once per stretch, the week the window is exceeded
                        stall_alarms[w] += 1
                prev_newest_doc, prev_max_date = newest_doc, max_date
            gaps.extend(drug_gaps)
            rows.append([drug[:22], str(changes), str(caught), str(advances),
                         ", ".join(str(g) for g in drug_gaps) or "-"])

    rule(f"A. Arrival: does the newest date among the top-{TOP_K} advance in the week a new current label arrives?")
    table(["drug", "weeks the current label changed", "of those, date advanced", "advances in total", "weeks between advances"], rows)
    if missed:
        table(["drug", "week", "what happened"], missed[:12])
    headline("Change weeks where the newest date advanced", pct(advanced_on_change, change_weeks),
             "Recall, same event and same weeks the overlap monitor was scored on.")
    headline("Quiet weeks where the newest date advanced anyway", pct(advanced_on_quiet, quiet_weeks),
             "False alarms. An older document entering the top-3 cannot move the maximum, so this should be zero.")

    rule("B. Stall: how long does the newest date sit still in healthy operation?")
    if gaps:
        headline("Weeks between one advance and the next, across all drugs",
                 f"shortest {min(gaps)}, median {statistics.median(gaps):.0f}, longest {max(gaps)}",
                 "A stall alarm must wait longer than the longest healthy gap, or it fires when nothing is wrong.")
    for w in WINDOWS:
        headline(f"Stall alarms that would have fired in healthy operation, window {w} weeks",
                 str(stall_alarms[w]),
                 f"and a real stall would go unnoticed for {w} weeks after the last advance")
    print()
    bench.report(f"{len(versions)} documents, {len(cache)} distinct retrievals, {healthy_weeks} drug-weeks, no model calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
