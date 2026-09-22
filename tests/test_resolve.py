"""The layout-tolerant resolver.

Every case here is a shape that showed up when the corpus was rendered to pages
and read back with OCR. Exact matching found none of 73 citations after a scan,
including one with no degradation applied, because laying text on a page
re-wraps it.
"""
import pytest

from citecheck.resolve import resolve


def test_exact_match_is_still_preferred():
    text = "management concluded that controls were effective as of year end"
    got = resolve("controls were effective", text)
    assert got.exact and not got.normalized
    assert text[got.start:got.end] == "controls were effective"


def test_line_wrap_inside_the_quote():
    text = "Based on this evaluation, management concluded that our internal\ncontrol over financial reporting was effective."
    got = resolve("our internal control over financial reporting was effective", text)
    assert got and not got.exact
    # The span must cover the real passage, newline and all.
    assert "internal" in text[got.start:got.end]
    assert "effective" in text[got.start:got.end]


def test_hyphen_split_across_a_line_break():
    # "Internal Control-Integrated Framework" comes back from OCR as
    # "Internal Control- Integrated Framework" when the line breaks at the hyphen.
    text = "criteria in Internal Control- Integrated Framework (2013) issued by COSO"
    got = resolve("Internal Control-Integrated Framework (2013)", text)
    assert got and not got.exact
    assert "Integrated Framework" in text[got.start:got.end]


def test_collapsed_runs_of_whitespace():
    text = "the  Company   did    not maintain effective controls"
    got = resolve("the Company did not maintain effective controls", text)
    assert got and not got.exact
    assert text[got.start:got.end].startswith("the")
    assert text[got.start:got.end].rstrip().endswith("controls")


def test_case_differences():
    text = "MANAGEMENT CONCLUDED THAT ICFR WAS EFFECTIVE"
    got = resolve("management concluded that icfr was effective", text)
    assert got and not got.exact


def test_absent_text_is_not_invented():
    text = "management concluded that controls were effective"
    assert resolve("the auditor issued an adverse opinion", text) is None


def test_offsets_point_at_the_real_passage_not_just_somewhere():
    # A resolver that reports a hit at the wrong offsets is worse than one that
    # reports nothing, because the citation looks checkable and isn't.
    text = ("First paragraph about disclosure controls.\n\n"
            "Second paragraph where management concluded that internal\n"
            "control over financial reporting was not effective.")
    got = resolve("internal control over financial reporting was not effective", text)
    assert got
    span = text[got.start:got.end]
    assert "not effective" in span
    assert "First paragraph" not in span


@pytest.mark.parametrize("quote", ["", "   "])
def test_empty_quotes_resolve_to_nothing(quote):
    assert resolve(quote, "some text") is None
