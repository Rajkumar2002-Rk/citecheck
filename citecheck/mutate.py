"""Break known-good citations on purpose and see which breakages the gates catch.

Recall is hard to measure honestly here. It needs a labeled set of bad citations,
and the corpus has almost none, because the model's citations are mostly good.
Judging 190 of them by hand to find a handful of failures is a poor trade.

So the defects are manufactured instead. Each mutator introduces one specific,
realistic failure into a citation that currently passes every gate. The catch
rate per mutator is recall against that defect class, and the misses name the
blind spots, which is more useful than a single percentage.

The limit is worth stating plainly: this measures recall against defects chosen
by the person who wrote the gates. A defect nobody thought of is absent from both
the gates and this file.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Callable

FIELDS = ("disclosure_controls_effective", "icfr_effective",
          "control_framework", "auditor_opinion")

# Boilerplate that appears in most filings and supports nothing. Citing it is the
# textbook plausible-looking failure.
_BOILERPLATE = re.compile(
    r"[^.]*?(?:is a process designed to provide reasonable assurance"
    r"|because of its inherent limitations"
    r"|projections of any evaluation of effectiveness)[^.]*\.",
    re.IGNORECASE,
)

FLIP = {
    "EFFECTIVE": "NOT_EFFECTIVE",
    "NOT_EFFECTIVE": "EFFECTIVE",
    "COSO_2013": "COSO_1992",
    "COSO_1992": "COSO_2013",
    "UNQUALIFIED": "ADVERSE",
    "ADVERSE": "UNQUALIFIED",
    "NOT_REQUIRED": "UNQUALIFIED",
    "ABSENT": "UNQUALIFIED",
}


@dataclass
class Mutation:
    name: str
    describes: str
    apply: Callable[[dict, str, str], dict | None]


def _cited(extraction: dict, field: str) -> dict | None:
    if field in extraction and isinstance(extraction.get(field), dict):
        return extraction[field]
    return None


def _fabricate(extraction, field, text):
    """Cite text that is not in the document at all."""
    cited = _cited(extraction, field)
    if cited is None:
        return None
    out = copy.deepcopy(extraction)
    out[field]["citation"]["quote"] = (
        "management concluded that all controls operated without exception "
        "throughout the period under review")
    return out


def _truncate(extraction, field, text):
    """Cut the quote before the part that carries the conclusion."""
    cited = _cited(extraction, field)
    if cited is None:
        return None
    quote = cited["citation"]["quote"]
    if len(quote) < 60:
        return None
    short = quote[: max(30, int(len(quote) * 0.4))]
    if short not in text:
        return None
    out = copy.deepcopy(extraction)
    out[field]["citation"]["quote"] = short
    return out


def _swap(extraction, field, text):
    """Use a different field's citation, so the subject is wrong."""
    cited = _cited(extraction, field)
    if cited is None:
        return None
    donor = next((f for f in FIELDS
                  if f != field and _cited(extraction, f)
                  and _cited(extraction, f)["citation"]["quote"]
                  != cited["citation"]["quote"]), None)
    if donor is None:
        return None
    out = copy.deepcopy(extraction)
    out[field]["citation"]["quote"] = extraction[donor]["citation"]["quote"]
    return out


def _boilerplate(extraction, field, text):
    """Point at the definitional boilerplate, which is real text saying nothing."""
    cited = _cited(extraction, field)
    if cited is None:
        return None
    match = _BOILERPLATE.search(text)
    if match is None:
        return None
    out = copy.deepcopy(extraction)
    out[field]["citation"]["quote"] = match.group(0).strip()
    return out


def _flip_value(extraction, field, text):
    """Keep the citation, invert the claim it is supposed to support."""
    cited = _cited(extraction, field)
    if cited is None or cited["value"] not in FLIP:
        return None
    out = copy.deepcopy(extraction)
    out[field]["value"] = FLIP[cited["value"]]
    return out


MUTATIONS = [
    Mutation("fabricated_quote", "cites text that is not in the document", _fabricate),
    Mutation("truncated_quote", "cuts the quote before the conclusion", _truncate),
    Mutation("swapped_subject", "cites another field's passage", _swap),
    Mutation("boilerplate", "cites the definitional boilerplate", _boilerplate),
    Mutation("flipped_value", "keeps the citation, inverts the claim", _flip_value),
]
