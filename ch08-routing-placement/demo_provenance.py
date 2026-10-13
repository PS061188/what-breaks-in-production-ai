"""Chapter 8, demonstration: what a provenance record lets you tell apart.

Not a measurement. Everything here holds by construction, and the book must not
print it as a rate. It exists so a reader can run the chapter's diagnosis and
watch it work.

The chapter's containment advice: when content is in the wrong section, compare
two fields of the provenance record — generated_into (which section the
component that produced the element was writing) and placed_into (where the
merge step filed it). They separate two causes that look identical in the
final document:

  merge fault       the generator wrote the right section; the merge step moved it
                    -> generated_into != placed_into
  generator fault   the generator itself wrote content that belongs elsewhere
                    -> generated_into == placed_into, but the content's real
                       origin (located in the source) is a different section

Without the record, both cases show only "content is in the wrong section".
The quote check can locate the content's origin, but it cannot say which stage
put it where it is.

This script builds a two-stage pipeline in code — generators that emit each
label's sentences as elements tagged with generated_into, then a merge step that
files them with placed_into — plants faults of both kinds plus the two other
impossible states the chapter names (an element under two headings; an element
with no record), and reports how the diagnosis reads each one.

Usage:
  python demo_provenance.py     # no model calls
"""

import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from common import SECTIONS, build_cases, locate  # noqa: E402

SEED = 8


def sentences(text: str):
    parts = re.split(r"(?<=[.;:])\s+(?=[A-Z(])", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def generate(case):
    """Stage 1: one generator per section emits elements with provenance."""
    elements = []
    for section in SECTIONS:
        for i, text in enumerate(sentences(case["sections"][section])):
            elements.append({
                "element_id": f"{case['drug'][:8]}:{section[:4]}:{i}",
                "text": text,
                "produced_by": f"{section}_generator",
                "generated_into": section,
            })
    return elements


def merge(elements):
    """Stage 2: file every element. Correct by default."""
    return [{**e, "placed_into": e["generated_into"]} for e in elements]


def plant(doc, case, rng):
    """Plant one fault of each kind; return the doc and the truth for each."""
    truth = {}
    others = lambda s: [x for x in SECTIONS if x != s]
    # merge fault: the record still says where it was generated
    e = rng.choice(doc); e["placed_into"] = rng.choice(others(e["generated_into"])); truth[e["element_id"]] = "merge fault"
    # generator fault: content from section X, emitted by Y's generator and filed under Y
    src = rng.choice(SECTIONS); dst = rng.choice(others(src))
    text = rng.choice(sentences(case["sections"][src]))
    g = {"element_id": f"{case['drug'][:8]}:gen-fault", "text": text, "produced_by": f"{dst}_generator",
         "generated_into": dst, "placed_into": dst}
    doc.append(g); truth[g["element_id"]] = "generator fault"
    # duplicate: the same element under two headings
    d = rng.choice([x for x in doc if x["element_id"] not in truth])
    doc.append({**d, "placed_into": rng.choice(others(d["placed_into"]))}); truth[d["element_id"]] = "duplicate"
    # no record
    n = {"element_id": f"{case['drug'][:8]}:no-record", "text": rng.choice(sentences(case["sections"][SECTIONS[0]])),
         "placed_into": SECTIONS[0]}
    doc.append(n); truth[n["element_id"]] = "no record"
    return doc, truth


def diagnose(doc, case):
    """The chapter's checks, run over the record."""
    verdicts = {}
    seen = {}
    for e in doc:
        eid = e["element_id"]
        if "generated_into" not in e:
            verdicts[eid] = "no record"; continue
        if eid in seen:
            verdicts[eid] = "duplicate"; continue
        seen[eid] = e
        if e["placed_into"] != e["generated_into"]:
            verdicts[eid] = "merge fault"; continue
        origin = locate(e["text"], case["sections"])
        if origin is not None and origin != e["generated_into"]:
            verdicts[eid] = "generator fault"; continue
        verdicts[eid] = "ok"
    return verdicts


def without_record(doc, case):
    """What the quote check alone can say: wrong section or not, cause unknown."""
    out = {}
    for e in doc:
        origin = locate(e["text"], case["sections"])
        out[e["element_id"]] = "wrong section (cause unknown)" if origin and origin != e["placed_into"] else "looks fine"
    return out


def main() -> int:
    rng = random.Random(SEED)
    cases = build_cases()
    tally = {}
    blind = {}
    for case in cases:
        doc, truth = plant(merge(generate(case)), case, rng)
        v = diagnose(doc, case)
        b = without_record(doc, case)
        for eid, kind in truth.items():
            tally.setdefault(kind, [0, 0]); tally[kind][1] += 1
            tally[kind][0] += (v.get(eid) == kind)
            blind.setdefault(kind, {}); blind[kind][b.get(eid)] = blind[kind].get(b.get(eid), 0) + 1
    print(f"{len(cases)} labels, four planted faults each\n")
    print(f"{'planted fault':18} {'named correctly by the record':>30}")
    for kind, (ok, n) in tally.items():
        print(f"{kind:18} {ok:>10} of {n}")
    print("\nWhat the quote check alone says about the same faults (no record):")
    for kind, d in blind.items():
        print(f"  {kind:18} -> " + "; ".join(f"{v}: {c}" for v, c in d.items()))
    print("\nBy construction: the record names each cause because the record is written faithfully.")
    print("The point is the second table — without it, a merge fault and a generator fault read the same.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
