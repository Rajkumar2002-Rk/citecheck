"""Hand-labeled ground truth, and the diff against it.

Nothing in this module may consult a model. The labels are the only
independent measurement in the project: gates calibrated against model output
can only tell you the gate agrees with the model, and the defect taxonomy
cannot distinguish C from D without knowing whether the claim is actually true.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .corpus import DATA, MANIFEST, TEXT
from .schema import AuditorOpinion, ControlFramework

LABELS = DATA / "labels.csv"

# One row per filing. Weaknesses are a count plus a semicolon-joined summary:
# free-text descriptions are not comparable across labeler and model, so the
# diff scores the count and the effectiveness/framework/auditor fields, which
# are enum-valued and unambiguous.
COLUMNS = [
    "text_file",
    "company",
    "disclosure_controls_effective",   # true / false
    "icfr_effective",                  # true / false
    "material_weakness_count",         # integer
    "material_weakness_summary",       # free text, semicolon-separated, for review only
    "control_framework",               # COSO_2013 / COSO_1992 / OTHER / NOT_STATED
    "auditor_opinion",                 # UNQUALIFIED / ADVERSE / NOT_REQUIRED / CROSS_REFERENCED / ABSENT
    "auditor_name",                    # blank if none stated
    "notes",                           # anything ambiguous; read this before trusting a diff
]

SCORED = [
    "disclosure_controls_effective",
    "icfr_effective",
    "material_weakness_count",
    "control_framework",
    "auditor_opinion",
]


def write_template(force: bool = False) -> Path:
    """Emit a CSV pre-filled with filing identifiers and blank label columns."""
    if LABELS.exists() and not force:
        raise FileExistsError(f"{LABELS} already exists; pass force=True to overwrite")
    filings = json.loads(MANIFEST.read_text())["filings"]
    with LABELS.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for filing in filings:
            writer.writerow({"text_file": filing["text_file"], "company": filing["company"]})
    return LABELS


def load_labels() -> dict[str, dict]:
    rows = {}
    with LABELS.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not any((row.get(c) or "").strip() for c in SCORED):
                continue  # unlabeled row
            rows[row["text_file"]] = row
    return rows


def _norm_bool(raw: str) -> bool | None:
    value = (raw or "").strip().lower()
    if value in {"true", "t", "yes", "y", "1"}:
        return True
    if value in {"false", "f", "no", "n", "0"}:
        return False
    return None


@dataclass
class Mismatch:
    field: str
    labeled: object
    extracted: object

    def as_dict(self) -> dict:
        return {"field": self.field, "labeled": self.labeled, "extracted": self.extracted}


def diff(record, label: dict) -> list[Mismatch]:
    """Compare an extraction against one hand-labeled row.

    A mismatch here means the CLAIM is wrong, which is what separates defect
    types C and D: if the claim is wrong and the citation nonetheless resolved
    and passed the support check, the model fabricated support for a false
    statement (D). If the claim is right but a citation gate fired, it cited the
    wrong place for a true statement (C).
    """
    out: list[Mismatch] = []

    for field in ("disclosure_controls_effective", "icfr_effective"):
        expected = _norm_bool(label.get(field, ""))
        if expected is None:
            continue
        actual = getattr(record, field).value
        if actual != expected:
            out.append(Mismatch(field, expected, actual))

    raw_count = (label.get("material_weakness_count") or "").strip()
    if raw_count.isdigit():
        expected_count = int(raw_count)
        actual_count = len(record.material_weaknesses)
        if actual_count != expected_count:
            out.append(Mismatch("material_weakness_count", expected_count, actual_count))

    raw_framework = (label.get("control_framework") or "").strip().upper()
    if raw_framework in ControlFramework.__members__:
        actual = record.control_framework.value.value
        if actual != raw_framework:
            out.append(Mismatch("control_framework", raw_framework, actual))

    raw_opinion = (label.get("auditor_opinion") or "").strip().upper()
    if raw_opinion in AuditorOpinion.__members__:
        actual = record.auditor_opinion.value.value
        if actual != raw_opinion:
            out.append(Mismatch("auditor_opinion", raw_opinion, actual))

    return out


def classify(mismatches: list[Mismatch], citation_findings: list) -> str:
    """Assign the defect type for one field-level outcome."""
    claim_wrong = bool(mismatches)
    citation_bad = bool(citation_findings)
    if claim_wrong:
        # Wrong claim. Whether or not a gate fired, the citation accompanying it
        # points at text that cannot support it -- that is type D. The subtype
        # is worth keeping: a D the gates caught is recoverable, a D that passed
        # every gate is the one an audit workflow would ship.
        return "D_FABRICATED_TO_MATCH" if citation_bad else "D_UNDETECTED"
    if citation_bad:
        return "C_WRONG_LOCATION"
    return "CLEAN"


def read_rows() -> list[dict]:
    """All rows, labeled or not, in manifest order."""
    with LABELS.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def is_labeled(row: dict) -> bool:
    return any((row.get(c) or "").strip() for c in SCORED)


def save_row(text_file: str, values: dict) -> None:
    """Update one row in place, leaving every other row untouched."""
    rows = read_rows()
    for row in rows:
        if row["text_file"] == text_file:
            row.update(values)
            break
    else:
        raise KeyError(text_file)
    with LABELS.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
