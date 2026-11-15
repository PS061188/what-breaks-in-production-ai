"""Experiment 10.10 — the not_extracted field, verified by code (fix 4's deterministic half).

Prachi's question (14 Oct 2026): the field is an engineering fix, so should it
not be checked through code, where results are deterministic? The schema half
already is deterministic (a reply without the field fails validation). The
field's content is model-written, so the deterministic thing code can add is
verification: every entry the model claims it "considered and left out" must
trace back to the source document. An entry that names a value or item the
source never states is the model inventing its own leftovers.

This probe replays every recorded reply of Experiment 10.7 (as-printed and
narrowed, three runs each: 360 replies, no model calls) and checks each
not_extracted entry against its dialogue, strictest test first:

  verbatim        every number in the entry appears in the dialogue as digits,
                  and the entry's item words appear there too
  spoken/unit     a number appears only in spoken form ("two . five",
                  "five hundred") or the entry added a unit the dialogue
                  does not state next to the number
  name only       the entry names no number; its content words appear
  NOT TRACED      something in the entry appears nowhere in the dialogue

Every NOT TRACED entry is printed in full and must be read; the classes are
the checker's claim until they are. The same test runs over the `extracted`
list, where an untraced item is a fabricated extraction rather than a
fabricated leftover.

    python3 probe_field_codecheck.py            # replay, prints per-condition table
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "exp105_dialogue_doses"))
sys.path.insert(0, str(HERE.parent))
from shared.cli_defaults import SUFFIX  # noqa: E402

from probe_field_conversation import load_dialogues, doses_in, stated_without_unit  # noqa: E402

FIXTURES = HERE / ("fixtures_field_conversation" + SUFFIX)
STOP = set("""the a an and or of for with without from into onto over under to in on at by as is are was were
be been than then that this these those it its his her their there not no none any some but if when
while during after before patient doctor medication medications medicine drug dose doses amount amounts
specified mentioned provided stated given document prescribed taking takes took daily currently""".split())


def content_words(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z'&-]{2,}", str(text).lower()) if w not in STOP}


def numbers_in(text: str) -> set:
    """Numbers incl. transcript forms like '.5'; normalised (no commas, no leading zero on decimals)."""
    out=set()
    for n in re.findall(r"(?:\d+(?:[.,]\d+)?|\.\d+)", str(text)):
        n=n.replace(",","")
        out.add(n[1:] if n.startswith("0.") else n)
    return out


_ONES=["","one","two","three","four","five","six","seven","eight","nine","ten","eleven","twelve",
       "thirteen","fourteen","fifteen","sixteen","seventeen","eighteen","nineteen"]
_TENS=["","","twenty","thirty","forty","fifty","sixty","seventy","eighty","ninety"]

def spoken_variants(n: str) -> list:
    """Transcript spellings of a number: 'a thousand', 'seven and a half', 'one fifty', 'point five'."""
    try: x=float(n)
    except ValueError: return []
    forms=[]
    if x==int(x):
        v=int(x)
        if v<20: forms.append(_ONES[v])
        elif v<100: forms.append(_TENS[v//10]+((" "+_ONES[v%10]) if v%10 else ""))
        elif v<1000:
            h,r=divmod(v,100)
            tail=(_TENS[r//10]+((" "+_ONES[r%10]) if r%10 else "")) if r>=20 else _ONES[r]
            forms+= [f"{_ONES[h]} hundred"+(f" and {tail}" if r else ""), f"a hundred"+(f" and {tail}" if r else "")]
            if r and r%10==0:
                forms.append(f"{_ONES[h]} {_TENS[r//10]}")            # "one fifty"
                forms.append(f"{_ONES[h]} {_TENS[r//10][:-1]}ies")    # "one thirties"
        elif v%1000==0 and v//1000<20:
            k=v//1000; forms+= [f"{_ONES[k]} thousand", "a thousand" if k==1 else ""]
    else:
        whole=int(x); frac=str(x).split(".")[1]
        if frac=="5":
            forms+= [ (spoken_variants(str(whole))[0] if whole and spoken_variants(str(whole)) else "")+" and a half",
                      "and a half", "half a" if whole==0 else ""]
        forms+= ["point "+" ".join(_ONES[int(c)] if int(c) else "zero" for c in frac)]
    return [f.strip() for f in forms if f and f.strip()]


def trace(entry_text: str, dialogue: str, truth) -> str:
    """How well one entry traces back to its dialogue."""
    t = str(entry_text)
    nums = numbers_in(t)
    dlg_nums = numbers_in(dialogue)
    words = content_words(t)
    dlg_low = dialogue.lower()
    words_found = sum(1 for w in words if w in dlg_low)
    words_ok = not words or words_found / len(words) >= 0.5
    if nums:
        if all(n in dlg_nums or n.replace(",", "") in {x.replace(",", "") for x in dlg_nums} for n in nums):
            return "verbatim" if words_ok else "NOT TRACED"
        canons = doses_in(t)
        if canons and stated_without_unit(canons, dialogue.lower()):
            return "spoken/unit"
        loose = {n for n in nums if n not in dlg_nums}
        if all(stated_without_unit({f"{n} mg"}, dialogue.lower())
               or any(v in dlg_low for v in spoken_variants(n)) for n in loose):
            return "spoken/unit"
        return "NOT TRACED"
    if not words:
        tokens=re.findall(r"[a-z0-9.]+", str(entry_text).lower())
        if tokens and all(tok in dlg_low for tok in tokens if tok not in STOP):
            return "name only"
        return "NOT TRACED"
    return "name only" if words_ok else "NOT TRACED"


def main() -> int:
    dialogues = {(d["split"], d["encounter_id"]): d["dialogue"] for d in load_dialogues()}
    for condition, root in [("as-printed", FIXTURES), ("narrowed", FIXTURES / "narrowed")]:
        print(f"\n=== {condition}")
        for sdir in sorted(root.glob("s*")):
            if not sdir.is_dir():
                continue
            field_c, extr_c = Counter(), Counter()
            not_traced = []
            for f in sorted(sdir.glob("*.json")):
                rec = json.loads(f.read_text())
                obj = rec.get("parsed")
                if obj is None:
                    continue
                dlg = dialogues[(rec["split"], rec["encounter_id"])]
                for e in obj.get("not_extracted") or []:
                    text = e.get("text", e) if isinstance(e, dict) else e
                    verdict = trace(text, dlg, None)
                    field_c[verdict] += 1
                    if verdict == "NOT TRACED":
                        reason = e.get("reason", "") if isinstance(e, dict) else ""
                        not_traced.append(("field", rec["encounter_id"], str(text)[:110], str(reason)[:90]))
                for item in obj.get("extracted") or []:
                    verdict = trace(item, dlg, None)
                    extr_c[verdict] += 1
                    if verdict == "NOT TRACED":
                        not_traced.append(("extracted", rec["encounter_id"], str(item)[:110], ""))
            def row(c):
                tot = sum(c.values())
                return (f"{tot:4} total: {c['verbatim']:3} verbatim, {c['spoken/unit']:3} spoken/unit-added, "
                        f"{c['name only']:3} name only, {c['NOT TRACED']:3} NOT TRACED")
            print(f"  run {sdir.name}: field   {row(field_c)}")
            print(f"  run {sdir.name}: extract {row(extr_c)}")
            for kind, enc, text, reason in not_traced:
                print(f"      [NOT TRACED · {kind}] {enc}: «{text}»" + (f" — {reason}" if reason else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
