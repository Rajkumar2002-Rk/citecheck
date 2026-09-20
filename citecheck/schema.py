"""Typed record the LLM must produce for each Item 9A section.

Every substantive field is wrapped in Cited[...], so a value cannot be stated
without provenance. That is deliberate: a schema that lets the model answer
without citing gives it a way to dodge the experiment.

Two citation shapes, run as an A/B condition:

  SpanCitation  - the model emits character offsets itself.
  QuoteCitation - the model emits only the quoted snippet and the harness
                  resolves offsets by exact search.

The difference between the two failure rates separates "the model invented
support" from "the model cannot count characters". Only the first is a finding
worth putting in front of an auditor.
"""
from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")
C = TypeVar("C", bound=BaseModel)


class QuoteCitation(BaseModel):
    """Condition B: snippet only; the harness computes the span."""

    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=1, description="Text copied exactly from the source.")


class SpanCitation(BaseModel):
    """Condition A: the model asserts the offsets, 0-based, end-exclusive."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0, description="Character offset where the support begins.")
    end: int = Field(gt=0, description="Character offset one past the end of the support.")
    quote: str = Field(min_length=1, description="Text at [start, end), copied exactly.")

    @model_validator(mode="after")
    def _ordered(self) -> "SpanCitation":
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be greater than start ({self.start})")
        return self


class Cited(BaseModel, Generic[T, C]):
    model_config = ConfigDict(extra="forbid")

    value: T
    citation: C


class ControlFramework(str, Enum):
    COSO_2013 = "COSO_2013"
    COSO_1992 = "COSO_1992"
    OTHER = "OTHER"
    NOT_STATED = "NOT_STATED"


class AuditorOpinion(str, Enum):
    UNQUALIFIED = "UNQUALIFIED"            # auditor concluded ICFR effective
    ADVERSE = "ADVERSE"                    # auditor concluded ICFR not effective
    NOT_REQUIRED = "NOT_REQUIRED"          # filer exempt from SOX 404(b)
    CROSS_REFERENCED = "CROSS_REFERENCED"  # opinion exists but outside Item 9A
    ABSENT = "ABSENT"                      # no mention at all


class RemediationStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"      # nothing to remediate
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    REMEDIATED = "REMEDIATED"              # resolved as of the balance-sheet date
    NOT_STATED = "NOT_STATED"


class MaterialWeakness(BaseModel, Generic[C]):
    model_config = ConfigDict(extra="forbid")

    description: Cited[str, C]
    remediation_status: Cited[RemediationStatus, C]


class Item9AExtraction(BaseModel, Generic[C]):
    """One record per filing."""

    model_config = ConfigDict(extra="forbid")

    disclosure_controls_effective: Cited[bool, C]
    icfr_effective: Cited[bool, C]
    material_weaknesses: list[MaterialWeakness[C]] = Field(default_factory=list)
    control_framework: Cited[ControlFramework, C]
    auditor_name: Cited[str, C] | None = None
    auditor_opinion: Cited[AuditorOpinion, C]


SpanExtraction = Item9AExtraction[SpanCitation]
QuoteExtraction = Item9AExtraction[QuoteCitation]
