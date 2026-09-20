"""Extraction prompts.

Deliberately neutral about what the answer should be. The prompt explains the
domain and the citation contract; it does not hint that weaknesses are common,
that most filings are clean, or that any field is usually absent. Steering the
model toward the right answer would make the defect rate meaningless.
"""
from __future__ import annotations

SYSTEM = """\
You extract structured facts from Item 9A ("Controls and Procedures") of SEC \
Form 10-K filings.

Domain notes:
- Item 9A contains management's conclusion on disclosure controls and \
procedures, management's assessment of internal control over financial \
reporting (ICFR) under SOX Section 404(a), and, for filers that are required to \
have one, a reference to the auditor's separate attestation under Section 404(b).
- A material weakness is a deficiency, or combination of deficiencies, such that \
there is a reasonable possibility that a material misstatement will not be \
prevented or detected on a timely basis.
- Smaller reporting companies and non-accelerated filers are exempt from the \
auditor attestation requirement.
- Some filings reference the auditor's opinion but print it elsewhere in the \
document, outside the text you are given.

Report only what the provided text states. Do not infer, complete, or normalize \
beyond what is written. If the text does not establish a field, use the enum \
value that says so rather than guessing."""

CITATION_SPAN = """\
Every field must carry a citation with:
- start: the 0-based character offset in the SOURCE TEXT where the supporting \
text begins
- end: the character offset one past the last supporting character
- quote: the text lying at exactly [start, end), copied character for character

The quote must be the literal substring at those offsets. The cited span must \
itself state the fact you are reporting -- not merely discuss the same topic."""

CITATION_QUOTE = """\
Every field must carry a citation containing:
- quote: the supporting text, copied character for character from the SOURCE TEXT

The quote must appear verbatim in the source. The quoted passage must itself \
state the fact you are reporting -- not merely discuss the same topic."""

USER = """\
{citation_contract}

SOURCE TEXT (Item 9A, {length} characters, offset 0 is the first character below):
<source>
{text}
</source>

Extract the structured record."""


def build_user_prompt(text: str, *, mode: str) -> str:
    contract = CITATION_SPAN if mode == "span" else CITATION_QUOTE
    return USER.format(citation_contract=contract, length=len(text), text=text)
