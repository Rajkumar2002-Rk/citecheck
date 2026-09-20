"""Quote-mode pass with prompt v2 (adds the remediation rule). Same corpus."""
import json, os, sys
from pathlib import Path

import anthropic

from citecheck.corpus import TEXT, MANIFEST
from citecheck.extract import extract
from citecheck.gates import run_gates

OUT = Path("data/quote_v2.jsonl")
LOCK = Path("data/.v2_run.lock")
if LOCK.exists():
    try:
        os.kill(int(LOCK.read_text().strip()), 0)
        sys.exit("a v2 run is already active")
    except (ProcessLookupError, ValueError):
        pass
LOCK.write_text(str(os.getpid()))

done = set()
if OUT.exists():
    done = {json.loads(l)["text_file"] for l in OUT.read_text().splitlines()
            if l.strip() and "extraction" in json.loads(l)}

try:
    filings = json.loads(MANIFEST.read_text())["filings"]
    client = anthropic.Anthropic()
    with OUT.open("a") as out:
        for i, f in enumerate(filings, 1):
            if f["text_file"] in done:
                continue
            text = (TEXT / f["text_file"]).read_text()
            a = extract(client, text, mode="quote", version=2)
            rec = {"company": f["company"], "text_file": f["text_file"],
                   "length": f["length"], "error": a.error, "stop": a.stop_reason,
                   "in": a.input_tokens, "out": a.output_tokens, "sec": round(a.seconds, 1)}
            if a.error and "credit balance" in (a.error or ""):
                print("STOPPING: out of credits", flush=True)
                break
            if a.parsed is not None:
                r = run_gates(a.parsed, text, mode="quote")
                rec["extraction"] = a.parsed.model_dump(mode="json")
                rec["findings"] = [x.as_dict() for x in r.findings]
                rec["passed"] = r.passed
            out.write(json.dumps(rec) + "\n"); out.flush()
            tag = "FAILED" if a.parsed is None else f"mw={len(rec['extraction']['material_weaknesses'])}"
            print(f"[{i}/{len(filings)}] {f['company'].split('(')[0].strip()[:26]:28} {tag}", flush=True)
    print("DONE", flush=True)
finally:
    LOCK.unlink(missing_ok=True)
