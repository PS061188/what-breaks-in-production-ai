"""Model client, fixture cache, and cost meter.

Every chapter script goes through this. Two things matter here:

1. **Fixtures.** Each request is hashed and its response written to the
   chapter's fixtures/ directory. Re-running offline replays the recorded
   response, so `python broken.py` works with no API key and costs nothing.
   `--live` re-runs against the API and rewrites the fixtures.

2. **Cost.** Every live call accumulates token usage, printed at the end of
   each run. If a chapter costs more than a few cents you should be able to
   see that before you run it, not after.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_MODEL = "claude-haiku-4-5"

# USD per million tokens (input, output), from each provider's pricing page.
# Used for the run-cost estimate only — it is not billing.
PRICES = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (5.00, 25.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
}


# Models where reasoning is on unless you turn it off, and therefore share the
# output budget with the answer.
# Sonnet 5 reasons by default too. This is the same bug appearing a second
# time: a budget that fits a non-thinking model truncates a thinking one, and
# it surfaces as unreadable output rather than as anything mentioning budgets.
# The headroom is added to the request, not to the cache key, so recordings
# made before this change stay valid.
THINKS_BY_DEFAULT = {
    "claude-opus-5", "claude-sonnet-5",
    # And the GPT-5 family, which is the third model family to hit this. Their
    # reasoning tokens count against the same completion budget, and they use
    # considerably more of it than the Claude models do — hence the larger
    # headroom below. Three families, one mistake: a budget sized for a model
    # that answers immediately truncates a model that thinks first, and the
    # symptom is never a message about budgets.
    "gpt-5", "gpt-5-mini", "gpt-5-nano",
}
REASONING_HEADROOM = {"gpt-5": 8000, "gpt-5-mini": 8000, "gpt-5-nano": 8000}


def provider_for(model: str) -> str:
    """Which SDK a model id belongs to.

    The point of the cross-provider sweep is to find out which results are
    properties of the failure and which are properties of one vendor's model.
    Everything else in the repo is provider-agnostic already — the prompts are
    plain text and the checks are plain code.
    """
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    raise ValueError(f"Unknown provider for model {model!r}")


class FixtureMissing(RuntimeError):
    pass


def load_dotenv(start: Path) -> None:
    """Merge KEY=VALUE lines from every .env on the path upward.

    Nearest file wins per key, because `setdefault` never overwrites, and an
    exported variable beats every file.

    This walks the whole tree rather than stopping at the first .env it finds.
    The earlier version stopped, and the moment a repo-local .env was added
    holding only an OPENAI key, every Anthropic call started failing with
    "ANTHROPIC_API_KEY is not set" — while the key sat, untouched, in a .env one
    directory up. Worth remembering as its own small lesson: the bug was not in
    the code that broke.
    """
    for directory in [start, *start.parents]:
        env_file = directory / ".env"
        if not env_file.is_file():
            continue
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class LLM:
    def __init__(self, chapter_dir: Path, model: str = DEFAULT_MODEL, live: bool = False):
        self.fixtures = Path(chapter_dir) / "fixtures"
        self.fixtures.mkdir(exist_ok=True)
        self.model = model
        self.provider = provider_for(model)
        self.live = live
        self.calls = 0
        self.replayed = 0
        self.input_tokens = 0
        self.output_tokens = 0
        # Wall-clock spent inside API calls. Recorded into the fixture so a
        # replay can still tell you what the live run cost in time, not just in
        # money — the two scale differently and readers need both.
        self.api_seconds = 0.0
        self.recorded_seconds = 0.0
        self.duplicate_requests = 0
        self._client = None
        self._lock = __import__('threading').Lock()

    def _get_client(self):
        if self._client is not None:
            return self._client

        load_dotenv(Path(__file__).resolve().parent)

        if self.provider == "anthropic":
            import anthropic

            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add "
                    "your key, or drop --live to replay the recorded fixtures."
                )
            self._client = anthropic.Anthropic()
        else:
            try:
                import openai
            except ImportError as exc:
                raise RuntimeError("pip install openai to use GPT models") from exc

            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. Note this is an API key from "
                    "platform.openai.com — a ChatGPT subscription is a different "
                    "product and does not provide one."
                )
            self._client = openai.OpenAI()
        return self._client

    def _call_openai(self, system, user, schema, max_tokens):
        """Same contract as the Anthropic path: text back, usage recorded.

        OpenAI's structured-output field is `response_format` with a named
        json_schema rather than Anthropic's `output_config`; the schema itself
        is the same JSON Schema, which is why the chapter code needs no changes.
        """
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens": max_tokens,
        }
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            }
        response = self._get_client().chat.completions.create(**kwargs)
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError(
                f"Response hit max_tokens={max_tokens} and was cut off mid-output."
            )
        return (
            choice.message.content or "",
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )

    def _key(self, payload: Dict[str, Any]) -> str:
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]

    def complete(
        self,
        system: str,
        user: str,
        schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4000,
    ) -> str:
        """Return the model's text response, from cache or from the API."""
        payload = {
            "model": self.model,
            "system": system,
            "user": user,
            "schema": schema,
            "max_tokens": max_tokens,
        }
        key = self._key(payload)
        path = self.fixtures / f"{key}.json"

        # Editing a prompt changes the key, which orphans the old fixture rather
        # than overwriting it. prune_fixtures.py sets FIXTURE_AUDIT and reads
        # this file back to find the strays.
        audit = os.environ.get("FIXTURE_AUDIT")
        if audit:
            with open(audit, "a") as handle:
                handle.write(f"{self.fixtures}\t{key}\n")

        if not self.live and path.is_file():
            recorded = json.loads(path.read_text())
            with self._lock:
                self.replayed += 1
                self.recorded_seconds += recorded.get("elapsed_ms", 0) / 1000.0
                self.input_tokens += recorded.get("usage", {}).get("input_tokens", 0)
                self.output_tokens += recorded.get("usage", {}).get("output_tokens", 0)
            return recorded["response"]

        if not self.live:
            raise FixtureMissing(
                f"No fixture for this request ({key}).\n"
                "Either the prompt changed or the corpus did. Re-record with --live, "
                "or `git checkout` the fixtures/ directory to get the committed run back."
            )

        # Two concurrent calls with an identical request both miss the cache,
        # both hit the API, and both write the same content-addressed file — so
        # the run uses two sampled answers while the recording keeps only one,
        # and a later replay quietly disagrees with the live run. Found by a
        # chapter whose fixture went missing on replay. The cache is doing what
        # it was designed to do; the design absorbed a duplicate silently
        # instead of saying so.
        if self.live and path.is_file():
            with self._lock:
                self.duplicate_requests += 1

        started = time.monotonic()
        if self.provider == "openai":
            headroom = REASONING_HEADROOM.get(self.model, 0) if self.model in THINKS_BY_DEFAULT else 0
            text, tokens_in, tokens_out = self._call_openai(
                system, user, schema, max_tokens + headroom
            )
        else:
            # Models that think by default spend part of max_tokens on
            # reasoning before writing a single character of the answer, so a
            # budget tuned for a non-thinking model truncates them mid-output.
            # This is the first thing that broke in the cross-model sweep, and
            # it is worth knowing about before you swap models in production:
            # the failure looks like malformed JSON, not like a budget problem.
            budget = max_tokens + (REASONING_HEADROOM.get(self.model, 4000)
                                   if self.model in THINKS_BY_DEFAULT else 0)
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": budget,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
            if schema is not None:
                kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}

            response = self._get_client().messages.create(**kwargs)

            if response.stop_reason == "refusal":
                raise RuntimeError(
                    f"Model declined this request (stop_reason=refusal): {user[:120]}"
                )
            if response.stop_reason == "max_tokens":
                # Truncated output is not a JSON parse error, however it
                # presents. Say so here rather than letting json.loads report an
                # unterminated string 4,000 characters into a response nobody is
                # going to read.
                raise RuntimeError(
                    f"Response hit max_tokens={max_tokens} and was cut off mid-output. "
                    "Raise max_tokens for this call; the fixture was not written."
                )

            text = "".join(block.text for block in response.content if block.type == "text")
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens

        elapsed_ms = int((time.monotonic() - started) * 1000)
        with self._lock:
            self.api_seconds += elapsed_ms / 1000.0
            self.calls += 1
            self.input_tokens += tokens_in
            self.output_tokens += tokens_out

        path.write_text(
            json.dumps(
                {
                    "model": self.model,
                    "system": system,
                    "user": user,
                    "schema": schema,
                    "response": text,
                    "elapsed_ms": elapsed_ms,
                    "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return text

    def json(
        self,
        system: str,
        user: str,
        schema: Dict[str, Any],
        max_tokens: int = 4000,
    ) -> Any:
        """Same as complete(), but parses the response as JSON.

        Both the broken and the fixed script use structured output, so the only
        difference between them is the prompt and the code around it — not
        whether the JSON parsed.
        """
        return json.loads(self.complete(system, user, schema=schema, max_tokens=max_tokens))

    def cost(self) -> float:
        rate_in, rate_out = PRICES.get(self.model, (0.0, 0.0))
        return (self.input_tokens * rate_in + self.output_tokens * rate_out) / 1_000_000

    def report(self, label: str = "") -> None:
        """Cost and wall-clock, printed at the end of every run.

        On a replay the cost and time are what the *recorded* live run spent,
        read back out of the fixtures — a replay itself is free and instant.
        """
        mode = "live" if self.live else "replay"
        seconds = self.api_seconds if self.live else self.recorded_seconds
        n = self.calls if self.live else self.replayed
        parts = [f"  [{mode}] {n} model call(s)"]
        if self.input_tokens or self.output_tokens:
            parts.append(f"{self.input_tokens:,} in / {self.output_tokens:,} out tokens")
            parts.append(f"${self.cost():.4f} on {self.model}")
        if seconds:
            per_call = seconds / max(n, 1)
            parts.append(f"{seconds:.1f}s in API ({per_call:.2f}s/call)")
        if self.duplicate_requests:
            parts.append(
                f"WARNING: {self.duplicate_requests} duplicate request(s) — "
                "identical prompts sampled more than once; only one recording kept"
            )
        if label:
            parts.append(label)
        print("  ·  ".join(parts), file=sys.stderr)


def map_parallel(fn, items, workers: int = 8):
    """Run fn over items concurrently, returning results in the original order.

    Every call in this repo is independent — one document, one question — so
    the only reason they ran one at a time was that a for-loop is the obvious
    way to write it. On a run of a few hundred calls that costs most of the
    wall-clock and none of the money.

    Order is preserved so results stay aligned with their inputs, and the first
    exception is re-raised rather than swallowed: a partially-completed
    experiment that reports a number is worse than one that stops.
    """
    from concurrent.futures import ThreadPoolExecutor

    items = list(items)
    if len(items) < 2:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))


def load_labels() -> list:
    """The corpus, optionally damaged first.

    Setting CORRUPT_MODE applies Chapter 2's deterministic corruption to every
    section of every label before any other chapter sees it. The point is to
    answer the objection that hangs over four chapters of this project: their
    failures barely reproduced, and the most likely explanation is that FDA
    labels are unusually clean input. Every chapter keeps its own scoring — only
    the documents change.

    Corruption is seeded on the drug name and the section, so a given
    (mode, drug, section) is byte-identical on every run and fixtures replay.
    """
    path = Path(__file__).resolve().parent.parent / "data" / "labels.json"
    labels = json.loads(path.read_text())["labels"]

    mode = os.environ.get("CORRUPT_MODE")
    if not mode or mode == "clean":
        return labels

    # Real OCR, not simulated. data/labels_ocr.json holds the corpus after it was
    # typeset, rendered, degraded like a scan, and read back by Apple Vision.
    # Only dosage_and_administration was rendered, so chapters that need other
    # sections cannot use this mode.
    if mode == "real_ocr":
        ocr_path = Path(__file__).resolve().parent.parent / "data" / "labels_ocr.json"
        if not ocr_path.is_file():
            raise SystemExit(
                "CORRUPT_MODE=real_ocr needs data/labels_ocr.json.\n"
                "  Build it with: .venv-ocr/bin/python make_ocr_corpus.py"
            )
        by_drug = {d["drug"]: d["ocr_text"]
                   for d in json.loads(ocr_path.read_text())["documents"]}
        for label in labels:
            text = by_drug.get(label.get("drug"))
            if text:
                label["sections"]["dosage_and_administration"] = text
        return labels

    # ch02's directory name is not a valid module name, so load it by path.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_ch02_common",
        Path(__file__).resolve().parent.parent / "ch02-input-integrity" / "common.py",
    )
    ch02 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ch02)

    for label in labels:
        drug = label.get("drug", "?")
        for section, text in list(label.get("sections", {}).items()):
            if not text:
                continue
            label["sections"][section] = ch02.corrupt(text, mode, f"{drug}:{section}")
    return labels


def base_args(description: str):
    """The flags every chapter script shares."""
    import argparse

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--live",
        action="store_true",
        help="call the API instead of replaying fixtures (costs money, rewrites fixtures)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"model id (default: {DEFAULT_MODEL}). Try claude-opus-5 to see whether the "
        "failure still reproduces on a stronger model.",
    )
    parser.add_argument("--limit", type=int, default=0, help="only run the first N documents")
    return parser
