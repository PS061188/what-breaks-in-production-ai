"""Chapter 8, probe: the Instructor library itself, on ten clinical notes (Experiment 8.7).

Experiment 8.7's validated condition (probe_schema.py) builds the
validator-and-re-ask loop by hand: a Pydantic model requires every sentence ID
to be filed exactly once, and a failed reply goes back with the error quoted.
That is the loop the Instructor library automates. This probe runs Instructor
itself with the same Pydantic model (probe_schema.Filing), the same plain
prompt, and the first ten of the 60 ACI-Bench notes, at max_retries=2: up to
three calls a note, as in probe_schema.py.

The model is Claude Haiku 4.5 with thinking switched off
(MAX_THINKING_TOKENS=0), as in the API calls of probe_schema.py. Instructor
accepts any function that returns an Anthropic Message
(`instructor.patch(create=...)`); the one here turns each request into one
model call. Instructor runs in Mode.JSON, because these calls have no tool
calls and no enforced schema: Instructor writes the JSON schema into the
system prompt and parses the reply. Its re-ask appends a user message
(the validation error and the failed reply), so every message in a request is
a user message; they are joined into one prompt with a blank line between them.

Every call is saved in fixtures_instructor/, named by note and a hash of the
exact request, so a replay needs Instructor installed but no key.

  uv venv --python 3.11 .venv-instructor
  uv pip install --python .venv-instructor/bin/python instructor==1.17.0 anthropic
  .venv-instructor/bin/python ch08-routing-placement/probe_instructor.py          # replay
  .venv-instructor/bin/python ch08-routing-placement/probe_instructor.py --live   # record (about 12 calls)
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from shared.deps import require  # noqa: E402

require("instructor", "instructor==1.17.0 anthropic", "running the Instructor library itself")

import instructor  # noqa: E402
from anthropic.types import Message, TextBlock, Usage  # noqa: E402
from instructor.core.exceptions import InstructorRetryException  # noqa: E402
from instructor.v2.core.providers import Provider  # noqa: E402
from shared.llm import base_args  # noqa: E402
import probe_clinical as pc  # noqa: E402
import probe_schema as ps  # noqa: E402

FIXTURES = HERE / "fixtures_instructor"
CLI = str(Path.home() / ".local" / "bin" / "claude")
NOTES = 10
MAX_RETRIES = 2


def call_cli(model: str, system: str, prompt: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    env["MAX_THINKING_TOKENS"] = "0"
    cmd = [CLI, "-p", "--model", model, "--output-format", "json", "--system-prompt", system,
           "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]
    with tempfile.TemporaryDirectory() as cwd:
        for attempt in range(3):
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env, cwd=cwd, timeout=600)
            if proc.returncode == 0:
                out = json.loads(proc.stdout)
                if not out.get("is_error"):
                    return out
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"claude CLI failed: {proc.stderr[-400:] or proc.stdout[-400:]}")


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "\n\n".join(b["text"] for b in content if b.get("type") == "text")


def recorded(case: dict, model: str, system: str, prompt: str, live: bool) -> dict:
    digest = hashlib.sha256(json.dumps([model, system, prompt]).encode()).hexdigest()[:16]
    path = FIXTURES / f"{case['encounter_id']}__{digest}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise FileNotFoundError(f"no recorded answer: {path.relative_to(HERE)} (run with --live)")
    started = time.time()
    out = call_cli(model, system, prompt)
    record = {"note": case["encounter_id"], "model_requested": model,
              "models_used": sorted((out.get("modelUsage") or {}).keys()), "thinking": "off",
              "is_reask": "Validation Errors found" in prompt, "reply": out.get("result", ""),
              "usage": {k: (out.get("usage") or {}).get(k, 0) for k in ("input_tokens", "output_tokens")},
              "seconds": round(time.time() - started, 1), "notional_cost_usd": out.get("total_cost_usd")}
    FIXTURES.mkdir(exist_ok=True)
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return record


def run_note(case: dict, model: str, live: bool):
    calls = []

    def create(**kw):
        if any(m["role"] != "user" for m in kw["messages"]):
            raise RuntimeError("a non-user message cannot be carried by one prompt")
        system = text_of(kw.get("system") or "")
        prompt = "\n\n".join(text_of(m["content"]) for m in kw["messages"])
        rec = recorded(case, model, system, prompt, live)
        calls.append(rec)
        return Message(id=f"cli-{len(calls)}", type="message", role="assistant", model=model,
                       content=[TextBlock(type="text", text=rec["reply"])], stop_reason="end_turn",
                       stop_sequence=None, usage=Usage(**rec["usage"]))

    client = instructor.patch(create=create, mode=instructor.Mode.JSON, provider=Provider.ANTHROPIC)
    ids = [it["id"] for it in case["items"]]
    try:
        filing = client(response_model=ps.Filing, model=model, max_tokens=4000, max_retries=MAX_RETRIES,
                        system=pc.PROMPTS["plain"][0] + pc.listing(case, False),
                        messages=[{"role": "user", "content": "File the sentences."}],
                        context={"ids": ids})
        return filing.model_dump(), calls, True
    except InstructorRetryException:
        obj, _ = ps.parse_free(calls[-1]["reply"])
        return obj, calls, False


TEXT_AFTER_ID = re.compile(r"\s*(S\d+)\s*:\s*\S")


def entries(obj) -> list:
    return [x for v in (obj or {}).values() if isinstance(v, list) for x in v if isinstance(x, str)]


def ids_only(obj) -> dict:
    """The same filing with any text after each sentence ID removed."""
    return {k: [TEXT_AFTER_ID.match(x).group(1) if TEXT_AFTER_ID.match(x) else x for x in v]
            for k, v in (obj or {}).items() if isinstance(v, list)}


def main() -> int:
    args = base_args(__doc__).parse_args()
    cases = pc.build_cases()[: args.limit or NOTES]
    n_units = sum(len(c["items"]) for c in cases)
    print(f"Instructor {instructor.__version__} · Mode.JSON · max_retries={MAX_RETRIES} · {args.model}, thinking off")
    print(f"{len(cases)} ACI-Bench notes (the first ten of probe_clinical.py's 60), {n_units} sentences; plain prompt\n")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda c: run_note(c, args.model, bool(args.live)), cases))

    print(f"{'note':10} {'calls':>5} {'valid':>6} {'duplicates':>10} {'missing':>8} {'unknown IDs':>11} {'misplaced':>10}")
    total = {"duplicates": 0, "missing": 0, "unknown_ids": 0, "misplaced": 0}
    for case, (obj, calls, ok) in zip(cases, results):
        c = ps.audit(case, obj)
        for k in total:
            total[k] += c[k]
        print(f"{case['encounter_id']:10} {len(calls):>5} {'yes' if ok else 'NO':>6} {c['duplicates']:>10} "
              f"{c['missing']:>8} {c['unknown_ids']:>11} {c['misplaced']:>10}")
    n_calls = sum(len(calls) for _, calls, _ in results)
    first_fail = sum(1 for _, calls, _ in results if len(calls) > 1)
    fixed1 = sum(1 for _, calls, ok in results if len(calls) == 2 and ok)
    fixed2 = sum(1 for _, calls, ok in results if len(calls) == 3 and ok)
    still = sum(1 for _, _, ok in results if not ok)
    with_text = sum(1 for _, calls, _ in results if len(calls) > 1
                    and any(TEXT_AFTER_ID.match(x) for x in entries(ps.parse_free(calls[0]["reply"])[0])))
    models = sorted({m for _, calls, _ in results for r in calls for m in r["models_used"]})
    print(f"{'all':10} {n_calls:>5} {len(cases) - still:>6} {total['duplicates']:>10} {total['missing']:>8} "
          f"{total['unknown_ids']:>11} {total['misplaced']:>10}")
    print(f"\nfirst replies that failed: {with_text} of {first_fail} wrote each sentence's text after its ID "
          f"(\"S21: Sean Phillips is...\"); the rest left a sentence out or filed one twice")
    for case, (obj, calls, ok) in zip(cases, results):
        if not ok:
            c = ps.audit(case, ids_only(obj))
            print(f"{case['encounter_id']}, last reply with the text after each ID removed: duplicates {c['duplicates']}, "
                  f"missing {c['missing']}, unknown IDs {c['unknown_ids']}")
    print(f"\nmodels that answered: {', '.join(models)}")
    print(f"\n>> instructor: {len(cases) - still} of {len(cases)} notes returned a valid filing; {first_fail} failed "
          f"the validator at first, fixed by one re-ask {fixed1}, by two {fixed2}; still failing {still}; {n_calls} calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
