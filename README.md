# citecheck

I wanted to know how an LLM fabricates provenance when you force it to cite its
sources. So I built a harness that checks span-level citations against the
source text, using deterministic checks that never call a model, and ran it over
30 real SEC filings with ground truth I labeled by hand.

It didn't fabricate anything. The interesting failure was somewhere else.

## The headline

Over 30 filings and 178 cited fields, asking Claude Opus 5 to extract audit
conclusions with a citation on every field:

**96.6% of citations were valid. 23% of filings contained a claim that was
wrong and that every citation check passed.**

Those two numbers are the whole point. Citation integrity and claim correctness
are different properties, and verifying the first tells you very little about
the second.

## What the model got wrong

Almost every wrong claim was the same field: how many material weaknesses the
company disclosed.

| filing | hand-labeled | model |
|---|---|---|
| Alta Equipment Group | 1 | 3 |
| Empire State Realty Trust | 0 | 1 |
| FlexShopper | 1 | 2 |
| Titan Pharmaceuticals | 0 | 1 |
| Video Display Corp | 0 | 1 |
| Trendmaker | 1 | 2 |
| Tribal Rides International | 3 | 1 |

Six of the seven are over-counts, and five of those are the same mistake: the
filing says a weakness was **remediated as of the fiscal year end**, and the
model counted it anyway.

That distinction is not cosmetic. A remediated material weakness is a company
reporting that it fixed a problem. An open one means internal control over
financial reporting is ineffective and the auditor issues an adverse opinion.
They are close to opposite facts, and they sit two sentences apart in the same
paragraph.

Every one of these passed the citation gates. The model quoted the remediation
language accurately and still counted the weakness as open. There is no
provenance check that catches this, because nothing about the provenance is
wrong.

## Offsets, and what they cost

The extraction ran in two modes. In **span** mode the model reports character
offsets itself. In **quote** mode it returns the quoted text and the harness
resolves offsets with `str.find`.

| | span | quote |
|---|---|---|
| citation integrity | 74.4% | **96.6%** |
| filings with no findings | 12/30 | **25/30** |
| quote not present in source | 0 | 0 |
| offset errors | 40 | 0 |
| cost | $12.58 | **$1.19** |
| wall clock | 70 min | **4 min** |

The model never invented source text. Not once, in either mode, across every
cited field. Every quote it produced appears verbatim in the filing.

Every offset failure was a **constant per-document drift**. All 14 filings with
offset errors showed a single consistent shift, usually one character, once 66.
Not one produced scattered offsets. The model knows where the text is; it just
anchors its coordinate frame differently from the file.

So self-reported offsets cost about ten times as much, take fifteen times
longer, and introduce a defect class that does not otherwise exist. If you need
character spans, have the model quote the text and find it yourself.

## The part I did not expect

The deterministic layer was buggier than the model it was checking.

- **7** distinct false-positive classes in the gates, each found and fixed
- **4** harness failures that would have been recorded as model defects
- **0** citations fabricated by the model

The first version of the support gate reported a 100% defect rate. Roughly 95%
of that was its own bugs. I had written the patterns from what I assumed audit
language sounded like rather than from the filings. Some examples:

- filings assert effectiveness as "maintained effective internal control", not
  "was effective"
- the sentence delivering an adverse opinion rarely contains the word "adverse"
- `[^.]{0,200}` cannot cross a period, so any registrant whose legal name ends
  in "Inc." broke the unqualified-opinion pattern
- filings break phrases across newlines, so "internal\ncontrol over financial
  reporting" never matched a plain-space regex

That last one, a single missing `\s+`, produced a third of the findings at one
point. Each fix is pinned in `tests/test_captured_failures.py` against the
filing text that caused it.

I mention this because a verification layer that reports a scary number is not
automatically right, and mine was wrong far more often than the model was.

## How it works

1. Pull Item 9A ("Controls and Procedures") from 30 10-K filings through SEC
   EDGAR. Section boundaries are harder than they look: the table of contents
   matches first, auditors cross-reference the item from inside their own
   reports, and amendments name the item in an explanatory note before the
   section itself.
2. Ask the model for a typed record per filing, with a span-level citation on
   every field. Pydantic v2, enum-constrained.
3. Run the gates. No gate calls an LLM.
   - **span resolution** — do the offsets resolve, and does the quoted text
     match the source exactly
   - **support** — does the cited passage state the claim, or only discuss the
     same topic. Support is a scope question, not a substring one: a span can
     resolve perfectly while the surrounding text retracts it
   - **consistency** — a weakness that is still open contradicts effective ICFR,
     but a remediated one does not
4. Diff against hand-labeled ground truth. This is the only independent
   measurement in the project. Gates calibrated against model output can only
   tell you the gate agrees with the model.

## Usage

```bash
uv sync
export EDGAR_USER_AGENT="Your Name your@email.com"   # EDGAR blocks requests without it

uv run python -m citecheck.cli discover      # find candidate filings
uv run python -m citecheck.cli build         # download and extract Item 9A
uv run python -m citecheck.cli show 1        # read one filing
uv run python -m citecheck.cli label         # hand-label ground truth
uv run python -m citecheck.cli report --fail-under 0.90
```

Exit codes: `0` pass, `1` below threshold, `2` usage error, `3` no data.

CI runs on every push and needs no secrets, because the corpus text, the saved
extractions and the labels are all committed. It fails the build if citation
integrity on the committed run drops below threshold, which catches a gate
regression and not only a model one.

A second workflow re-extracts a sample against the labels to catch model drift.
That one costs money, so it runs on manual trigger rather than a schedule:

```bash
gh workflow run drift.yml -f sample=5
```

## What this does not prove

- **n = 30, one model, one run per filing.** Run-to-run variance is real. The
  same filing returned 6 findings on one pass and 1 on another.
- Public filings are clean HTML. No OCR, no scanned documents, no messy
  enterprise data. That is the harder half of the problem and it is not here.
- Item 9A only, not whole filings.
- **I am not an auditor.** I learned the domain from primary sources over a
  weekend. The rules I applied are written up in
  [`docs/audit-notes.md`](docs/audit-notes.md), including the filings that
  caught me out, so you can check my reasoning rather than take it on trust.
- Two filings do not contain their own answer. CubeSmart incorporates
  management's ICFR report by reference to page F-2, and MARKY never states a
  disclosure-controls conclusion at all. No extraction system can be right about
  those from the assigned scope, and I labeled them by inference and said so.
