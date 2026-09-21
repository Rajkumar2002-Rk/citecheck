"""Same corpus, same prompt, same gates, different model.

The point is narrow: the undated-COSO failure is the one model error that
repeats, and it has only ever been observed on one model. If a second model does
the same thing it is a family trait. If it doesn't, the finding is about Opus and
should say so.
"""
import json
from pathlib import Path

from citecheck.labels import diff, load_labels
from citecheck.schema import QuoteExtraction

RATES = {  # per million tokens, input / output
    "claude-opus-5": (5, 25),
    "claude-sonnet-5": (2, 10),
}
COSO_FILINGS = ("NETLIST", "JAAG")

labels = load_labels()


def summarise(path, label):
    fields = bad = clean = 0
    tin = tout = secs = 0.0
    wrong, coso = [], {}
    model = None
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "extraction" not in r:
            continue
        model = r.get("model", "claude-opus-5")
        name = r["company"].split("(")[0].strip()[:26]
        rec = QuoteExtraction.model_validate(r["extraction"])
        fields += 4 + 2 * len(rec.material_weaknesses)
        findings = r.get("findings", [])
        bad += len(findings)
        clean += not findings
        tin += r.get("in", 0); tout += r.get("out", 0); secs += r.get("sec", 0)
        ms = diff(rec, labels.get(r["text_file"], {}))
        if ms:
            wrong.append((name, [(m.field, m.labeled, m.extracted) for m in ms]))
        if any(k in name.upper() for k in COSO_FILINGS):
            coso[name] = rec.control_framework.value.value
    rin, rout = RATES.get(model, (5, 25))
    return {"label": label, "model": model, "fields": fields, "findings": bad,
            "clean": clean, "integrity": 1 - bad / fields, "wrong": wrong,
            "coso": coso, "cost": tin * rin / 1e6 + tout * rout / 1e6,
            "min": secs / 60, "out_tokens": int(tout)}


rows = [summarise("data/quote_pass1.jsonl", "Opus 5"),
        summarise("data/sonnet_run1.jsonl", "Sonnet 5")]

print(f"{'':12} {'model':18} {'integrity':>10} {'clean':>7} {'wrong':>7} "
      f"{'out tok':>9} {'cost':>7} {'min':>5}")
for r in rows:
    print(f"{r['label']:12} {r['model']:18} {r['integrity']:>9.1%} "
          f"{r['clean']:>4}/30 {len(r['wrong']):>4}/30 {r['out_tokens']:>9,} "
          f"${r['cost']:>6.2f} {r['min']:>5.0f}")

print("\nundated COSO filings (correct answer is OTHER):")
for r in rows:
    for name, value in sorted(r["coso"].items()):
        mark = "correct" if value == "OTHER" else "WRONG"
        print(f"  {r['label']:12} {name:28} {value:12} {mark}")

for r in rows:
    print(f"\n{r['label']} claim errors ({len(r['wrong'])}):")
    for name, ms in r["wrong"]:
        print("  " + f"{name:28} " + "; ".join(
            f"{f}: label={l} model={e}" for f, l, e in ms))
