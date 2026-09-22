"""Does reading a scan instead of the file change what the model gets right?

The resolver answers whether a citation can still be located after a scan. This
answers the different question of whether the facts survive, judged against the
same hand labels, on the same 30 documents.

The failure worth looking for is the one that cannot happen on clean input: a
citation that resolves cleanly into text OCR got wrong. Quote matches, offsets
correct, underlying document says something else, and no gate sees a problem.
"""
import json
import re
from pathlib import Path

from citecheck.corpus import TEXT
from citecheck.gates import run_gates
from citecheck.labels import diff, load_labels
from citecheck.resolve import resolve
from citecheck.schema import QuoteExtraction

OCR = Path("data/text_ocr")
labels = load_labels()


def summarise(path, source, tolerant):
    fields = bad = clean = 0
    wrong = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "extraction" not in r:
            continue
        text = (source / r["text_file"]).read_text(encoding="utf-8")
        rec = QuoteExtraction.model_validate(r["extraction"])
        res = run_gates(rec, text, mode="quote", tolerant=tolerant)
        fields += 4 + 2 * len(rec.material_weaknesses)
        bad += len(res.findings)
        clean += not res.findings
        ms = diff(rec, labels.get(r["text_file"], {}))
        if ms:
            wrong.append((r["company"].split("(")[0].strip()[:24],
                          [(m.field, m.labeled, m.extracted) for m in ms]))
    return fields, bad, clean, wrong


rows = [("clean text", *summarise("data/quote_pass1.jsonl", TEXT, False)),
        ("OCR text", *summarise("data/ocr_run1.jsonl", OCR, True))]

print(f"{'source':12} {'fields':>7} {'findings':>9} {'clean':>7} {'integrity':>10} {'wrong claims':>13}")
for label, fields, bad, clean, wrong in rows:
    print(f"{label:12} {fields:>7} {bad:>9} {clean:>4}/30 {1 - bad/fields:>9.1%} {len(wrong):>10}/30")

for label, _, _, _, wrong in rows:
    print(f"\n{label} claim errors:")
    for name, ms in wrong:
        print("  " + f"{name:26} " + "; ".join(f"{a}: label={b} model={c}" for a, b, c in ms))

# The new failure: citation resolves in the OCR text but that text is corrupt.
print("\ncitations that resolve in OCR but differ from the clean document:")
shown = 0
for line in Path("data/ocr_run1.jsonl").read_text().splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    if "extraction" not in r:
        continue
    clean_text = (TEXT / r["text_file"]).read_text(encoding="utf-8")
    for field in ("disclosure_controls_effective", "icfr_effective",
                  "control_framework", "auditor_opinion"):
        cited = r["extraction"].get(field)
        if not isinstance(cited, dict):
            continue
        quote = cited["citation"]["quote"]
        if resolve(quote, clean_text) is None:
            print(f"  {r['company'].split('(')[0].strip()[:24]:26} {field:30}")
            print(f"      {quote[:100]!r}")
            shown += 1
print(f"  ({shown} found)" if shown else "  none: every quote also traces to the clean document")
