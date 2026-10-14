"""Experiment 10.11 — the field enforced through the answer schema.

Prachi's question (14 Oct 2026): does enforcing the field through the answer
schema change what the model writes in it, compared with asking in prompt
words? Two kinds of enforcement exist. Decoder-level enforcement (the API's
structured outputs) constrains generation itself; it needs the paid API and was
not run. Engineering enforcement validates each reply against the schema in
code and sends it back for correction until it conforms. That layer is
deterministic given a reply, and every reply of Experiment 10.7 is recorded, so
the enforced arm is computable by replay: validate all 360, and make a live
correction call only where validation fails.

The strict schema: exactly two keys; "extracted" a list of strings;
"not_extracted" a list of {"text", "reason"} string pairs.

    python3 probe_field_enforce.py           # replay; --live to record a needed correction
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from probe_field_conversation import SYSTEM, USER, call_cli, load_dialogues, parse_json  # noqa: E402

FIXTURES = HERE / "fixtures_field_conversation"
CORRECTIONS = HERE / "fixtures_field_enforce"


def strict_errors(obj) -> list:
    errs = []
    if not isinstance(obj, dict):
        return ["not a JSON object"]
    extra = set(obj) - {"extracted", "not_extracted"}
    if extra:
        errs.append(f"unexpected keys {sorted(extra)}")
    for key in ("extracted", "not_extracted"):
        if not isinstance(obj.get(key), list):
            errs.append(f'"{key}" must be a list')
    for i, e in enumerate(obj.get("extracted") or []):
        if not isinstance(e, str):
            errs.append(f'"extracted"[{i}] must be a string')
    for i, e in enumerate(obj.get("not_extracted") or []):
        if not (isinstance(e, dict) and set(e) == {"text", "reason"}
                and all(isinstance(e[x], str) for x in ("text", "reason"))):
            errs.append(f'"not_extracted"[{i}] must be an object with string "text" and "reason"')
    return errs


def correct(rec: dict, errs: list, dialogue: str, live: bool) -> dict:
    path = CORRECTIONS / f"{rec['split']}__{rec['encounter_id']}__s{rec['sample']}.json"
    if path.exists():
        return json.loads(path.read_text())
    if not live:
        raise FileNotFoundError(f"correction not recorded: {path.name} (run with --live)")
    prompt = (USER.format(dialogue=dialogue)
              + "\n\nYour previous reply was:\n" + rec["result"]
              + "\n\nIt did not match the required schema: " + "; ".join(errs)
              + "\nReturn only the corrected JSON object.")
    out = call_cli(prompt)
    record = {"experiment": "10.11", "encounter_id": rec["encounter_id"], "split": rec["split"],
              "sample": rec["sample"], "errors": errs, "result": out.get("result", ""),
              "parsed": parse_json(out.get("result", "")),
              "models_used": sorted((out.get("modelUsage") or {}).keys()),
              "notional_cost_usd": out.get("total_cost_usd")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1))
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    dialogues = {(d["split"], d["encounter_id"]): d["dialogue"] for d in load_dialogues()}
    for condition, root in [("as-printed", FIXTURES), ("narrowed", FIXTURES / "narrowed")]:
        tally = Counter()
        for sdir in sorted(root.glob("s*")):
            if not sdir.is_dir():
                continue
            for f in sorted(sdir.glob("*.json")):
                rec = json.loads(f.read_text())
                errs = strict_errors(rec.get("parsed"))
                tally["replies"] += 1
                if not errs:
                    tally["conform as generated"] += 1
                    continue
                tally["corrected by enforcement"] += 1
                print(f"\n{condition} s{rec['sample']} {rec['encounter_id']} failed strict validation: {errs}")
                old = rec.get("parsed") or {}
                fix = correct(rec, errs, dialogues[(rec["split"], rec["encounter_id"])], args.live)
                new = fix.get("parsed")
                still = strict_errors(new)
                print(f"  after one correction call: {'conforms' if not still else still}")
                if isinstance(new, dict):
                    def norm(o):
                        return (sorted(map(str, o.get('extracted') or [])),
                                sorted(str(e.get('text', e) if isinstance(e, dict) else e) for e in o.get('not_extracted') or []))
                    print(f"  content before: extracted={norm(old)[0]}")
                    print(f"  content after:  extracted={norm(new)[0]}")
                    print(f"  field before: {norm(old)[1]}")
                    print(f"  field after:  {norm(new)[1]}")
        print(f"{condition}: {dict(tally)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
