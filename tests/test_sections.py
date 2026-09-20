"""Each test here is pinned to a failure actually observed on a real filing."""
from citecheck.sections import find_item_9a
from citecheck.textify import html_to_text


def test_textify_is_deterministic(avdx_html):
    # Offsets are meaningless if the transform is not reproducible.
    assert html_to_text(avdx_html) == html_to_text(avdx_html)


def test_skips_table_of_contents(avdx_html):
    # Observed: "Item 9A" first matches the TOC ~305k chars before the section.
    text = html_to_text(avdx_html)
    section = find_item_9a(text)
    assert section.text.lstrip().upper().startswith("ITEM 9A")
    assert "Evaluation of Disclosure Controls and Procedures" in section.text
    assert text.index("Item 9B.") < section.start or section.start > 100_000


def test_skips_auditor_cross_reference(avdx_html):
    # Observed: PwC's report contains "Item 9A. Our responsibility is to..."
    section = find_item_9a(html_to_text(avdx_html))
    assert "Our responsibility is to express opinions" not in section.text


def test_does_not_truncate_at_midsentence_item_reference(avdx_html):
    # Observed: an unanchored terminator matched "Item 16" inside the sentence
    # "...report set forth in the F pages after Item 16...", cutting the section
    # before Changes in ICFR -- where remediation status is disclosed.
    section = find_item_9a(html_to_text(avdx_html))
    assert "Changes in Internal Control Over Financial Reporting" in section.text
    assert "were no changes in our internal control" in section.text


def test_offsets_resolve_against_source(avdx_html):
    text = html_to_text(avdx_html)
    section = find_item_9a(text)
    assert text[section.start : section.end] == section.text


def test_amendment_retains_retraction_context(bglc_html):
    # The money case: the section must contain BOTH the retracted weakness
    # bullets and the sentence retracting them. Truncating either way would
    # make the ground truth unrecoverable.
    section = find_item_9a(html_to_text(bglc_html))
    assert "unable to maintain segregation of duties" in section.text
    assert "the above basis for identifying a material weakness was inaccurate" in section.text
    assert "internal control over financial reporting were effective" in section.text


def test_prefers_real_heading_over_amendment_explanatory_note(ceridian_html):
    # Observed: the Explanatory Note opens "Item 9A Controls and Procedures in
    # this Form 10-K/A to update its conclusions regarding the effectiveness of
    # its disclosure controls and procedures..." -- at line start, followed by
    # the subsection words mid-sentence. Preferring the longest candidate
    # captured 26,481 chars starting at the note; the real section is 9,042.
    section = find_item_9a(html_to_text(ceridian_html))
    assert section.text.startswith("Item 9A. Controls and Procedures.")
    assert "to update its conclusions regarding" not in section.text[:400]
    assert section.length < 12_000
