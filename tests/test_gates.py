"""One test per gate behaviour, anchored in real filing text.

The fixtures are real Item 9A sections; the records are constructed by hand so
each test isolates a single gate decision. Records captured from actual model
runs are pinned in test_captured_failures.py once a full run exists.
"""
import pytest

from citecheck.gates import Defect, gate_consistency, run_gates
from citecheck.schema import (
    AuditorOpinion, Cited, ControlFramework, Item9AExtraction, MaterialWeakness,
    QuoteCitation, RemediationStatus, SpanCitation,
)
from citecheck.sections import find_item_9a
from citecheck.textify import html_to_text


@pytest.fixture(scope="session")
def avdx_9a(avdx_html):
    return find_item_9a(html_to_text(avdx_html)).text


@pytest.fixture(scope="session")
def bglc_9a(bglc_html):
    return find_item_9a(html_to_text(bglc_html)).text


def quote_record(**overrides):
    """A record that is correct for AvidXchange unless overridden."""
    base = dict(
        disclosure_controls_effective=Cited[bool, QuoteCitation](
            value=True,
            citation=QuoteCitation(quote="our disclosure controls and procedures were effective")),
        icfr_effective=Cited[bool, QuoteCitation](
            value=True,
            citation=QuoteCitation(
                quote="our internal control over financial reporting as of December 31, 2024 was effective")),
        control_framework=Cited[ControlFramework, QuoteCitation](
            value=ControlFramework.COSO_2013,
            citation=QuoteCitation(
                quote="Internal Control - Integrated Framework (2013) issued by the Committee of Sponsoring Organizations of the Treadway Commission")),
        auditor_opinion=Cited[AuditorOpinion, QuoteCitation](
            value=AuditorOpinion.CROSS_REFERENCED,
            citation=QuoteCitation(
                quote="as stated in their report set forth in the F pages after Item 16")),
    )
    base.update(overrides)
    return Item9AExtraction[QuoteCitation](**base)


def test_correct_record_passes_cleanly(avdx_9a):
    # False positives are the thing that would kill this project: a gate that
    # flags correct extractions makes every rate meaningless.
    result = run_gates(quote_record(), avdx_9a, mode="quote")
    assert result.passed, [f.as_dict() for f in result.findings]


def test_fabricated_quote_is_type_a(avdx_9a):
    record = quote_record(icfr_effective=Cited[bool, QuoteCitation](
        value=True,
        citation=QuoteCitation(quote="management concluded that all controls were flawless")))
    result = run_gates(record, avdx_9a, mode="quote")
    assert [f.defect for f in result.findings] == [Defect.A_UNRESOLVABLE]


def test_wrong_offsets_with_real_quote_is_type_a(avdx_9a):
    quote = "our internal control over financial reporting as of December 31, 2024 was effective"
    real = avdx_9a.index(quote)
    record = Item9AExtraction[SpanCitation](
        disclosure_controls_effective=Cited[bool, SpanCitation](
            value=True, citation=SpanCitation(start=0, end=10, quote=avdx_9a[:10])),
        icfr_effective=Cited[bool, SpanCitation](
            value=True,
            citation=SpanCitation(start=real + 40, end=real + 40 + len(quote), quote=quote)),
        control_framework=Cited[ControlFramework, SpanCitation](
            value=ControlFramework.NOT_STATED,
            citation=SpanCitation(start=0, end=10, quote=avdx_9a[:10])),
        auditor_opinion=Cited[AuditorOpinion, SpanCitation](
            value=AuditorOpinion.CROSS_REFERENCED,
            citation=SpanCitation(start=0, end=10, quote=avdx_9a[:10])),
    )
    result = run_gates(record, avdx_9a, mode="span")
    offsets = [f for f in result.findings if f.field == "icfr_effective"]
    assert offsets and offsets[0].defect is Defect.A_UNRESOLVABLE
    assert "offsets are wrong" in offsets[0].message


def test_definitional_boilerplate_is_type_b(avdx_9a):
    # Real text, topically perfect, supports nothing: it defines internal
    # control rather than assessing this company's.
    record = quote_record(icfr_effective=Cited[bool, QuoteCitation](
        value=True,
        citation=QuoteCitation(
            quote="no evaluation of controls can provide absolute assurance")))
    result = run_gates(record, avdx_9a, mode="quote")
    findings = [f for f in result.findings if f.field == "icfr_effective"]
    assert findings and findings[0].defect is Defect.B_UNSUPPORTED
    assert "boilerplate" in findings[0].message


def test_retracted_weakness_is_type_b(bglc_9a):
    # The money case. BioNexus lists segregation-of-duties bullets, then says
    # two sentences later that the basis was inaccurate. Citing the bullets
    # resolves perfectly and reads plausibly to a skimming human.
    quote = "We were unable to maintain segregation of duties within our business operations"
    assert quote in bglc_9a
    weakness = MaterialWeakness[QuoteCitation](
        description=Cited[str, QuoteCitation](
            value="Insufficient segregation of duties", citation=QuoteCitation(quote=quote)),
        remediation_status=Cited[RemediationStatus, QuoteCitation](
            value=RemediationStatus.NOT_STATED, citation=QuoteCitation(quote=quote)),
    )
    result = run_gates(quote_record(material_weaknesses=[weakness]), bglc_9a, mode="quote")
    hits = [f for f in result.findings if f.field.startswith("material_weaknesses")]
    assert hits and all(f.defect is Defect.B_UNSUPPORTED for f in hits)
    assert any("retracts" in f.message for f in hits), [f.as_dict() for f in hits]


def test_framework_not_stated_contradicted_by_span(avdx_9a):
    record = quote_record(control_framework=Cited[ControlFramework, QuoteCitation](
        value=ControlFramework.NOT_STATED,
        citation=QuoteCitation(quote="Committee of Sponsoring Organizations of the Treadway Commission")))
    result = run_gates(record, avdx_9a, mode="quote")
    assert any(f.field == "control_framework" and f.defect is Defect.B_UNSUPPORTED
               for f in result.findings)


def _weakness(status):
    q = QuoteCitation(quote="material weakness")
    return MaterialWeakness[QuoteCitation](
        description=Cited[str, QuoteCitation](value="x", citation=q),
        remediation_status=Cited[RemediationStatus, QuoteCitation](value=status, citation=q),
    )


def test_unremediated_weakness_contradicts_effective_icfr():
    record = quote_record(material_weaknesses=[_weakness(RemediationStatus.IN_PROGRESS)])
    findings = gate_consistency(record).findings
    assert [f.defect for f in findings] == [Defect.CONSISTENCY]
    assert "not remediated" in findings[0].message


def test_remediated_weakness_with_effective_icfr_is_consistent():
    # The false-positive guard that matters most: "we had a weakness, we fixed
    # it, ICFR is effective at year end" is a perfectly ordinary filing.
    record = quote_record(material_weaknesses=[_weakness(RemediationStatus.REMEDIATED)])
    assert gate_consistency(record).findings == []


def test_not_effective_without_any_weakness_is_flagged():
    record = quote_record(icfr_effective=Cited[bool, QuoteCitation](
        value=False, citation=QuoteCitation(quote="was not effective")))
    findings = gate_consistency(record).findings
    assert any(f.field == "material_weaknesses" for f in findings)
