"""Chapter 8, probe: what a strict schema guarantees, measured (Experiment 8.7).

Fix 1 of the chapter says: use structured outputs, or Instructor with a
Pydantic model, so the model cannot invent field names or cross-populate them.
Every run in this repository already enforces a JSON schema (additionalProperties
false), so the fix had never been compared with its absence. This probe does,
on the 60 ACI-Bench notes of probe_clinical.py, with the plain prompt (the four
headings, nothing more). Three conditions, one draw each:

  free       no schema. The prompt asks for JSON with the four keys and the code
             parses whatever comes back.
  schema     the same call with the JSON schema enforced by the API — exactly
             what Experiment 8.6 ran (this condition replays 8.6's first draw).
  validated  schema, then a Pydantic model whose validator requires every
             sentence ID from the input to be filed exactly once and no ID the
             input did not contain. On failure the model is asked again with
             the validation error quoted back, up to two times — the loop that
             the Instructor library automates.

Counted per output: not JSON at all; keys outside the four headings; IDs the
input did not contain; sentences filed under two headings; sentences not filed.
Misplacement is also scored, to show what the schema does not touch.

Usage:
  python probe_schema.py                 # replay
  python probe_schema.py --live missing  # record only what is not recorded yet (~$0.30)
"""

import collections
import json
import re
import sys
from pathlib import Path
from typing import List

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from shared.deps import require  # noqa: E402

require("pydantic", "pydantic", "the schema-validated extraction")
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator  # noqa: E402
from shared.llm import LLM, base_args, map_parallel  # noqa: E402
import probe_clinical as pc  # noqa: E402

RETRIES = 2


class Filing(BaseModel):
    """The four headings, nothing else, and every input sentence exactly once."""

    model_config = ConfigDict(extra="forbid")
    subjective: List[str]
    objective_exam: List[str]
    objective_results: List[str]
    assessment_and_plan: List[str]

    @model_validator(mode="after")
    def exactly_once(self, info):
        expected = set(info.context["ids"])
        filed = [x.strip().upper() for d in pc.DIVISIONS for x in getattr(self, d)]
        counts = collections.Counter(filed)
        dup = sorted(k for k, v in counts.items() if v > 1)
        unknown = sorted(k for k in counts if k not in expected)
        missing = sorted(expected - set(counts))
        problems = []
        if dup:
            problems.append("filed under more than one heading: " + ", ".join(dup))
        if unknown:
            problems.append("not in the input: " + ", ".join(unknown))
        if missing:
            problems.append("not filed anywhere: " + ", ".join(missing))
        if problems:
            raise ValueError("; ".join(problems))
        return self


def parse_free(text: str):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t), True
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0)), True
            except json.JSONDecodeError:
                pass
    return None, False


def audit(case, obj):
    """Structural faults of one output, the things a schema can and cannot stop."""
    ids = {it["id"] for it in case["items"]}
    c = collections.Counter()
    if obj is None or not isinstance(obj, dict):
        c["not_json"] += 1
        return c
    c["extra_keys"] += sum(1 for k in obj if k not in pc.DIVISIONS)
    filed = collections.Counter()
    for d in pc.DIVISIONS:
        v = obj.get(d)
        if not isinstance(v, list):
            c["bad_value"] += 1
            continue
        for x in v:
            sid = (x.get("id") if isinstance(x, dict) else str(x)).strip().upper() if x is not None else ""
            filed[sid] += 1
    c["unknown_ids"] += sum(1 for k in filed if k not in ids)
    c["duplicates"] += sum(1 for k, v in filed.items() if k in ids and v > 1)
    c["missing"] += sum(1 for k in ids if k not in filed)
    ok = {d: [(x.get("id") if isinstance(x, dict) else str(x)) for x in obj.get(d, []) if x is not None] for d in pc.DIVISIONS if isinstance(obj.get(d), list)}
    counts, _, _, _, _ = pc.score(case, ok, False)
    c["misplaced"] += counts["misplaced"]
    return c


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(HERE, model=args.model, live=args.live)
    cases = pc.build_cases()
    system_plain = pc.PROMPTS["plain"][0]
    n_units = sum(len(c["items"]) for c in cases)
    print(f"{len(cases)} ACI-Bench notes, {n_units} sentences; plain prompt; one draw per condition\n")

    def free(case):
        text = llm.complete(system=system_plain + pc.listing(case, False) + "\n\nReturn only the JSON object with the four keys.",
                            user="File the sentences.", schema=None, max_tokens=4000, sample=1)
        obj, _ = parse_free(text)
        return obj

    def with_schema(case):
        return llm.json(system=system_plain + pc.listing(case, False), user="File the sentences.",
                        schema=pc.schema(False), max_tokens=4000, sample=1)

    def validated(case):
        ids = [it["id"] for it in case["items"]]
        obj = with_schema(case)
        attempts = 0
        while True:
            try:
                Filing.model_validate(obj, context={"ids": ids})
                return obj, attempts, True
            except ValidationError as e:
                msg = "; ".join(err["msg"].replace("Value error, ", "") for err in e.errors())
                if attempts >= RETRIES:
                    return obj, attempts, False
                attempts += 1
                obj = llm.json(system=system_plain + pc.listing(case, False),
                               user="File the sentences.\n\nYour previous answer was:\n" + json.dumps(obj) +
                                    "\n\nIt failed validation: " + msg + "\nReturn the corrected JSON.",
                               schema=pc.schema(False), max_tokens=4000, sample=1)

    free_out = map_parallel(free, cases, workers=8)
    schema_out = map_parallel(with_schema, cases, workers=8)
    val_out = map_parallel(validated, cases, workers=8)

    print(f"{'condition':10} {'not JSON':>8} {'extra keys':>10} {'unknown IDs':>11} {'duplicates':>10} {'missing':>8} {'misplaced':>10}   (60 outputs, {n_units} sentences)")
    for name, outs in (("free", free_out), ("schema", schema_out), ("validated", [o for o, _, _ in val_out])):
        c = collections.Counter()
        for case, obj in zip(cases, outs):
            c.update(audit(case, obj))
        print(f"{name:10} {c['not_json']:>8} {c['extra_keys']:>10} {c['unknown_ids']:>11} {c['duplicates']:>10} {c['missing']:>8} {c['misplaced']:>10}")
    first_fail = sum(1 for _, a, _ in val_out if a > 0)
    fixed1 = sum(1 for _, a, ok in val_out if a == 1 and ok)
    fixed2 = sum(1 for _, a, ok in val_out if a == 2 and ok)
    still = sum(1 for _, _, ok in val_out if not ok)
    print(f"\n>> validated: {first_fail} of 60 outputs failed the exactly-once validator at first; fixed by one re-ask {fixed1}, by two {fixed2}; still failing after two {still}")
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
