"""Hand-labeled verdicts on individual citations.

Unused so far. A pass was started and abandoned: judging 190 citations one at a
time is tedious enough that the answers stop being considered, and a file of
unconsidered verdicts is worse than no file. Gate recall is measured by mutation
instead, in `mutate.py`. This is kept for a future sample-based pass, where a
careful 40 would be worth more than a careless 190.

The claim labels answer "is this field's value right". They say nothing about
whether the citation attached to it actually supports that value, so they cannot
measure gate recall: a gate that misses every bad citation still looks fine if
the claims happen to be correct.

This is the second, narrower labeling pass. One verdict per citation.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .corpus import DATA, TEXT

CITATION_LABELS = DATA / "citation_labels.csv"
COLUMNS = ["text_file", "company", "field", "value", "quote", "verdict", "note"]

GOOD = "good"          # the cited text states the claim
BAD = "bad"            # it does not
UNSURE = "unsure"      # excluded from both precision and recall


@dataclass
class Citation:
    text_file: str
    company: str
    field: str
    value: str
    quote: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.text_file, self.field)


def iter_citations(run: Path) -> list[Citation]:
    """Every citation in a run, in file order."""
    out: list[Citation] = []
    for line in run.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if "extraction" not in record:
            continue
        extraction = record["extraction"]
        company = record["company"].split("(")[0].strip()

        def add(field: str, cited: dict) -> None:
            out.append(Citation(record["text_file"], company, field,
                                str(cited["value"]), cited["citation"]["quote"]))

        for field in ("disclosure_controls_effective", "icfr_effective",
                      "control_framework", "auditor_opinion"):
            add(field, extraction[field])
        if extraction.get("auditor_name"):
            add("auditor_name", extraction["auditor_name"])
        for i, weakness in enumerate(extraction["material_weaknesses"]):
            add(f"material_weaknesses[{i}].description", weakness["description"])
            add(f"material_weaknesses[{i}].remediation_status",
                weakness["remediation_status"])
    return out


def load_verdicts() -> dict[tuple[str, str], dict]:
    if not CITATION_LABELS.exists():
        return {}
    with CITATION_LABELS.open(encoding="utf-8") as fh:
        return {(r["text_file"], r["field"]): r
                for r in csv.DictReader(fh) if (r.get("verdict") or "").strip()}


def save_verdict(citation: Citation, verdict: str, note: str = "") -> None:
    rows = {}
    if CITATION_LABELS.exists():
        with CITATION_LABELS.open(encoding="utf-8") as fh:
            rows = {(r["text_file"], r["field"]): r for r in csv.DictReader(fh)}
    rows[citation.key] = {
        "text_file": citation.text_file, "company": citation.company,
        "field": citation.field, "value": citation.value,
        "quote": citation.quote[:200], "verdict": verdict, "note": note,
    }
    with CITATION_LABELS.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows.values())


def context(citation: Citation, window: int = 260) -> str:
    """The cited text with a little of what surrounds it."""
    section = (TEXT / citation.text_file).read_text(encoding="utf-8")
    at = section.find(citation.quote)
    if at < 0:
        return "(quote not found in the section)"
    start, end = max(0, at - window), at + len(citation.quote) + window
    return section[start:end]
