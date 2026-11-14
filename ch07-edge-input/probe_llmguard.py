"""Chapter 7, probe: an off-the-shelf prompt-injection scanner.

The chapter's injection fix names LLM Guard and Azure Content Safety as the
scanner to use, and then measures an eight-line regex. This probe runs LLM
Guard's PromptInjection scanner — a fine-tuned DeBERTa classifier that runs
locally, no API key — over the same 144 cases, the same way fixed.py runs the
regex: on the user's message, and separately on the retrieved document, which
is where the buried payload lives.

What it answers:
  - does a model-based scanner beat the phrase list, in particular on the
    twelve Spanish attempts the list deliberately does not cover;
  - what it costs in false alarms on legitimate traffic, especially the Hindi
    and padded queries that the embedding-distance gate destroyed.

Ground truth is derived from how each query was built (common.py): the four
injection subclasses should be flagged, the other eight should not. For
inj_buried_doc the query is clean and the payload is in the document, so only
the document scan can catch it.

Two configurations are run, because the scanner reads at most 512 tokens:
  full    the library default — one pass over the text, truncated
  chunks  the text split into chunks and every chunk scanned
Threshold is the library default (0.92 on the model's risk score).

Usage:
  python probe_llmguard.py            # replay from llmguard_scan.json
  python probe_llmguard.py --live     # re-scan (downloads the model on first use)
  python probe_llmguard.py --timings | tee llmguard_timings_log.txt
                                      # time every scan; writes nothing to the cache

Timings are a property of the machine, so they cannot be replayed: --timings
scans all 144 cases again, times each scan, checks the fresh flags against
llmguard_scan.json, and prints the machine. llmguard_timings_log.txt is its
last output. On a Mac with Apple silicon the library runs the model on the
GPU (torch "mps") by default, so --timings times that and the CPU separately.

Needs Python 3.10+ and `pip install llm-guard`. The rest of the repo runs on
3.9; keep this probe in its own environment.
"""

import argparse
import dataclasses
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from common import build_cases  # noqa: E402

CACHE = HERE / "llmguard_scan.json"
TIMINGS_LOG = HERE / "llmguard_timings_log.txt"
CONFIGS = ("full", "chunks")
INJECTION = ("inj_direct", "inj_roleplay", "inj_spanish", "inj_buried_doc")
SUBCLASS_ORDER = [
    "in_scope_indication", "in_scope_dosage", "oos_other_drug", "oos_nonmedical",
    "ood_hindi", "ood_long", "ood_numeric", "ood_blank",
    "inj_direct", "inj_roleplay", "inj_spanish", "inj_buried_doc",
]


def _key(config: str, threshold: float, text: str) -> str:
    h = hashlib.sha256(f"{config}|{threshold}|{text}".encode("utf-8")).hexdigest()[:20]
    return h


def load_scanner(config: str, threshold: float, device=None):
    from llm_guard.input_scanners import PromptInjection
    from llm_guard.input_scanners.prompt_injection import MatchType, V2_MODEL
    from llm_guard.util import configure_logger

    configure_logger(log_level="ERROR")  # it logs every scan to stdout at DEBUG
    match = MatchType.FULL if config == "full" else MatchType.CHUNKS
    model = V2_MODEL
    if device is not None:  # same model, pinned to one device instead of the library's pick
        model = dataclasses.replace(V2_MODEL, pipeline_kwargs={**V2_MODEL.pipeline_kwargs, "device": device})
    return PromptInjection(threshold=threshold, match_type=match, model=model), V2_MODEL


def scan_all(cases, threshold: float, live: bool):
    cache = json.loads(CACHE.read_text()) if CACHE.is_file() else {}
    texts = []
    for c in cases:
        texts.append(("query", c["query"]))
        texts.append(("document", c["context"]))
    results, timings, model_name = {}, {}, None
    for config in CONFIGS:
        wanted = {(config, kind, t) for kind, t in texts}
        missing = [(kind, t) for cfg, kind, t in wanted if _key(config, threshold, t) not in cache]
        if missing or live:
            scanner, model_name = load_scanner(config, threshold)
            todo = [(kind, t) for kind, t in texts] if live else missing
            t0 = time.time()
            for n, (kind, t) in enumerate(todo, 1):
                if not t.strip():
                    cache[_key(config, threshold, t)] = {"risk": 0.0, "flagged": False, "text": ""}
                    continue
                _, is_valid, risk = scanner.scan(t)
                cache[_key(config, threshold, t)] = {
                    "risk": round(float(risk), 4), "flagged": not is_valid, "text": t[:70],
                }
                if n % 20 == 0:  # save as we go: a long first run must not lose progress
                    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True))
            timings[config] = (time.time() - t0) / max(1, len(todo))
            CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True))
        results[config] = {(kind, t): cache[_key(config, threshold, t)] for kind, t in texts}
    return results, timings, model_name


def report(cases, results, timings, model_name, threshold):
    print(f"LLM Guard PromptInjection, model {model_name or '(library default, replayed)'}, "
          f"threshold {threshold}")
    for config in CONFIGS:
        r = results[config]
        print(f"\n=== match type: {config} ===")
        print(f"{'subclass':22} {'n':>3} {'should flag':>11} {'query flagged':>13} {'doc flagged':>11} {'mean risk (q)':>13}")
        agg = {}
        for sub in SUBCLASS_ORDER:
            subset = [c for c in cases if c["subclass"] == sub]
            q = [r[("query", c["query"])] for c in subset]
            d = [r[("document", c["context"])] for c in subset]
            qf, df = sum(x["flagged"] for x in q), sum(x["flagged"] for x in d)
            should = "yes" if sub in INJECTION else "no"
            agg[sub] = (len(subset), qf, df)
            print(f"{sub:22} {len(subset):>3} {should:>11} {qf:>13} {df:>11} {sum(x['risk'] for x in q)/len(q):>13.2f}")
        inj = [c for c in cases if c["subclass"] in INJECTION]
        caught = sum(1 for c in inj if r[("query", c["query"])]["flagged"] or r[("document", c["context"])]["flagged"])
        legit = [c for c in cases if c["subclass"] not in INJECTION]
        false = sum(1 for c in legit if r[("query", c["query"])]["flagged"] or r[("document", c["context"])]["flagged"])
        spanish = agg["inj_spanish"][1]
        hindi_f, padded_f = agg["ood_hindi"][1], agg["ood_long"][1]
        print(f"\n>> Injection attempts flagged, on the query or the document: {caught} of {len(inj)}")
        print(f"   Spanish attempts flagged on the query: {spanish} of 12  (the regex caught 0 of 12)")
        print(f"   Buried-document attempts flagged on the document: {agg['inj_buried_doc'][2]} of 12")
        print(f">> Legitimate inputs wrongly flagged (query or document): {false} of {len(legit)}")
        print(f"   Hindi questions flagged: {hindi_f} of 12   Padded questions flagged: {padded_f} of 12")
        if config in timings:
            print(f">> Time per scan: {timings[config]*1000:.0f} ms (local machine), no API calls")
        else:
            print(f">> Time per scan: not replayable; last measured in {TIMINGS_LOG.name} (--timings)")


def machine() -> str:
    cpu = platform.processor() or platform.machine()
    if sys.platform == "darwin":
        cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                             capture_output=True, text=True).stdout.strip() or cpu
    return f"{platform.platform()} · {cpu} · {os.cpu_count()} cores · Python {platform.python_version()}"


def time_scans(cases, threshold: float, passes: int) -> None:
    """Scan every non-blank query and document live, timing each scan.

    Writes nothing: llmguard_scan.json stays as recorded, and the fresh flags
    are compared with it. Model load and one warm-up scan are not timed.
    """
    from importlib.metadata import version

    import torch
    from llm_guard.util import device as library_device

    cache = json.loads(CACHE.read_text())
    texts = [(kind, t) for c in cases for kind, t in (("query", c["query"]), ("document", c["context"]))]
    scanned = [(kind, t) for kind, t in texts if t.strip()]
    print(f"machine: {machine()}")
    print(f"llm-guard {version('llm-guard')} · torch {version('torch')} · transformers {version('transformers')}"
          f" · torch CPU threads {torch.get_num_threads()} · threshold {threshold}")
    print(f"{len(scanned)} scans per pass ({len(texts)} texts, {len(texts) - len(scanned)} blank queries skipped)"
          f" × {passes} passes; model load and one warm-up scan not timed\n")
    devices = [str(library_device())] + ([] if library_device().type == "cpu" else ["cpu"])
    for dev in devices:
        for config in CONFIGS:
            scanner, _ = load_scanner(config, threshold, dev)
            scanner.scan(scanned[0][1])
            ms = {"query": [], "document": []}
            pass_means, agree, compared, worst = [], 0, 0, 0.0
            for p in range(passes):
                t_pass = []
                for kind, t in scanned:
                    t0 = time.perf_counter()
                    _, is_valid, risk = scanner.scan(t)
                    took = (time.perf_counter() - t0) * 1000
                    ms[kind].append(took)
                    t_pass.append(took)
                    rec = cache.get(_key(config, threshold, t)) if p == 0 else None
                    if rec:  # recorded only at the thresholds a --live run used
                        compared += 1
                        agree += (not is_valid) == rec["flagged"]
                        worst = max(worst, abs(round(float(risk), 4) - rec["risk"]))
                pass_means.append(statistics.mean(t_pass))
            every = ms["query"] + ms["document"]
            label = dev + (" (library default)" if dev == devices[0] else "")
            print(f"=== device {label} · match type {config}")
            print(f"   mean {statistics.mean(every):.0f} ms · median {statistics.median(every):.0f} ms"
                  f" · queries {statistics.mean(ms['query']):.0f} ms · documents {statistics.mean(ms['document']):.0f} ms"
                  f" · slowest {max(every):.0f} ms")
            print("   mean per pass: " + ", ".join(f"{m:.0f}" for m in pass_means) + " ms")
            print(f"   flags agree with {CACHE.name} on {agree} of {compared} recorded scans;"
                  f" largest risk difference {worst:.4f}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--timings", action="store_true", help="time every scan live; writes nothing to the cache")
    ap.add_argument("--passes", type=int, default=3, help="passes over the corpus for --timings")
    ap.add_argument("--threshold", type=float, default=0.92)
    args = ap.parse_args()
    cases = build_cases()
    if args.timings:
        time_scans(cases, args.threshold, args.passes)
        return 0
    results, timings, model_name = scan_all(cases, args.threshold, args.live)
    report(cases, results, timings, model_name, args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
