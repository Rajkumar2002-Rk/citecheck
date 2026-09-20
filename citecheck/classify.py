"""Cheap, deterministic descriptors used to balance the corpus.

These are NOT labels. They decide which filings go in the corpus; the ground
truth for every extracted field is hand-made. Nothing here may be reused as an
expected value, or the experiment becomes circular.
"""
from __future__ import annotations

import re

# SOX 404(b): large accelerated filers get an auditor opinion on ICFR. Smaller
# filers are exempt and say so in almost these words. Which side a filing falls
# on is the single best cheap proxy for company size, and it also determines
# whether auditor_opinion is legitimately absent.
_EXEMPT = re.compile(
    r"(?:does not include|is not required to include|are not required to include)"
    r"[^.]{0,120}attestation report",
    re.IGNORECASE,
)
_ATTESTED = re.compile(
    r"(?:has been audited by|attestation report of|report of .{0,60}independent registered"
    r" public accounting firm)",
    re.IGNORECASE,
)

_MW = re.compile(r"material weakness(?:es)?", re.IGNORECASE)
_NOT_EFFECTIVE = re.compile(
    r"(?:was|were) not effective|did not maintain effective", re.IGNORECASE
)


def describe(section: str) -> dict:
    exempt = bool(_EXEMPT.search(section))
    return {
        "attested": (not exempt) and bool(_ATTESTED.search(section)),
        "attestation_exempt": exempt,
        "mentions_material_weakness": bool(_MW.search(section)),
        "asserts_not_effective": bool(_NOT_EFFECTIVE.search(section)),
    }
