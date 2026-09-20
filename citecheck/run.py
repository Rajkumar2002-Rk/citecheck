"""Extract, verify, repair, and log every attempt."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import anthropic

from .corpus import DATA, MANIFEST, TEXT
from .extract import extract
from .gates import run_gates

REPORT = DATA / "report.json"
MAX_ATTEMPTS = 3  # initial + 2 repairs


def run_one(client: anthropic.Anthropic, text: str, *, mode: str) -> dict:
    """One filing, one mode, with bounded gate-driven repair."""
    attempts: list[dict] = []
    repair: str | None = None

    for index in range(MAX_ATTEMPTS):
        attempt = extract(client, text, mode=mode, repair=repair)
        record = {
            "attempt": index,
            "mode": mode,
            "repair_given": repair,
            "error": attempt.error,
            "input_tokens": attempt.input_tokens,
            "output_tokens": attempt.output_tokens,
            "seconds": round(attempt.seconds, 2),
        }

        if attempt.parsed is None:
            attempts.append({**record, "findings": [], "passed": False})
            break

        result = run_gates(attempt.parsed, text, mode=mode)
        record["extraction"] = attempt.parsed.model_dump(mode="json")
        record["findings"] = [f.as_dict() for f in result.findings]
        record["passed"] = result.passed
        attempts.append(record)

        if result.passed:
            break
        repair = result.repair_prompt()

    return {"mode": mode, "attempts": attempts, "passed": attempts[-1]["passed"]}


def run_corpus(modes: tuple[str, ...] = ("span", "quote"), limit: int | None = None,
               progress=None) -> dict:
    filings = json.loads(MANIFEST.read_text())["filings"]
    if limit:
        filings = filings[:limit]

    client = anthropic.Anthropic()
    results = []
    for filing in filings:
        text = (TEXT / filing["text_file"]).read_text(encoding="utf-8")
        entry = {"company": filing["company"], "accession": filing["accession"],
                 "text_file": filing["text_file"], "length": filing["length"], "runs": {}}
        for mode in modes:
            entry["runs"][mode] = run_one(client, text, mode=mode)
            if progress:
                progress(filing, mode, entry["runs"][mode])
        results.append(entry)

    report = {"model": __import__("citecheck.extract", fromlist=["MODEL"]).MODEL,
              "modes": list(modes), "filings": results}
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
