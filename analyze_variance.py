"""Compare repeated runs of the same corpus under identical settings.

A single pass gives you one number with no error bar. This reports the spread,
and more usefully, which individual findings are stable across runs and which
appear once and vanish. A defect that only shows up in one run of three is noise
and should not be anyone's headline.
"""
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from citecheck.labels import diff, load_labels
from citecheck.schema import QuoteExtraction

runs = sorted(Path("data").glob("variance_run*.jsonl"))
labels = load_labels()

per_run = []
finding_seen = defaultdict(set)     # (filing, field, defect) -> which runs
claim_seen = defaultdict(set)       # (filing, field) -> which runs
counts_seen = defaultdict(list)     # filing -> weakness counts per run

for index, path in enumerate(runs):
    fields = bad = clean = 0
    wrong = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if "extraction" not in record:
            continue
        name = record["company"].split("(")[0].strip()[:26]
        extraction = QuoteExtraction.model_validate(record["extraction"])
        fields += 4 + 2 * len(extraction.material_weaknesses)
        findings = record.get("findings", [])
        bad += len(findings)
        clean += not findings
        for f in findings:
            finding_seen[(name, f["field"], f["defect"])].add(index)

        counts_seen[name].append(len([
            w for w in extraction.material_weaknesses
            if w.remediation_status.value.value != "REMEDIATED"
        ]))
        mismatches = diff(extraction, labels.get(record["text_file"], {}))
        wrong += bool(mismatches)
        for m in mismatches:
            claim_seen[(name, m.field)].add(index)

    per_run.append({"file": path.name, "fields": fields, "findings": bad,
                    "clean": clean, "wrong": wrong,
                    "integrity": 1 - bad / fields})

print(f"{len(runs)} runs, identical settings\n")
print(f"{'run':22} {'fields':>7} {'findings':>9} {'clean':>6} {'wrong claims':>13} {'integrity':>10}")
for r in per_run:
    print(f"{r['file']:22} {r['fields']:>7} {r['findings']:>9} {r['clean']:>6} "
          f"{r['wrong']:>13} {r['integrity']:>9.1%}")

if len(per_run) > 1:
    vals = [r["integrity"] for r in per_run]
    print(f"\nintegrity: mean {statistics.mean(vals):.1%}, "
          f"range {min(vals):.1%} to {max(vals):.1%}, "
          f"spread {max(vals) - min(vals):.1%}")
    cl = [r["clean"] for r in per_run]
    wr = [r["wrong"] for r in per_run]
    print(f"clean filings: {min(cl)} to {max(cl)} of 30")
    print(f"filings with a wrong claim: {min(wr)} to {max(wr)} of 30")

stability = Counter(len(v) for v in finding_seen.values())
print(f"\ncitation findings by how many runs they appear in (of {len(runs)}):")
for n in sorted(stability, reverse=True):
    print(f"  {n}/{len(runs)} runs: {stability[n]} findings"
          + ("   <- reproducible" if n == len(runs) else
             "   <- noise" if n == 1 else ""))

print(f"\nclaim errors by how many runs they appear in:")
for key, seen in sorted(claim_seen.items(), key=lambda kv: -len(kv[1])):
    name, field = key
    print(f"  {len(seen)}/{len(runs)}  {name:28} {field}")

unstable = {k: v for k, v in counts_seen.items() if len(set(v)) > 1}
if unstable:
    print(f"\nfilings where the open-weakness count changed between runs:")
    for name, vals in unstable.items():
        print(f"  {name:28} {vals}")
else:
    print("\nopen-weakness counts were identical across all runs")
