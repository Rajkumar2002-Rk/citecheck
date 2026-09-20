"""Locate Item 9A within a 10-K.

Naive str.find("Item 9A") is wrong in at least two ways we have confirmed on
real filings:

  1. The table of contents matches first. AvidXchange FY2024 has the TOC entry
     ~305k characters before the real section.
  2. Auditors cross-reference the item from inside their own report
     ("...as required by Item 9A. Our responsibility is to express opinions..."),
     which matches but is not a section heading.

So: require the heading to be followed closely by "Controls and Procedures"
(kills #2), then discriminate the TOC from the body by how much text runs
before the next item heading (kills #1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# "ITEM 9A.", "Item 9A(T)", "I TEM 9A" -- filings letterspace headings.
_HEADING = re.compile(
    r"I\s?TEM\s*9\s?A\s*(?:\(T\))?\s*[.:\-—]?\s*(?:CONTROLS\s+AND\s+PROCEDURES)",
    re.IGNORECASE,
)

# Anything that legitimately terminates Item 9A. Anchored to the start of a
# line: filings cross-reference later items mid-sentence ("...set forth in the
# F pages after Item 16..."), and an unanchored match truncates the section
# before Changes in ICFR, which is where remediation status lives.
# Note the deliberate omission of "Report of Independent Registered Public
# Accounting Firm": dual registrants such as Vornado print the auditor's ICFR
# opinion *inside* Item 9A, and terminating there would cut the auditor fields
# out of the substrate.
_NEXT = re.compile(
    r"^\s*(?:I\s?TEM\s*(?:9\s?B|9\s?C|10|15|16|6)\b"
    r"|PART\s+(?:III|IV)\b"
    r"|INDEX TO (?:THE )?(?:CONSOLIDATED )?FINANCIAL STATEMENTS"
    r"|SIGNATURES?\s*$"
    r"|EXHIBIT INDEX)",
    re.IGNORECASE | re.MULTILINE,
)

# A real Item 9A always discusses ICFR. A TOC line never does.
_ICFR = re.compile(r"internal control over financial reporting", re.IGNORECASE)

# A real Item 9A opens into one of its canonical subsections almost immediately.
# An Explanatory Note that merely names the item opens into prose instead. This
# is what separates Ceridian's true section (at +17438 inside the blob) from the
# amendment preamble that was swallowing it.
# Line-anchored: the explanatory note contains the same words mid-sentence
# ("...the effectiveness of its disclosure controls and procedures and its
# internal control..."), so an unanchored match scores the preamble and the
# real section identically and length then picks the wrong one.
_SUBSECTION = re.compile(
    r"^\s*(?:Evaluation of |Management.s (?:Annual )?Report on |Management.s Evaluation of )?"
    r"(?:Disclosure Controls and Procedures|Internal Control Over Financial Reporting)",
    re.IGNORECASE | re.MULTILINE,
)
_SUBSECTION_WINDOW = 400

MIN_BODY = 600
# Item 9A is a few thousand characters. Anything far past that means a missing
# terminator let the section run into the financial statements; flag it rather
# than silently admitting 100kB of balance sheets into the corpus.
SUSPECT_BODY = 30_000


@dataclass(frozen=True)
class Section:
    start: int
    end: int
    text: str

    @property
    def length(self) -> int:
        return self.end - self.start


class SectionNotFound(Exception):
    pass


def find_item_9a(text: str) -> Section:
    """Return the Item 9A span with character offsets into `text`.

    Offsets are absolute into the string passed in, so a citation resolved
    against the full document and one resolved against the section agree.
    """
    candidates: list[tuple[int, int, Section]] = []
    for m in _HEADING.finditer(text):
        start = m.start()
        nxt = _NEXT.search(text, m.end())
        end = nxt.start() if nxt else len(text)
        body = text[start:end]
        if len(body) < MIN_BODY or not _ICFR.search(body):
            continue
        # Look for a subsection heading in the text immediately following the
        # Item 9A heading itself -- searching from a fixed offset instead
        # overshoots it, since "Evaluation of Disclosure Controls and
        # Procedures" can begin only 35 characters in.
        window = text[m.end() : m.end() + _SUBSECTION_WINDOW]
        opens_properly = 1 if _SUBSECTION.search(window) else 0
        candidates.append((opens_properly, len(body), Section(start, end, body)))

    if not candidates:
        raise SectionNotFound("no Item 9A heading with a plausible body")

    # Length only breaks ties among equally well-formed candidates; on its own
    # it reliably picks the amendment preamble over the real section.
    return max(candidates, key=lambda c: (c[0], c[1]))[2]
