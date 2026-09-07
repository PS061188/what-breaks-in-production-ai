"""Download the drug-label corpus used by every chapter.

Source: openFDA (https://open.fda.gov/apis/drug/label/), a public-domain US
government API serving the SPL text of FDA-approved drug labels.

The repo ships a snapshot at data/labels.json so nothing here needs to run.
Re-run it to refresh the corpus or to swap in different drugs:

    python fetch_data.py                 # rewrite data/labels.json
    python fetch_data.py --show          # print field coverage for the snapshot

Labels change over time. Refreshing may change the measured numbers, which is
the point: the fixtures record what the model did against the corpus you had.
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.fda.gov/drug/label.json"

# One label per drug, chosen for a spread of section coverage: some carry a
# pediatric or pregnancy section, some do not. The gaps are what Chapter 9
# measures, so they are load-bearing, not incidental.
DRUGS = [
    "Prednisone",
    "Lisinopril",
    "Metformin Hydrochloride",
    "Atorvastatin Calcium",
    "Levothyroxine Sodium",
    "Amoxicillin",
    "Sertraline Hydrochloride",
    "Warfarin Sodium",
    "Albuterol Sulfate",
    "Gabapentin",
    "Furosemide",
    "Omeprazole",
]

# Sections the chapters read. Anything not in this list is dropped so the
# snapshot stays small and the field set is stable across refreshes.
KEEP = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings",
    "precautions",
    "adverse_reactions",
    "drug_interactions",
    "pediatric_use",
    "geriatric_use",
    "pregnancy",
    "nursing_mothers",
    "overdosage",
    "how_supplied",
    "description",
]

DATA = Path(__file__).resolve().parent / "data" / "labels.json"
VERSIONS = Path(__file__).resolve().parent / "data" / "label_versions.json"

# For the version-locked retrieval demo: the same drug, labelled by many
# repackagers over several years. openFDA carries hundreds of these per generic
# with real, widely-spread effective_time values — so "an old version of the
# document is still in the index" needs no synthetic data.
VERSION_DRUGS = ["Lisinopril", "Metformin Hydrochloride", "Prednisone",
                 "Furosemide", "Gabapentin", "Sertraline Hydrochloride"]
VERSIONS_PER_DRUG = 8


def fetch_one(brand: str) -> dict:
    query = urllib.parse.quote(f'openfda.brand_name:"{brand}"')
    url = f"{API}?search={query}&limit=1"
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.load(resp)
    result = payload["results"][0]

    label = {
        "drug": brand,
        "set_id": result.get("set_id"),
        "effective_time": result.get("effective_time"),
        "sections": {},
    }
    for field in KEEP:
        if field in result:
            # openFDA returns each section as a list of strings; join them so
            # downstream code sees one block of text per section.
            text = "\n\n".join(result[field]).strip()
            if text:
                label["sections"][field] = text
    return label


def fetch_versions(brand: str, limit: int) -> list:
    """Several real labels for one drug, spread across years."""
    query = urllib.parse.quote(f'openfda.brand_name:"{brand}"')
    url = f"{API}?search={query}&limit={limit}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.load(resp)

    out = []
    for result in payload["results"]:
        text = "\n\n".join(result.get("dosage_and_administration", [])).strip()
        if not text or not result.get("effective_time"):
            continue
        out.append(
            {
                "drug": brand,
                "set_id": result.get("set_id"),
                "effective_time": result["effective_time"],
                "labeler": (result.get("openfda", {}).get("manufacturer_name") or ["unknown"])[0],
                "text": text[:2500],
            }
        )
    if not out:
        return []

    # The newest label for a drug is the live one; everything older is a
    # version still sitting in the index. This is the only derived field, and
    # it is derived from the labels' own dates.
    newest = max(v["effective_time"] for v in out)
    for version in out:
        version["status"] = "ACTIVE" if version["effective_time"] == newest else "SUPERSEDED"
        version["age_days"] = _days_between(version["effective_time"], newest)
    return out


def _days_between(older: str, newer: str) -> int:
    from datetime import datetime

    fmt = "%Y%m%d"
    return (datetime.strptime(newer, fmt) - datetime.strptime(older, fmt)).days


def build_versions() -> int:
    versions = []
    for brand in VERSION_DRUGS:
        try:
            found = fetch_versions(brand, VERSIONS_PER_DRUG)
            versions.extend(found)
            print(f"fetched {len(found)} versions of {brand}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"skipped {brand}: {exc}", file=sys.stderr)
        time.sleep(0.4)

    VERSIONS.parent.mkdir(parents=True, exist_ok=True)
    VERSIONS.write_text(
        json.dumps(
            {
                "source": "openFDA drug/label API (public domain, US FDA)",
                "retrieved": time.strftime("%Y-%m-%d"),
                "note": "status is derived: newest effective_time per drug is ACTIVE",
                "versions": versions,
            },
            indent=2,
        )
    )
    stale = [v for v in versions if v["status"] == "SUPERSEDED"]
    oldest = max((v["age_days"] for v in stale), default=0)
    print(
        f"wrote {len(versions)} label versions ({len(stale)} superseded, "
        f"oldest {oldest} days behind its drug's current label)",
        file=sys.stderr,
    )
    return 0


def show(labels: list) -> None:
    print(f"{'drug':<28} {'sections':>8}  missing")
    for label in labels:
        missing = [f for f in KEEP if f not in label["sections"]]
        print(f"{label['drug']:<28} {len(label['sections']):>8}  {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", action="store_true", help="print coverage, download nothing")
    parser.add_argument(
        "--versions",
        action="store_true",
        help="build data/label_versions.json for the version-locked retrieval demo",
    )
    args = parser.parse_args()

    if args.show:
        show(json.loads(DATA.read_text())["labels"])
        return 0

    if args.versions:
        return build_versions()

    labels = []
    for brand in DRUGS:
        try:
            labels.append(fetch_one(brand))
            print(f"fetched {brand}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - a missing drug is not fatal
            print(f"skipped {brand}: {exc}", file=sys.stderr)
        time.sleep(0.4)  # openFDA rate-limits unauthenticated callers

    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(
        json.dumps(
            {
                "source": "openFDA drug/label API (public domain, US FDA)",
                "retrieved": time.strftime("%Y-%m-%d"),
                "labels": labels,
            },
            indent=2,
        )
    )
    print(f"wrote {len(labels)} labels to {DATA}", file=sys.stderr)
    show(labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
