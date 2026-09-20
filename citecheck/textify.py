"""HTML -> plain text.

Offset stability is the whole project: every citation the LLM produces is a
character range into the string this module returns. So the transform must be
deterministic and lossless in position -- run it twice on the same bytes and
you must get byte-identical output.
"""
from __future__ import annotations

import re
import unicodedata

from selectolax.parser import HTMLParser

# Filings are littered with these; normalizing them to a plain space keeps
# quoted snippets matchable by a human who copy-pastes from a browser.
_INVISIBLE = dict.fromkeys(map(ord, "   ​‌‍﻿"), " ")
_DASHES = {ord("‐"): "-", ord("‑"): "-", ord("‒"): "-", ord("–"): "-", ord("—"): "-"}
_QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}

_BLOCK = "p div br tr li h1 h2 h3 h4 h5 h6 table td th".split()


def html_to_text(raw: str) -> str:
    tree = HTMLParser(raw)
    for tag in ("script", "style", "head"):
        for node in tree.css(tag):
            node.decompose()

    # Force a newline boundary at block-level elements so headings don't fuse
    # onto the body text that follows them.
    for tag in _BLOCK:
        for node in tree.css(tag):
            node.insert_after("\n")

    text = tree.body.text() if tree.body else tree.text()
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_INVISIBLE).translate(_DASHES).translate(_QUOTES)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
