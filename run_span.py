"""Full span-mode pass. Single instance enforced by a lockfile."""
import json, os, sys
from pathlib import Path

import anthropic

from citecheck.corpus import TEXT, MANIFEST
from citecheck.extract import extract
from citecheck.gates import run_gates

LOCK = Path("data/.span_run.lock")
if LOCK.exists():
    pid = LOCK.read_text().strip()
    try:
        os.kill(int(pid), 0)
        sys.exit(f"a span run is already active (pid {pid}); refusing to start a second")
    except (ProcessLookupError, ValueError):
        pass  # stale lock
LOCK.write_text(str(os.getpid()))

OUT = Path("data/span_pass1.jsonl")


def completed() -> set[str]:
    """Filings already extracted successfully, so a resume does not re-pay.

    A record with no extraction (truncation, credit exhaustion, API error) is
    not complete and will be retried.
    """
    if not OUT.exists():
        return set()
    done = set()
    for line in OUT.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if "extraction" in rec:
            done.add(rec["text_file"])
    return done


try:
    filings = json.loads(MANIFEST.read_text())["filings"]
    client = anthropic.Anthropic()
    already = completed()
    if already:
        print(f"resuming: {len(already)} filings already extracted, skipping them",
              flush=True)
    # Append, never truncate: re-running must not destroy completed work.
    with OUT.open("a") as out:
        for i, f in enumerate(filings, 1):
            if f["text_file"] in already:
                continue
            text = (TEXT / f["text_file"]).read_text()
            a = extract(client, text, mode="span")
            if a.error and "credit balance is too low" in a.error:
                # Every subsequent call will fail identically; burning through
                # the remaining filings just writes 16 useless error records.
                print("STOPPING: account is out of credits", flush=True)
                break
            rec = {"company": f["company"], "text_file": f["text_file"],
                   "length": f["length"], "error": a.error, "stop": a.stop_reason,
                   "in": a.input_tokens, "out": a.output_tokens, "sec": round(a.seconds, 1)}
            if a.parsed is not None:
                r = run_gates(a.parsed, text, mode="span")
                rec["extraction"] = a.parsed.model_dump(mode="json")
                rec["findings"] = [x.as_dict() for x in r.findings]
                rec["passed"] = r.passed
            out.write(json.dumps(rec) + "\n"); out.flush()
            tag = "FAILED" if a.parsed is None else f"find={len(rec['findings'])}"
            print(f"[{i}/{len(filings)}] {f['company'].split('(')[0].strip()[:28]:30} "
                  f"{f['length']:>6}ch out={a.output_tokens:>6} {a.seconds:>4.0f}s {tag}",
                  flush=True)
    print("DONE", flush=True)
finally:
    LOCK.unlink(missing_ok=True)
