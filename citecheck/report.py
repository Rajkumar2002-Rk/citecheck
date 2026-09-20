"""Aggregate run artifacts into the defect taxonomy.

Reports what the data supports and nothing more. Where the ground truth is
missing, types C and D are reported as UNADJUDICATED rather than folded into
another bucket -- a defect table that quietly counts unadjudicated findings as
type B would overstate exactly the number this project exists to measure.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .corpus import DATA, MANIFEST, TEXT
from .labels import LABELS, classify, diff, load_labels
from .schema import QuoteExtraction, SpanExtraction

SPAN_RUN = DATA / "span_pass1.jsonl"
QUOTE_RUN = DATA / "quote_pass1.jsonl"

MODELS = {"span": SpanExtraction, "quote": QuoteExtraction}


@dataclass
class ModeSummary:
    mode: str
    filings: int = 0
    clean_filings: int = 0
    cited_fields: int = 0
    type_a_arithmetic: int = 0
    type_a_fabricated: int = 0
    type_b: int = 0
    consistency: int = 0
    unverifiable: int = 0
    type_c: int = 0
    type_d_detected: int = 0
    type_d_undetected: int = 0
    unadjudicated: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    @property
    def cost_usd(self) -> float:
        return self.input_tokens * 5 / 1e6 + self.output_tokens * 25 / 1e6

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["cost_usd"] = round(self.cost_usd, 2)
        return d


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize(mode: str, labels: dict[str, dict]) -> ModeSummary:
    path = SPAN_RUN if mode == "span" else QUOTE_RUN
    summary = ModeSummary(mode=mode)

    for rec in _load(path):
        if "extraction" not in rec:
            continue  # API/budget failure; not a citation defect
        summary.filings += 1
        summary.input_tokens += rec.get("in", 0)
        summary.output_tokens += rec.get("out", 0)
        summary.seconds += rec.get("sec", 0.0)

        extraction = rec["extraction"]
        summary.cited_fields += 4 + 2 * len(extraction["material_weaknesses"])

        findings = rec.get("findings", [])
        if not findings:
            summary.clean_filings += 1
        for f in findings:
            if f["defect"] == "A_UNRESOLVABLE":
                if "offsets are wrong" in f["message"]:
                    summary.type_a_arithmetic += 1
                else:
                    summary.type_a_fabricated += 1
            elif f["defect"] == "B_UNSUPPORTED":
                summary.type_b += 1
            elif f["defect"] == "CONSISTENCY":
                summary.consistency += 1
            elif f["defect"] == "UNVERIFIABLE":
                summary.unverifiable += 1

        label = labels.get(rec["text_file"])
        if label is None:
            # No ground truth: C and D are undecidable for this filing.
            summary.unadjudicated += len(findings)
            continue

        record = MODELS[mode].model_validate(extraction)
        mismatches = diff(record, label)
        verdict = classify(mismatches, findings)
        if verdict == "C_WRONG_LOCATION":
            summary.type_c += 1
        elif verdict == "D_FABRICATED_TO_MATCH":
            summary.type_d_detected += 1
        elif verdict == "D_UNDETECTED":
            summary.type_d_undetected += 1

    return summary


def build() -> dict:
    labels = load_labels() if LABELS.exists() else {}
    summaries = {mode: summarize(mode, labels) for mode in ("span", "quote")}
    total_filings = len(json.loads(MANIFEST.read_text())["filings"])
    return {
        "corpus_filings": total_filings,
        "labeled_filings": len(labels),
        "modes": {m: s.as_dict() for m, s in summaries.items()},
    }
