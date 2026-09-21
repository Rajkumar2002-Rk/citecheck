"""Did giving the model a NOT_STATED option help, or did it just get used everywhere?

Two filings in the corpus genuinely lack a conclusion inside Item 9A. One points
to a page outside the section for management's report; the other defines
disclosure controls and never concludes anything. Everything else states its
answer plainly. So the good outcome is narrow: NOT_STATED on those two fields and
nowhere else.
"""
import json
from pathlib import Path

from citecheck.labels import load_labels, diff
from citecheck.schema import Effectiveness, QuoteExtraction

EXPECTED = {  # the two known gaps, by company prefix and field
    ("CubeSmart", "icfr_effective"),
    ("MARKY", "disclosure_controls_effective"),
}

labels = load_labels()
used, correct_gap, other = [], [], []
fields = bad = clean = 0
wrong = []

for line in Path("data/enum_run1.jsonl").read_text().splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    if "extraction" not in r:
        continue
    name = r["company"].split("(")[0].strip()
    rec = QuoteExtraction.model_validate(r["extraction"])
    fields += 4 + 2 * len(rec.material_weaknesses)
    findings = r.get("findings", [])
    bad += len(findings)
    clean += not findings

    for field in ("icfr_effective", "disclosure_controls_effective"):
        if getattr(rec, field).value is Effectiveness.NOT_STATED:
            used.append((name, field))
            hit = any(name.startswith(c) and field == f for c, f in EXPECTED)
            (correct_gap if hit else other).append((name, field))

    ms = diff(rec, labels.get(r["text_file"], {}))
    if ms:
        wrong.append((name[:26], [(m.field, m.labeled, m.extracted) for m in ms]))

print(f"citation integrity {1 - bad / fields:.1%}  ({fields} fields, {bad} findings)")
print(f"clean filings {clean}/30\n")

print(f"NOT_STATED used {len(used)} times")
print(f"  on the two known gaps: {len(correct_gap)}/2")
for n, f in correct_gap:
    print(f"    hit    {n[:30]:32} {f}")
missed = EXPECTED - {(c, f) for c, f in EXPECTED
                     if any(n.startswith(c) and f == ff for n, ff in correct_gap)}
for c, f in sorted(missed):
    print(f"    missed {c:32} {f}")
print(f"  anywhere else: {len(other)}")
for n, f in other:
    print(f"    extra  {n[:30]:32} {f}")

print(f"\nclaim errors vs labels: {len(wrong)}/30")
for n, ms in wrong:
    print("  " + f"{n:28} " + "; ".join(f"{a}: label={b} model={c}" for a, b, c in ms))
