# citecheck

A harness that checks whether an LLM's **citations** actually support the claims
it makes, over SOX Item 9A disclosures in real SEC 10-K filings.

**Status: in progress.** Extraction and the gate layer are complete and run over
30 filings. Hand-labeled ground truth is being built now; defect types C and D
are not reported until it exists.

## The question

Ask a model to extract structured facts from an audit disclosure and cite its
sources at span level. How does the provenance fail?

Four defect types, counted separately:

| | |
|---|---|
| **A** | citation points nowhere — bad offsets, or the quote is not in the document |
| **B** | citation resolves to real text that does not support the claim |
| **C** | claim is correct, citation points to the wrong place |
| **D** | claim is wrong and the citation is fabricated to match |

## What it does

1. Pulls Item 9A ("Controls and Procedures") from 30 10-K filings via SEC EDGAR.
2. Asks `claude-opus-5` for a typed record per filing — ICFR effective, material
   weaknesses, remediation status, control framework, auditor name and opinion —
   with a span-level citation on **every** field.
3. Runs deterministic gates. **No gate calls an LLM.** Span resolution, support
   checking, schema validation, cross-field consistency.
4. Diffs against hand-labeled ground truth.

Two citation modes are run as an A/B:

- **span** — the model reports character offsets itself
- **quote** — the model quotes the text, the harness resolves offsets with `str.find`

## Results so far (30 filings, 354 cited fields)

| | span | quote |
|---|---|---|
| clean filings | 12/30 | **25/30** |
| A: fabricated quote | **0** | **0** |
| A: offset arithmetic | 40 | 0 |
| citation integrity | 74.4% | **96.6%** |
| cost | $12.58 | **$1.19** |
| wall clock | 70 min | **4 min** |

**The model never fabricated source text.** Every quote it produced appears
verbatim in the filing.

**Every span failure was a constant per-document offset drift** — 14 of 14
filings with offset defects showed a single consistent shift, usually ±1
character. Not one produced scattered offsets. The model knows where the text
is; it anchors its coordinate frame differently from the file.

So citation verification here is a coordinate-frame problem, not a fabrication
problem — and `str.find` solves it for about 1/10th the cost.

## The uncomfortable part

The deterministic layer was buggier than the model it checked.

- **7** distinct false-positive classes in the gates, found and fixed
- **4** harness failures that would have been scored as model defects
- **0** fabricated citations by the model

The first version of the support gate reported a 100% defect rate. About 95% of
that was its own bugs — one missing `\s+` (filings break phrases across
newlines) manufactured a third of the findings. Every fix is pinned by a
regression test in `tests/test_captured_failures.py`.

## Usage

```bash
uv sync
export EDGAR_USER_AGENT="Your Name your@email.com"   # SEC blocks requests without it

uv run python -m citecheck.cli discover      # find candidate filings
uv run python -m citecheck.cli build         # download + extract Item 9A
uv run python -m citecheck.cli show 1        # read one filing
uv run python -m citecheck.cli label         # hand-label ground truth
uv run python -m citecheck.cli report --fail-under 0.90
```

Exit codes: `0` pass, `1` below threshold, `2` usage error, `3` no data.

## What this does NOT prove

- **n=30**, one model, single run per filing. Run-to-run variance is real and
  measured, not eliminated.
- Public SEC filings are clean HTML. No OCR, no scanned documents, no messy
  enterprise data.
- Item 9A only, not whole filings.
- **I am not an auditor.** The domain rules I applied are written up in
  [`docs/audit-notes.md`](docs/audit-notes.md); the labels are my own reading.
- Types C and D are unreported until ground truth is complete.
