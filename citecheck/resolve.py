"""Find a quoted passage in text whose layout has changed.

`str.find` is exact, which is right for a document you control and useless for
one that has been through a page and back. Rendering re-wraps lines, so the
words survive and the whitespace does not. On this corpus not one citation of 73
survived exact matching after a scan, including a render with no damage applied.

So matching happens on a normalized copy, and the position is mapped back to the
original. Normalizing is easy; the mapping is the part worth being careful about,
because a citation that resolves to the wrong offsets is worse than one that
fails to resolve at all.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Applied in order. Each step throws away a distinction that survives a scan
# badly but never changes what the words say.
_HYPHEN_BREAK = re.compile(r"-\s+")      # "control- integrated" from a line break
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Resolved:
    start: int
    end: int
    exact: bool          # matched without any normalization
    normalized: bool     # needed whitespace or hyphen folding


def _fold(text: str) -> tuple[str, list[int]]:
    """Normalize, and record where each surviving character came from.

    The index list is the whole point. Without it you can locate a quote in the
    folded copy and have no way to say where it sits in the document, which is
    the only thing a citation is for.
    """
    out: list[str] = []
    origin: list[int] = []
    previous_space = True          # collapses leading whitespace too
    i = 0
    while i < len(text):
        ch = text[i]
        # A hyphen followed by whitespace is a line break inside a word.
        if ch == "-" and i + 1 < len(text) and text[i + 1].isspace():
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            out.append("-")
            origin.append(i)
            previous_space = False
            i = j
            continue
        if ch.isspace():
            if not previous_space:
                out.append(" ")
                origin.append(i)
                previous_space = True
            i += 1
            continue
        out.append(ch.lower())
        origin.append(i)
        previous_space = False
        i += 1
    return "".join(out), origin


def resolve(quote: str, text: str) -> Resolved | None:
    """Locate `quote` in `text`, tolerating layout changes. None if absent."""
    if not quote:
        return None

    at = text.find(quote)
    if at >= 0:
        return Resolved(at, at + len(quote), exact=True, normalized=False)

    folded_text, origin = _fold(text)
    folded_quote, _ = _fold(quote)
    if not folded_quote:
        return None

    at = folded_text.find(folded_quote)
    if at < 0:
        # Hyphens themselves can be dropped or read as something else, so try
        # once more with them gone from both sides.
        bare_text = folded_text.replace("-", "")
        bare_quote = folded_quote.replace("-", "")
        if not bare_quote:
            return None
        at_bare = bare_text.find(bare_quote)
        if at_bare < 0:
            return None
        # Walk the folded text counting non-hyphens to recover the position.
        seen = 0
        at = None
        for index, ch in enumerate(folded_text):
            if seen == at_bare:
                at = index
                break
            if ch != "-":
                seen += 1
        if at is None:
            return None
        length = 0
        seen = 0
        for index in range(at, len(folded_text)):
            if folded_text[index] != "-":
                seen += 1
            length += 1
            if seen == len(bare_quote):
                break
        end_index = at + length - 1
    else:
        end_index = at + len(folded_quote) - 1

    start = origin[at]
    end = origin[min(end_index, len(origin) - 1)] + 1
    return Resolved(start, end, exact=False, normalized=True)
