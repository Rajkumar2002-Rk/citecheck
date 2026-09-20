"""Gate false positives captured from a real run, pinned so they cannot return.

Every string below is text a filing in the corpus actually uses, cited
correctly by the model, and wrongly reported as a defect by the first version
of the support gate. These are regressions against the gate, not the model.
"""
import pytest

from citecheck.gates import (
    _EFFECTIVE_NEG, _EFFECTIVE_POS, _OPINION_MARKERS, _REMEDIATION_MARKERS,
)
from citecheck.schema import AuditorOpinion, RemediationStatus


@pytest.mark.parametrize("quote", [
    # World Gold Trust: asserts effectiveness without the words "was effective".
    "concluded that the Trust and GLDM maintained effective internal control over"
    " financial reporting as of September 30, 2023",
    # Empire State Realty: the auditor's own phrasing.
    "In our opinion, Empire State Realty Trust, Inc. (the Company) maintained, in all"
    " material respects, effective internal control over financial reporting",
])
def test_effectiveness_assertions_are_recognized(quote):
    assert _EFFECTIVE_POS.search(quote)


def test_adverse_opinion_without_the_word_adverse():
    # Alta Equipment. The auditor never writes "adverse opinion" in the sentence
    # that delivers the adverse opinion.
    quote = ("In our opinion, because of the effect of the material weakness identified"
             " below on the achievement of the objectives of the control criteria, the"
             " Company has not maintained effective internal control over financial"
             " reporting")
    assert _OPINION_MARKERS[AuditorOpinion.ADVERSE].search(quote)


def test_unqualified_opinion_survives_a_period_in_the_registrant_name():
    # "Inc." ends a sentence as far as [^.] is concerned, so a character class
    # excluding periods could never span from "In our opinion" to "maintained".
    quote = ("In our opinion, Empire State Realty Trust, Inc. (the Company) maintained,"
             " in all material respects, effective internal control over financial"
             " reporting as of December 31, 2024")
    assert _OPINION_MARKERS[AuditorOpinion.UNQUALIFIED].search(quote)


@pytest.mark.parametrize("quote", [
    "Our independent registered public accounting firm is not required to report on the"
    " effectiveness of our internal control over financial reporting pursuant to Section 404",
    "Management's report was not subject to attestation by our registered public"
    " accounting firm pursuant to the rules of the SEC",
    "Our independent auditors have not audited and are not required to audit this"
    " assessment of our internal control over financial reporting",
    "We are smaller reporting company and a non-accelerated filer, and therefore our"
    " independent registered public accounting firm has not issued a report on the"
    " effectiveness of internal control",
])
def test_attestation_exemption_phrasings(quote):
    assert _OPINION_MARKERS[AuditorOpinion.NOT_REQUIRED].search(quote)


def test_completed_remediation_in_the_infinitive():
    # SkyWater. Matching only the past participle "remediated" missed this.
    quote = ("we were able to remediate the previously identified material weakness in the"
             " Control Activities component")
    assert _REMEDIATION_MARKERS[RemediationStatus.REMEDIATED].search(quote)


@pytest.mark.parametrize("quote", [
    # Progress can precede or follow the remediation word; the first version
    # only matched one order.
    "During 2022, we made progress towards remediation of this material weakness",
    "remediation of the material weakness in the revenue accounting process will require"
    " further remediation efforts",
    "The material weakness will not be considered fully remediated until the remediation"
    " actions are tested",
    "To remediate this material weakness, management is adding more in-depth review"
    " procedures to the tax provision",
])
def test_in_progress_remediation_phrasings(quote):
    assert _REMEDIATION_MARKERS[RemediationStatus.IN_PROGRESS].search(quote)


def test_negated_effectiveness_phrasings():
    assert _EFFECTIVE_NEG.search(
        "management concluded that we did not design and maintain effective controls over"
        " the completeness and accuracy of the accounting")
