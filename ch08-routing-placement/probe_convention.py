"""Chapter 8, probe: placement decided by convention, not by meaning.

Every earlier Chapter 8 test used FDA labels, whose sections differ in meaning:
a contraindication cannot be mistaken for an indication by its words, so the
model never misplaced anything, with or without the chapter's prompt, even with
the headings removed (probe_hardcorpus.py). That corpus cannot produce the
failure the chapter is about.

This probe uses the document Prompt 8-1 was written for: a shipping document
with three addresses — origin, destination, billing. The three are the same
kind of content in three roles, and only a label or a convention says which is
which. The documents are GENERATED, with exact ground truth, at three levels:

  L1 explicit    "Ship From:", "Ship To:", "Bill To:"
  L2 varied      role labels drawn from synonyms per document
                 (Sender / Consignee / Payer, From / To / Invoice to, ...)
  L3 position    no role labels; a header states the order, and half the
                 documents reverse it ("recipient first")
  L4 convention  no role labels and no header; sender first in half the
                 documents, recipient first in the other half. Nothing in the
                 text says which address is which — only a convention would.
                 Here the plain prompt must guess; Prompt 8-1's rule that a
                 field may be filled only from text carrying its keywords
                 should return null instead.

Three prompts, three live draws each (the helper's `sample` index):
  plain     extract the three addresses, quote your source
  chapter   Prompt 8-1 as printed in the book, as recorded (prompt_8_1.txt; the
            book's later layout moved two line breaks, the words are the same)
  graded    Prompt 8-1 plus placement_confidence HIGH/MEDIUM/LOW and requires_review,
            the fuller version the chapter's "What did not survive testing" tests
  evidence  Prompt 8-1 plus, per field, role_stated (true if the document says
            in words which address plays this role, false if decided from
            position or convention) as well as the grade — added 25 Sep 2026
            to see whether the model can report what it could not see, field
            by field, rather than a grade that marks the whole document down

Scoring is exact: every address carries a unique company name and a unique
street, so a field is correct if its value names the right company or street,
misplaced if it names another role's, empty if the value is null, and other
otherwise. (An earlier version matched the company only and counted addresses
returned without their company line as "other" — a scorer artefact, withdrawn.) For the graded prompt the report
also shows whether the grade tracks the errors — the question the label corpus
could not ask, because it had no errors.

Usage:
  python probe_convention.py           # replay
  python probe_convention.py --live    # record three draws per prompt (~$1)
"""

import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from shared.llm import LLM, base_args  # noqa: E402

PROMPT_8_1 = HERE / "prompt_8_1.txt"
ROLES = ("origin", "destination", "billing")
FIELDS = {r: f"{r}_address" for r in ROLES}
RUNS = (1, 2, 3)
PER_LEVEL = 12

COMPANIES = ["Northgate Supply", "Harbor Foods", "Ridgeway Components", "Bluefin Logistics", "Cedar Point Labs",
             "Marlowe Textiles", "Summit Packaging", "Ashford Medical", "Quarry Lane Steel", "Pinecrest Retail",
             "Larkspur Optics", "Delta Grain Co", "Ironbridge Tools", "Westmoor Print", "Halden Chemicals",
             "Sable River Dairy", "Oakhurst Electrics", "Tidewater Marine", "Greyfield Paper", "Corvus Data",
             "Merridew Garments", "Stonefall Ceramics", "Brightwater Pharma", "Kestrel Aviation Parts",
             "Foxglove Nursery", "Ravenscar Timber", "Ambleside Books", "Glasswing Cosmetics", "Thornbury Glass",
             "Ellery Instruments", "Wexcombe Brewing", "Nimbus Software", "Holloway Furniture", "Brackenfield Seeds",
             "Silverpine Foods", "Kingsmere Tyres"]
STREETS = ["14 Mill Road", "220 Harbour Street", "7 Station Yard", "91 Beacon Avenue", "3 Foundry Lane",
           "58 Orchard Way", "1200 Industrial Parkway", "16 Chapel Street", "402 Riverside Drive", "9 Kiln Close",
           "77 Market Square", "31 Weavers Row", "640 Northern Bypass", "5 Copper Court", "118 Bridge Road",
           "22 Tannery Walk", "870 Airport Road", "48 Priory Gardens", "2 Wharf Place", "155 Meadow Lane",
           "36 Castle Hill", "600 Trade Estate", "11 Coach Lane", "89 Ferry Road", "27 Granary Street",
           "310 Union Boulevard", "4 Lantern Yard", "63 Hillside Terrace", "199 Canal Street", "8 Barley Mews",
           "72 Quayside", "15 Turbine Way", "540 Ridge Road", "6 Almond Grove", "101 Docklands Avenue", "19 Fold Lane"]
CITIES = ["Leeds", "Bristol", "Cardiff", "Glasgow", "Norwich", "Plymouth", "Aberdeen", "Sheffield", "Exeter",
          "Dundee", "Derby", "Swansea", "Hull", "Preston", "Bath", "Chester", "Lincoln", "Carlisle", "York",
          "Reading", "Oxford", "Durham", "Truro", "Perth", "Stirling", "Wells", "Ely", "Ripon", "Salford", "Wigan",
          "Luton", "Poole", "Dover", "Rugby", "Kendal", "Hexham"]
LABELS_L1 = {"origin": "Ship From:", "destination": "Ship To:", "billing": "Bill To:"}
LABELS_L2 = {"origin": ["From:", "Sender:", "Shipper:", "Return address:", "Dispatched by:", "Consignor:"],
             "destination": ["To:", "Consignee:", "Deliver to:", "Recipient:", "Destination:", "Attention:"],
             "billing": ["Invoice to:", "Payer:", "Account holder:", "Charge to:", "Bill to:", "Remit-to party:"]}
ORDER_WORDS = {"origin": "sender", "destination": "recipient", "billing": "billing party"}


def address(i):
    return f"{COMPANIES[i]}\n{STREETS[i]}\n{CITIES[i]} {random.Random(i).randint(1000, 9999)}"


def make_docs():
    rng = random.Random(81)
    docs = []
    for level in (1, 2, 3, 4):
        for k in range(PER_LEVEL):
            idx = rng.sample(range(len(COMPANIES)), 3)
            truth = dict(zip(ROLES, idx))
            order = list(ROLES)
            header = []
            if level in (3, 4):
                if k % 2:
                    order = ["destination", "origin", "billing"]
            if level == 3:
                header = ["Addresses appear in the order: " + ", ".join(ORDER_WORDS[r] for r in order) + "."]
            lines = [f"SHIPPING DOCUMENT  No. SD-{rng.randint(10000, 99999)}", f"Date: 2026-0{rng.randint(1, 9)}-{rng.randint(10, 28)}", ""] + header
            for r in order:
                label = LABELS_L1[r] if level == 1 else (rng.choice(LABELS_L2[r]) if level == 2 else "")
                lines.append((label + "\n" if label else "") + address(truth[r]))
                lines.append("")
            lines += [f"Items: {rng.randint(1, 40)} cartons, {rng.randint(20, 900)} kg", f"Carrier reference: CR{rng.randint(1000, 9999)}"]
            docs.append({"level": level, "text": "\n".join(lines), "truth": {r: COMPANIES[i] for r, i in truth.items()}})
    return docs


def book_prompt():
    return PROMPT_8_1.read_text(encoding="utf-8")


PLAIN = ("Extract the origin address, the destination address and the billing address from the shipping "
         "document below. For each one, give the value and the exact line you took it from.\n\n<document>\n{doc}\n</document>")
GRADED_SUFFIX = ("\n\nFor each field, also state placement_confidence: HIGH, MEDIUM or LOW, meaning how sure you are "
                 "that this address plays this role. If any field is LOW, set requires_review to true.")
EVIDENCE_SUFFIX = ("\n\nFor each field, also state role_stated: true if the document says in words which address plays "
                   "this role (a label such as Ship From, Consignee or Bill To, or a line giving the order), false if you "
                   "decided from position or convention. Also state placement_confidence: HIGH, MEDIUM or LOW. Set "
                   "requires_review to true if any field has role_stated false or placement_confidence LOW.")


def schema(graded: bool, evidence: bool = False):
    field = {"type": "object", "properties": {"value": {"type": ["string", "null"]}, "source_quote": {"type": ["string", "null"]}},
             "required": ["value", "source_quote"], "additionalProperties": False}
    if graded:
        field["properties"]["placement_confidence"] = {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]}
        field["required"].append("placement_confidence")
    if evidence:
        field["properties"]["role_stated"] = {"type": "boolean"}
        field["required"].append("role_stated")
    props = {FIELDS[r]: field for r in ROLES}
    req = list(props)
    if graded:
        props["requires_review"] = {"type": "boolean"}; req.append("requires_review")
    return {"type": "object", "properties": props, "required": req, "additionalProperties": False}


def prompts():
    p81 = book_prompt()
    chapter = p81 + "\n\n<document>\n{doc}\n</document>" if "{doc}" not in p81 else p81
    return {"plain": (PLAIN, False, False), "chapter": (chapter, False, False),
            "graded": (chapter + GRADED_SUFFIX, True, False), "evidence": (chapter + EVIDENCE_SUFFIX, True, True)}


STREET_OF = dict(zip(COMPANIES, STREETS))


def names(company):
    return (company.lower(), STREET_OF[company].lower())


def judge(value, truth, role):
    if value is None or not str(value).strip():
        return "empty"
    v = str(value).lower()
    if any(n in v for n in names(truth[role])):
        return "correct"
    for other in ROLES:
        if other != role and any(n in v for n in names(truth[other])):
            return "misplaced"
    return "other"


def main() -> int:
    args = base_args(__doc__).parse_args()
    llm = LLM(HERE, model=args.model, live=args.live)
    docs = make_docs()
    P = prompts()
    print(f"{len(docs)} generated shipping documents, {PER_LEVEL} per level, {len(ROLES)} address fields each\n")
    out = {}
    for name, (system, graded, evidence) in P.items():
        for run in RUNS:
            for i, d in enumerate(docs):
                out[(name, run, i)] = llm.json(system=system.replace("{doc}", d["text"]),
                                               user="Fill in the fields.", schema=schema(graded, evidence), max_tokens=1200, sample=run)
    print(f"{'prompt':8} {'level':>5} {'run':>3} {'correct':>8} {'misplaced':>10} {'empty':>6} {'other':>6}   (of {PER_LEVEL * 3} fields)")
    grade_stats = {}
    ev = {}
    for name in P:
        for level in (1, 2, 3, 4):
            for run in RUNS:
                c = m = e = o = 0
                for i, d in enumerate(docs):
                    if d["level"] != level:
                        continue
                    r = out[(name, run, i)]
                    for role in ROLES:
                        f = r[FIELDS[role]]
                        verdict = judge(f.get("value"), d["truth"], role)
                        c += verdict == "correct"; m += verdict == "misplaced"; e += verdict == "empty"; o += verdict == "other"
                        if name == "evidence":
                            k = (level, bool(f.get("role_stated")), verdict == "correct")
                            ev[k] = ev.get(k, 0) + 1
                            if r.get("requires_review"):
                                ev[("review", level)] = ev.get(("review", level), 0) + 1
                        if name == "graded":
                            g = f.get("placement_confidence")
                            grade_stats.setdefault((g, verdict == "correct"), 0); grade_stats[(g, verdict == "correct")] += 1
                            if r.get("requires_review"):
                                grade_stats.setdefault(("review", verdict == "correct"), 0); grade_stats[("review", verdict == "correct")] += 1
                print(f"{name:8} {level:>5} {run:>3} {c:>8} {m:>10} {e:>6} {o:>6}")
        print()
    print(">> Graded prompt: does the grade track the errors?  (fields, all levels, all runs)")
    for g in ("HIGH", "MEDIUM", "LOW"):
        ok = grade_stats.get((g, True), 0); bad = grade_stats.get((g, False), 0)
        print(f"   {g:6}  on correct fields: {ok:>4}   on wrong or empty fields: {bad:>4}")
    print(f"   requires_review set: on records with a correct field {grade_stats.get(('review', True), 0)}, "
          f"with a wrong or empty field {grade_stats.get(('review', False), 0)}")
    print("\n>> Evidence prompt: did the model say the document states the role?  (fields, 3 runs; of 108 per level)")
    for level in (1, 2, 3, 4):
        print(f"   L{level}: role_stated=true on correct {ev.get((level, True, True), 0):>3}, on wrong/empty {ev.get((level, True, False), 0):>3}"
              f"   role_stated=false on correct {ev.get((level, False, True), 0):>3}, on wrong/empty {ev.get((level, False, False), 0):>3}"
              f"   requires_review set on {ev.get(('review', level), 0) // 3:>2} of 36 records")
    llm.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
