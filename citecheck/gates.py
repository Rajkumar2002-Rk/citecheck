"""Deterministic verification of an extracted record.

Hard rule: no gate may call an LLM. Every check here is regex, string, or set
logic over the source text and the record. If a gate cannot decide, it says so
(UNVERIFIABLE) rather than guessing -- a gate that guesses is just a second
model with worse calibration.

Defect taxonomy (A and B are decidable here; C and D need the hand-labeled
ground truth, since both turn on whether the *claim* is right):

  A  citation points nowhere        -- offsets invalid, or quote not in source
  B  citation resolves to real text that does not support the claim
  C  claim correct, citation to the wrong place       (needs ground truth)
  D  claim wrong, citation fabricated to match it     (needs ground truth)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Iterator

from .schema import AuditorOpinion, ControlFramework, Effectiveness, RemediationStatus


class Defect(str, Enum):
    A_UNRESOLVABLE = "A_UNRESOLVABLE"
    B_UNSUPPORTED = "B_UNSUPPORTED"
    CONSISTENCY = "CONSISTENCY"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass
class Finding:
    gate: str
    field: str
    defect: Defect
    message: str
    span: tuple[int, int] | None = None

    def as_dict(self) -> dict:
        return {
            "gate": self.gate, "field": self.field, "defect": self.defect.value,
            "message": self.message, "span": list(self.span) if self.span else None,
        }


@dataclass
class GateResult:
    findings: list[Finding] = dc_field(default_factory=list)
    resolved: dict[str, tuple[int, int]] = dc_field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.findings

    def repair_prompt(self) -> str:
        return "\n".join(f"- {f.field}: {f.message}" for f in self.findings)


# --------------------------------------------------------------------------
# Walking the record
# --------------------------------------------------------------------------

def iter_cited(record) -> Iterator[tuple[str, object]]:
    """Yield (dotted field path, Cited object) for every citation in a record."""
    for name in type(record).model_fields:
        value = getattr(record, name)
        if value is None:
            continue
        if name == "material_weaknesses":
            for i, weakness in enumerate(value):
                yield f"material_weaknesses[{i}].description", weakness.description
                yield f"material_weaknesses[{i}].remediation_status", weakness.remediation_status
        else:
            yield name, value


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


# --------------------------------------------------------------------------
# Gate 1 - span resolution
# --------------------------------------------------------------------------

def gate_span_resolution(record, text: str, *, mode: str) -> GateResult:
    """Do the offsets exist, and does the quote match the text at them exactly?

    In quote mode there are no offsets to check; the harness resolves them by
    exact search, and failure means the quoted text is not in the source at all.
    """
    result = GateResult()
    for path, cited in iter_cited(record):
        citation = cited.citation
        quote = citation.quote

        if mode == "span":
            start, end = citation.start, citation.end
            if end > len(text):
                result.findings.append(Finding(
                    "span_resolution", path, Defect.A_UNRESOLVABLE,
                    f"end offset {end} is past the end of the source ({len(text)} chars)",
                    (start, end)))
                continue
            actual = text[start:end]
            if actual == quote:
                result.resolved[path] = (start, end)
                continue
            # Offsets are wrong, but is the quoted text real? That distinction
            # separates "cannot count" from "invented the passage".
            found = text.find(quote)
            if found >= 0:
                result.findings.append(Finding(
                    "span_resolution", path, Defect.A_UNRESOLVABLE,
                    f"quote is real but offsets are wrong: cited ({start},{end}), "
                    f"actual ({found},{found + len(quote)})", (start, end)))
                result.resolved[path] = (found, found + len(quote))
            else:
                result.findings.append(Finding(
                    "span_resolution", path, Defect.A_UNRESOLVABLE,
                    f"quote does not appear in the source: {quote[:80]!r}", (start, end)))
            continue

        # quote mode
        found = text.find(quote)
        if found >= 0:
            result.resolved[path] = (found, found + len(quote))
            continue
        # Tolerate whitespace differences before calling it fabricated.
        loose = _normalize(quote)
        haystack = _normalize(text)
        if loose and loose in haystack:
            result.findings.append(Finding(
                "span_resolution", path, Defect.UNVERIFIABLE,
                "quote matches only after whitespace normalization; offsets not exact"))
        else:
            result.findings.append(Finding(
                "span_resolution", path, Defect.A_UNRESOLVABLE,
                f"quote does not appear in the source: {quote[:80]!r}"))
    return result


# --------------------------------------------------------------------------
# Gate 2 - support check (the Type B gate)
# --------------------------------------------------------------------------

# Boilerplate that appears in nearly every Item 9A. It is topically perfect and
# supports nothing: it defines ICFR, it does not assess this company's ICFR.
# A citation landing here resolves cleanly and reads plausibly to a skimming
# human, which is exactly the failure mode worth counting.
_DEFINITIONAL = re.compile(
    r"is a process designed to provide reasonable assurance"
    r"|includes those policies and procedures that"
    r"|because of its inherent limitations"
    r"|projections of any evaluation of effectiveness to future periods"
    r"|no evaluation of controls can provide absolute assurance"
    r"|control system, no matter how well designed",
    re.IGNORECASE,
)

# Cues, inside the cited span, that the text hypothesizes rather than asserts.
# Risk-factor prose reads exactly like a disclosure until you look at the mood.
_NON_ASSERTIVE = re.compile(
    r"\bif we (?:fail|identify|are unable)\b|\bcould (?:result|lead|cause)\b"
    r"|\bmay not prevent or detect\b|\bwe cannot assure\b"
    r"|\bthere can be no assurance\b",
    re.IGNORECASE,
)

# Cues that the filing RETRACTS the cited passage. These sit outside the span:
# in BioNexus the segregation-of-duties bullets are followed 470 characters
# later by "We made a mistake and the above basis ... was inaccurate". Checking
# only inside the span can never catch this, which is precisely why Type B
# survives naive verification. Kept deliberately narrow -- "previously
# disclosed" is NOT here, because remediation discussion uses it constantly and
# including it would flag ordinary filings.
_RETRACTION = re.compile(
    r"\bwas inaccurate\b|\bwe made a mistake\b|\bthe above basis\b"
    r"|\bincorrectly (?:stated|reported|identified|concluded)\b"
    r"|\bwas in error\b|\bshould not have been\b"
    r"|\bthe Original Filing,? however,? stated\b",
    re.IGNORECASE,
)

# How far around a span to look for a retraction.
CONTEXT_BEFORE = 400
CONTEXT_AFTER = 900

# Calibrated against the corpus, not against priors. Filings assert
# effectiveness with "maintained effective ..." at least as often as with
# "... was effective"; an earlier version of this gate recognized only the
# latter and reported false defects on correct citations.
_EFFECTIVE_POS = re.compile(
    r"\b(?:was|were|is|are)\s+effective\b"
    r"|\bmaintained,?[\s\S]{0,60}?effective\b"
    r"|\bmaintained\s+effective\b"
    r"|\boperating\s+effectively\b",
    re.IGNORECASE,
)
_EFFECTIVE_NEG = re.compile(
    r"\b(?:was|were|is|are)\s+not\s+effective\b"
    r"|\bdid\s+not\s+(?:maintain|design)[\s\S]{0,40}?effective\b"
    r"|\bhas\s+not\s+maintained[\s\S]{0,40}?effective\b"
    r"|\b(?:were|was) ineffective\b|\bineffective\b"
    r"|\bnot\s+effective\b",
    re.IGNORECASE,
)
# Every literal space in a phrase pattern must tolerate a newline. The corpus
# preserves block-element line breaks, so filings routinely read "our
# internal\ncontrol over financial reporting" -- a plain-space regex silently
# fails to match and the gate reports a defect on a perfectly good citation.
# This single omission produced 5 of the first 9 type B findings inspected.
def _phrase(*words: str) -> str:
    return r"\s+".join(words)


_ICFR_SUBJECT = re.compile(
    _phrase("internal", "control", "over", "financial", "reporting") + r"|ICFR",
    re.IGNORECASE)
_DCP_SUBJECT = re.compile(
    _phrase("disclosure", "controls", "and", "procedures"), re.IGNORECASE)
_MW = re.compile(_phrase("material", r"weakness(?:es)?"), re.IGNORECASE)

# Splitting on sentence enders is crude, but the alternative was worse. An
# earlier version asked whether the section contained any conclusion AND
# mentioned the subject anywhere in it, and fired on two filings where the model
# was right: one concludes about disclosure controls while saying nothing about
# ICFR, the other does the reverse. Both words were present, just never in the
# same statement.
_SENTENCE = re.compile(r"(?<=[.;:])\s+|\n{2,}")

# Any mention of the framework anywhere in the section. Used only to refute a
# NOT_STATED claim, so it is deliberately broad.
_FRAMEWORK_NAMED = re.compile(
    r"COSO|Treadway|Internal\s+Control\s*[-\u2013]?\s*Integrated\s+Framework",
    re.IGNORECASE,
)

_FRAMEWORK_MARKERS = {
    ControlFramework.COSO_2013: re.compile(
        r"(?:COSO|Treadway)[\s\S]{0,200}?2013|2013[\s\S]{0,200}?(?:COSO|Treadway)", re.IGNORECASE),
    ControlFramework.COSO_1992: re.compile(
        r"(?:COSO|Treadway)[\s\S]{0,200}?1992|1992[\s\S]{0,200}?(?:COSO|Treadway)", re.IGNORECASE),
}

# Every alternative below was taken from text a filing in this corpus actually
# uses. The auditor's own opinion sentence is "In our opinion, <entity>
# maintained, in all material respects, effective internal control ..." -- it
# never contains the word "unqualified", which is what the first version of
# this gate looked for.
_OPINION_MARKERS = {
    AuditorOpinion.UNQUALIFIED: re.compile(
        r"unqualified opinion|expressed an unqualified"
        r"|in our opinion[\s\S]{0,220}?maintained[\s\S]{0,90}?effective"
        r"|attestation report[\s\S]{0,120}?effective", re.IGNORECASE),
    AuditorOpinion.ADVERSE: re.compile(
        r"adverse opinion|expressed an adverse"
        r"|in our opinion[\s\S]{0,280}?has not maintained[\s\S]{0,70}?effective", re.IGNORECASE),
    AuditorOpinion.NOT_REQUIRED: re.compile(
        r"not (?:required|include)[\s\S]{0,160}?attestation"
        r"|does not include an attestation"
        r"|not (?:required to (?:report|audit)|subject to attestation)"
        r"|have not audited and are not required to audit"
        r"|has not issued a report on the effectiveness"
        r"|permanent exemption|smaller reporting company|non-?accelerated filer"
        r"|exempt", re.IGNORECASE),
    AuditorOpinion.CROSS_REFERENCED: re.compile(
        r"(?:set forth|included|appears|appearing|contained)[\s\S]{0,120}?"
        r"(?:elsewhere|F-?\d|F pages|Item\s*8|Item\s*15|this (?:Annual )?Report)"
        r"|as stated in (?:their|its) report"
        r"|which follows below|follows below|included (?:herein|below)"
        r"|has issued an attestation report", re.IGNORECASE),
}

# "we were able to remediate ..." is a completed remediation; matching only the
# past participle "remediated" missed it. Ordering also matters: filings write
# both "remediation is in progress" and "made progress towards remediation",
# so the progress cue is matched on either side of the remediation word.
_REMEDIATION_MARKERS = {
    RemediationStatus.REMEDIATED: re.compile(
        r"\bremediated\b|\bable to remediate\b|\bremediation[^.]{0,60}?complete"
        r"|no longer exists|\bwere remediated\b|operating effectively", re.IGNORECASE),
    # Filings describe in-flight remediation with a wide verb set: remediate,
    # mitigate, address, adopt. Matching only "remediate" reported defects on
    # four correct citations.
    RemediationStatus.IN_PROGRESS: re.compile(
        r"\bremediat\w+\b[\s\S]{0,120}?(?:plan|progress|ongoing|underway|continue|effort|further)"
        r"|(?:plan|progress|ongoing|underway|continue|effort|further)[\s\S]{0,120}?\bremediat\w+\b"
        r"|\bto (?:remediate|mitigate|address)\b"
        r"|\bin (?:an )?(?:effort|order) to\b"
        r"|\bnot be considered fully remediated\b"
        r"|\b(?:is|are|were|have been)\s+in the process of\b"
        r"|\b(?:is|are)\s+(?:adding|implementing|currently evaluating|engaging)\b"
        r"|\bwe (?:continue|are presently)\b"
        r"|have (?:begun|initiated)", re.IGNORECASE),
    # Future tense is the commonest way a filing says remediation has not begun.
    RemediationStatus.NOT_STARTED: re.compile(
        r"have not (?:yet )?(?:begun|commenced|started)|no remediation"
        r"|\bwill (?:implement|be implementing|develop|design)\b"
        r"|\b(?:plan|intend)s? to (?:implement|develop|design)\b", re.IGNORECASE),
}


def _require(span_text: str, pattern: re.Pattern, path: str, why: str,
             span: tuple[int, int]) -> Finding | None:
    if pattern.search(span_text):
        return None
    return Finding("support_check", path, Defect.B_UNSUPPORTED, why, span)


def gate_support(record, text: str, resolved: dict[str, tuple[int, int]]) -> GateResult:
    """Does the cited span actually assert the claim, or just discuss the topic?"""
    result = GateResult(resolved=dict(resolved))

    for path, cited in iter_cited(record):
        span = resolved.get(path)
        if span is None:
            continue  # gate 1 already reported it; nothing to check against
        span_text = text[span[0] : span[1]]
        context = text[max(0, span[0] - CONTEXT_BEFORE) : span[1] + CONTEXT_AFTER]
        value = cited.value

        # Generic traps, applied to every field.
        if _DEFINITIONAL.search(span_text):
            result.findings.append(Finding(
                "support_check", path, Defect.B_UNSUPPORTED,
                "cites the generic ICFR definition/limitations boilerplate, which "
                "defines internal control rather than assessing this company's", span))
            continue
        if _NON_ASSERTIVE.search(span_text):
            result.findings.append(Finding(
                "support_check", path, Defect.B_UNSUPPORTED,
                "cited text is hypothetical or risk-factor prose, not an assertion",
                span))
            continue
        if _RETRACTION.search(context):
            result.findings.append(Finding(
                "support_check", path, Defect.B_UNSUPPORTED,
                "the filing retracts the cited passage in the surrounding text; the "
                "span resolves exactly but the claim it appears to support is disowned",
                span))
            continue

        finding = None
        if path in ("icfr_effective", "disclosure_controls_effective"):
            icfr = path == "icfr_effective"
            subject = _ICFR_SUBJECT if icfr else _DCP_SUBJECT
            noun = ("internal control over financial reporting" if icfr
                    else "disclosure controls and procedures")
            finding = _require(span_text, subject, path,
                               f"span does not mention {noun}", span)
            if finding is None and value is not Effectiveness.NOT_STATED:
                positive = value is Effectiveness.EFFECTIVE
                wanted = _EFFECTIVE_POS if positive else _EFFECTIVE_NEG
                unwanted = _EFFECTIVE_NEG if positive else _EFFECTIVE_POS
                if not wanted.search(span_text):
                    finding = Finding("support_check", path, Defect.B_UNSUPPORTED,
                                      f"span does not state that {noun} was "
                                      f"{'effective' if positive else 'not effective'}",
                                      span)
                elif positive and unwanted.search(span_text):
                    finding = Finding("support_check", path, Defect.B_UNSUPPORTED,
                                      "span contains a negated effectiveness statement "
                                      "but the claim is effective", span)
            elif finding is None:
                # NOT_STATED is an absence claim, so the whole section refutes it
                # rather than the cited span. But the conclusion has to be about
                # THIS subject, so both have to land in the same sentence.
                stated = next(
                    (part for part in _SENTENCE.split(text)
                     if subject.search(part)
                     and (_EFFECTIVE_POS.search(part) or _EFFECTIVE_NEG.search(part))),
                    None,
                )
                if stated:
                    finding = Finding(
                        "support_check", path, Defect.B_UNSUPPORTED,
                        f"claims no conclusion is stated about {noun}, but the section "
                        f"contains one: {' '.join(stated.split())[:90]!r}", span)

        elif path == "control_framework":
            marker = _FRAMEWORK_MARKERS.get(value)
            if marker is not None:
                finding = _require(span_text, marker, path,
                                   f"span does not identify {value.value}", span)
            elif value == ControlFramework.NOT_STATED:
                # Checked against the WHOLE section, not just the cited span.
                # NOT_STATED is a claim about the absence of something, and you
                # cannot verify an absence by looking at one passage. The
                # observed failure is a filing that names COSO's framework
                # without giving a year: the model reports no framework at all,
                # collapsing "named but undated" into "not named" and erasing a
                # disclosure the company actually made. The right answer there
                # is OTHER.
                named = _FRAMEWORK_NAMED.search(text)
                if named:
                    finding = Finding(
                        "support_check", path, Defect.B_UNSUPPORTED,
                        "claims no control framework is stated, but the section names "
                        f"one at offset {named.start()}: {named.group(0)!r}. A framework "
                        "named without a year is OTHER, not NOT_STATED", span)

        elif path == "auditor_opinion":
            marker = _OPINION_MARKERS.get(value)
            if marker is not None:
                finding = _require(span_text, marker, path,
                                   f"span does not support auditor opinion {value.value}",
                                   span)

        elif path == "auditor_name":
            if _normalize(str(value)) not in _normalize(span_text):
                finding = Finding("support_check", path, Defect.B_UNSUPPORTED,
                                  f"span does not contain the auditor name {value!r}", span)

        elif path.endswith(".description"):
            # Filings list weaknesses as bullets under a "material weaknesses"
            # heading, so the phrase is frequently just outside the cited span.
            # Requiring it inside flagged correct citations; check the context.
            if not _MW.search(context) and not _EFFECTIVE_NEG.search(span_text):
                finding = Finding("support_check", path, Defect.B_UNSUPPORTED,
                                  "cited text neither mentions a material weakness nor "
                                  "describes an ineffective control", span)

        elif path.endswith(".remediation_status"):
            marker = _REMEDIATION_MARKERS.get(value)
            if marker is not None:
                finding = _require(span_text, marker, path,
                                   f"span does not support remediation status "
                                   f"{value.value}", span)

        if finding is not None:
            result.findings.append(finding)

    return result


# --------------------------------------------------------------------------
# Gate 3 - cross-field consistency
# --------------------------------------------------------------------------

# Remediated weaknesses are the trap here. "We disclosed a material weakness,
# we remediated it during the year, and ICFR was effective as of year end" is a
# perfectly consistent filing. A gate that flags any weakness alongside
# icfr_effective=true produces false positives on exactly the filings auditors
# care most about, so status is part of the rule, not an afterthought.
_UNRESOLVED = {RemediationStatus.NOT_STARTED, RemediationStatus.IN_PROGRESS,
               RemediationStatus.NOT_STATED}


def gate_consistency(record) -> GateResult:
    result = GateResult()
    icfr_value = record.icfr_effective.value
    icfr = icfr_value is Effectiveness.EFFECTIVE
    icfr_unknown = icfr_value is Effectiveness.NOT_STATED
    weaknesses = record.material_weaknesses
    opinion = record.auditor_opinion.value

    unresolved = [w for w in weaknesses if w.remediation_status.value in _UNRESOLVED]
    if icfr_unknown:
        # No conclusion to contradict. Saying so is not an inconsistency.
        return result
    if unresolved and icfr:
        result.findings.append(Finding(
            "consistency", "icfr_effective", Defect.CONSISTENCY,
            f"{len(unresolved)} material weakness(es) are not remediated, so ICFR "
            f"cannot be concluded effective as of the balance-sheet date", None))

    if not icfr and not weaknesses:
        result.findings.append(Finding(
            "consistency", "material_weaknesses", Defect.CONSISTENCY,
            "ICFR is reported not effective but no material weakness is listed; a "
            "not-effective conclusion rests on at least one disclosed weakness", None))

    if opinion == AuditorOpinion.ADVERSE and icfr:
        result.findings.append(Finding(
            "consistency", "auditor_opinion", Defect.CONSISTENCY,
            "auditor opinion is adverse but management reports ICFR effective", None))

    if opinion == AuditorOpinion.UNQUALIFIED and not icfr:
        result.findings.append(Finding(
            "consistency", "auditor_opinion", Defect.CONSISTENCY,
            "auditor opinion is unqualified but management reports ICFR not effective",
            None))

    return result


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

def run_gates(record, text: str, *, mode: str) -> GateResult:
    """All gates, in order. Support runs only on spans that resolved."""
    spans = gate_span_resolution(record, text, mode=mode)
    support = gate_support(record, text, spans.resolved)
    consistency = gate_consistency(record)
    return GateResult(
        findings=spans.findings + support.findings + consistency.findings,
        resolved=spans.resolved,
    )
