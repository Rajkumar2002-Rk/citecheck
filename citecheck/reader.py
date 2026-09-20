"""Readable view of an Item 9A section for hand-labeling.

Splits the section into its canonical subsections and drops the boilerplate
that is identical across every filing (the ICFR definition, the inherent-
limitations paragraph, the auditor's basis-for-opinion). What remains is the
text that actually decides the labels.

Deliberately does NOT highlight or suggest answers: it navigates, it does not
adjudicate. Pointing the labeler at the sentence the gates expect would quietly
manufacture agreement between the human and the machine.
"""
from __future__ import annotations

import re

# Headings filings actually use, in the order they normally appear.
_HEADING = re.compile(
    r"^\s*("
    r"Item\s*9A[^\n]*"
    r"|(?:Management's\s+)?(?:Annual\s+|Evaluation\s+of\s+)?Report\s+on\s+Internal\s+Control[^\n]*"
    r"|(?:Management's\s+)?Evaluation\s+of\s+Disclosure\s+Controls[^\n]*"
    r"|Disclosure\s+Controls\s+and\s+Procedures"
    r"|Management's\s+Report\s+on\s+Internal\s+Control[^\n]*"
    r"|(?:Previously\s+disclosed\s+)?Material\s+Weakness(?:es)?[^\n]{0,60}"
    r"|Remediation[^\n]{0,60}"
    r"|\d{4}\s+Remediation[^\n]{0,40}"
    r"|Changes\s+in\s+Internal\s+Control[^\n]*"
    r"|Limitations?\s+on\s+Controls[^\n]*"
    r"|Report\s+of\s+Independent\s+Registered[^\n]*"
    r"|Opinion\s+on\s+Internal\s+Control[^\n]*"
    r"|Basis\s+for\s+Opinion"
    r"|Definition\s+and\s+Limitations[^\n]*"
    r"|Critical\s+Audit\s+Matters?"
    r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Paragraphs that are word-for-word boilerplate in every filing. They define
# what internal control is; they never say anything about THIS company.
# Never drop a paragraph containing an actual conclusion, whatever else is in it.
_CONCLUSION = re.compile(
    r"concluded|determined|assessment,? (?:our|management)|was (?:not )?effective"
    r"|were (?:not )?effective|did not maintain|material weakness",
    re.IGNORECASE,
)

_BOILERPLATE = re.compile(
    r"is a process designed to provide reasonable assurance"
    r"|includes those policies and procedures that"
    r"|Because of its inherent limitations"
    r"|projections of any evaluation of effectiveness to future periods"
    r"|We conducted our audit"
    r"|We are a public accounting firm registered with"
    r"|Our responsibility is to express an opinion"
    r"|A material weakness is a deficiency, or a combination",
    re.IGNORECASE,
)


def sections(text: str) -> list[tuple[str, str]]:
    """Split into (heading, body) pairs."""
    marks = [(m.start(), m.end(), m.group(1).strip()) for m in _HEADING.finditer(text)]
    if not marks:
        return [("Item 9A", text)]
    out = []
    for i, (start, end, heading) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out.append((heading, text[end:stop].strip()))
    return out


def trim(body: str) -> tuple[str, int]:
    """Drop boilerplate paragraphs; return (kept text, dropped paragraph count).

    Split on ANY newline, not just blank lines. Some filings separate paragraphs
    with a single newline, which made the whole section one "paragraph" -- so a
    single boilerplate sentence anywhere in it dropped the entire section,
    conclusion included. That hid the ICFR answer on Video Display Corp.
    """
    kept, dropped = [], 0
    for para in re.split(r"\n+", body):
        para = para.strip()
        if not para:
            continue
        # Only drop when the paragraph is boilerplate AND contains no
        # conclusion. A paragraph that states a finding is never disposable.
        if _BOILERPLATE.search(para) and len(para) > 200 and not _CONCLUSION.search(para):
            dropped += 1
            continue
        kept.append(para)
    return "\n\n".join(kept), dropped
