"""Task 10.1 — does silent omission get worse as the list gets longer?

Chapter 10's failure was tested on short numeric lists: 8 to 13 dose figures per
document, where an independent count is a regular expression. It barely
reproduced. The chapter's own examples are prose enumerations — forty obligations
in a contract, two hundred entries in an adverse-reactions list — and nothing in
the repo tested those.

This does. The source text is identical in every arm. The ONLY thing that changes
is how much is asked for at once:

  all-at-once   1 call   "list every adverse reaction"          185 expected
  by-system    13 calls  one body system per call               ~14 expected each
  by-group     39 calls  one frequency group per call            ~5 expected each

If omission is a load failure, recall should fall as the ask grows while the
document stays the same size. If it is a reading failure, recall should be flat.

Ground truth is the label's own structure: "Body System - Frequent: a, b;
Infrequent: c, d; Rare: e, f." Splitting on those delimiters yields 185 distinct
clinical terms with no model involved.

    python3 prose_scale.py
    python3 prose_scale.py --live
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.llm import LLM, base_args, load_labels, map_parallel  # noqa: E402
from shared.scoring import headline, pct, rule, table  # noqa: E402

DRUG = "Sertraline"
GROUP = re.compile(r"\b(Frequent|Infrequent|Rare)\s*:\s*([^;.]+)")
SYSTEM_HEAD = re.compile(
    r"(?:^|\.\s+)([A-Z][A-Za-z ,/]{4,70}?)\s*[–—-]\s*(?=(?:Frequent|Infrequent|Rare)\s*:)")
TERM = re.compile(r"[a-zA-Z][a-zA-Z \-'/]{2,44}")

SCHEMA = {
    "type": "object",
    "properties": {"reactions": {"type": "array", "items": {"type": "string"}}},
    "required": ["reactions"],
    "additionalProperties": False,
}

PROMPT = """You are a clinical data extraction assistant. The text below is the
ADVERSE REACTIONS section of a drug label.

{ask}

List them exactly as the document words them. Completeness is the quality measure.

<text>
{text}
</text>"""


def norm(s):
    return re.sub(r"\s+", " ", s.strip().lower().rstrip(".")).strip()


def ground_truth(text):
    """Every listed reaction, and the same split by body system and by group.

    Body-system headings sit before the FIRST frequency group of a run and the
    later groups inherit them, so each group is assigned to the nearest heading
    that precedes it.
    """
    heads = [(m.start(1), m.group(1).strip()) for m in SYSTEM_HEAD.finditer(text)]

    def system_for(pos):
        prior = [h for start, h in heads if start < pos]
        return prior[-1] if prior else "Unspecified"

    everything, by_system, by_group = [], {}, []
    for m in GROUP.finditer(text):
        items = [i.strip(" .") for i in m.group(2).split(",")]
        items = [i for i in items if TERM.fullmatch(i)]
        if not items:
            continue
        system = system_for(m.start())
        everything += items
        by_system.setdefault(system, []).extend(items)
        by_group.append((system, m.group(1), items))
    return everything, by_system, by_group


def recall(expected, returned):
    got = {norm(r) for r in returned}
    hit = [e for e in expected if norm(e) in got]
    return hit, [e for e in expected if norm(e) not in got]


def main() -> int:
    args = base_args(__doc__).parse_args()
    label = next(l for l in load_labels() if DRUG in l["drug"])
    text = label["sections"]["adverse_reactions"]
    everything, by_system, by_group = ground_truth(text)

    llm = LLM(Path(__file__).parent, model=args.model, live=args.live)

    def ask(question, max_tokens=4000):
        return llm.json(system=PROMPT.format(ask=question, text=text),
                        user="Return the list.", schema=SCHEMA,
                        max_tokens=max_tokens)["reactions"]

    rule(f"{DRUG} adverse reactions — {len(text):,} characters, "
         f"{len(everything)} listed reactions, {len(by_system)} body systems, "
         f"{len(by_group)} frequency groups")

    # ---- arm 1: everything at once -------------------------------------
    got_all = ask("List every adverse reaction the text mentions.")
    hit_all, miss_all = recall(everything, got_all)

    # ---- arm 2: one body system per call -------------------------------
    systems = sorted(by_system)
    outs = map_parallel(
        lambda s: ask(f'List every adverse reaction the text lists under the body '
                      f'system "{s}".', 1500), systems)
    hit_sys, miss_sys = [], []
    for s, out in zip(systems, outs):
        h, m = recall(by_system[s], out)
        hit_sys += h
        miss_sys += m

    # ---- arm 3: one frequency group per call ---------------------------
    outs = map_parallel(
        lambda g: ask(f'List every adverse reaction the text lists as "{g[1]}" under '
                      f'the body system "{g[0]}".', 800), by_group)
    hit_grp, miss_grp = [], []
    for g, out in zip(by_group, outs):
        h, m = recall(g[2], out)
        hit_grp += h
        miss_grp += m

    rows = [
        ["all at once", 1, len(everything), len(got_all), len(hit_all),
         pct(len(hit_all), len(everything))],
        ["by body system", len(systems), len(everything),
         sum(len(o) for o in outs) if False else "-", len(hit_sys),
         pct(len(hit_sys), len(everything))],
        ["by frequency group", len(by_group), len(everything), "-", len(hit_grp),
         pct(len(hit_grp), len(everything))],
    ]
    table(["arm", "calls", "expected", "returned", "found", "recall"], rows)

    headline("Recall asking for everything in one call",
             pct(len(hit_all), len(everything)),
             f"{len(miss_all)} of {len(everything)} listed reactions never appeared "
             "in the output, and nothing said so.")
    headline("Recall asking one body system at a time",
             pct(len(hit_sys), len(everything)),
             "Identical source text. Only the size of the request changed.")
    headline("Recall asking one frequency group at a time",
             pct(len(hit_grp), len(everything)),
             "The smallest ask over the same document.")

    if miss_all:
        rule("A sample of what the single-call arm dropped")
        print("   " + " | ".join(miss_all[:24]))
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
