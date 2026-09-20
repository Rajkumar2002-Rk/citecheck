# citecheck

**What happens to an LLM's citations when you check every single one against the
source text?**

I expected to catch it inventing support for things the filing never said. That's
the failure everyone worries about with provenance, and it's the one I built this
to measure.

It never happened. Not once, across 354 cited fields in 30 real SEC filings.

What I found instead was that my own verification layer, the deterministic part,
the part that felt authoritative, was wrong eight separate times. One of those
errors put a false number in this README before I caught it.

---

## The numbers

30 filings from SEC EDGAR. Claude Opus 5 extracts seven fields from each
company's Item 9A internal-control disclosure, with a span-level citation on
every field. Deterministic checks verify the citations. I hand-labeled all 30
filings myself to check the claims.

| | span mode | quote mode |
|---|---|---|
| citation integrity | 74.4% | 96.6% |
| filings with no findings | 12/30 | 25/30 |
| quotes not present in the source | 0 | 0 |
| offset errors | 40 | 0 |
| factual errors vs. hand labels | 2/30 | 3/30 |
| cost | $12.58 | $1.19 |
| wall clock | 70 min | 4 min |

Two citation modes, run as an A/B. In span mode the model reports character
offsets itself. In quote mode it returns the quoted text and the harness finds it
with `str.find`.

Three things fall out of that table.

## 1. It never fabricated a quote

Every quoted passage appears verbatim in the filing, in both modes, across every
cited field. Whatever else goes wrong here, the model doesn't invent source text.

## 2. Self-reported offsets are expensive and pointless

Every offset failure was a constant per-document drift. All 14 filings with
offset errors showed a single consistent shift, usually one character, once 66.
None of them produced scattered offsets. The model knows where the text is. It
just anchors its coordinate frame differently from the file.

So asking for offsets costs ten times more, takes fifteen times longer, and
creates a defect class that wouldn't otherwise exist. If you need character
spans, have the model quote the passage and locate it yourself.

## 3. Good citations don't mean true claims

This is the one that matters.

Citation integrity in quote mode is 96.6%. Three filings still came back with a
factual error, and two of those passed every citation check. The provenance was
fine. The claim was wrong.

| filing | hand-labeled | model | |
|---|---|---|---|
| Netlist | `OTHER` | `NOT_STATED` | framework named without a year |
| JAAG Enterprises | `OTHER` | `NOT_STATED` | same, under a later prompt |
| Tribal Rides | 3 | 1 | three weaknesses in one sentence, under-counted |
| Trendmaker | 1 | 2 | counted late SEC filings as a control weakness |

The repeating error is worth naming. Some filings cite COSO's *Internal Control -
Integrated Framework* without saying whether they mean the 1992 or the 2013
version. The model reports that no framework was stated at all, collapsing "named
but ambiguous" into "not named". In audit terms that erases a disclosure the
company actually made.

It's the only error that reproduced across prompt versions, so it's now caught
deterministically:

> `NOT_STATED` is a claim about the absence of something, and you can't verify an
> absence by reading the one passage the model chose to cite.

The check reads the whole section instead. If the framework is named anywhere,
`NOT_STATED` is refuted and the answer should be `OTHER`. Two true positives, no
false positives.

## The prompt fix that fixed nothing

Before the hand labels existed, the apparent failure was that the model counted
material weaknesses the filing said had already been remediated. So I added one
instruction, count only weaknesses still open at the fiscal year end, and re-ran
the whole corpus.

| | baseline | + remediation rule |
|---|---|---|
| citation integrity | 96.6% | 96.4% |
| filings with a wrong claim | 3 | 3 |
| remediated weaknesses reported | 7 | 0 |

No accuracy gain, and it silently deleted a category of disclosure. The baseline
had been reporting remediated weaknesses correctly all along, each tagged with
its own status. The "fix" just stopped reporting them. It also traded one error
for another, repairing Tribal Rides and breaking JAAG.

Both prompts are in the repository. An instruction that looks obviously correct,
measures as no better, and quietly removes information seemed worth recording.

## The part I didn't expect

The deterministic layer was buggier than the model it was checking.

- 8 defects in the verification layer, each found and fixed
- 4 harness failures that would have been scored as model defects
- 0 citations fabricated by the model

The first version of the support gate reported a 100% defect rate. Roughly 95% of
that was its own bugs. I'd written the patterns from what I assumed audit
language sounded like, rather than from the filings:

- filings assert effectiveness as "maintained effective internal control", not
  "was effective"
- the sentence delivering an adverse opinion rarely contains the word "adverse"
- `[^.]{0,200}` can't cross a period, so any registrant whose legal name ends in
  "Inc." broke the unqualified-opinion pattern
- filings break phrases across newlines, so "internal\ncontrol over financial
  reporting" never matched a plain-space regex

That last one, a single missing `\s+`, produced a third of the findings at one
point.

The eighth was the worst, and it was in the headline. My diff compared the
hand-labeled count of weaknesses *open at year end* against the number of
weaknesses the extraction *listed*, which includes remediated ones carrying a
`REMEDIATED` status. Two different definitions, compared as though they were the
same. That one mistake produced an apparent 23% claim-error rate. The real figure
is 10%, and the model had been right about every case I was counting against it.

I built a whole gate on top of that misreading before checking it. The gate
scored zero true positives and one false positive. I reverted it rather than
tuning it, because tuning it would have been fitting noise.

A verification layer feels authoritative in a way the model doesn't. Mine was
wrong far more often than the model was, and every alarming number it produced
turned out to be worth less than the five minutes it took to check the checker.

## How it works

1. Pull Item 9A ("Controls and Procedures") from 30 filings through EDGAR.
   Section boundaries are harder than they look. The table of contents matches
   first, auditors cross-reference the item from inside their own reports, and
   amendments name it in an explanatory note before the section itself.
2. Extract a typed record per filing. Pydantic v2, enum-constrained, with a
   span-level citation on every field.
3. Verify. No gate calls an LLM.
   - *span resolution*: do the offsets resolve, does the quote match exactly
   - *support*: does the cited passage state the claim, or only discuss the same
     topic. Support is a scope question rather than a substring one, since a span
     can resolve perfectly while the surrounding text retracts it
   - *consistency*: an open weakness contradicts effective ICFR, a remediated one
     doesn't
4. Diff against hand labels. This is the only independent measurement in the
   project. Gates calibrated against model output can only tell you the gate
   agrees with the model.

## Usage

```bash
uv sync
export EDGAR_USER_AGENT="Your Name your@email.com"   # EDGAR blocks requests without it

uv run python -m citecheck.cli discover           # find candidate filings
uv run python -m citecheck.cli build              # download and extract Item 9A
uv run python -m citecheck.cli show 1             # read one filing
uv run python -m citecheck.cli label              # hand-label ground truth
uv run python -m citecheck.cli extract --mode quote --prompt 1
uv run python -m citecheck.cli report --fail-under 0.90
```

`extract` is resumable and enforces a single instance, after two processes
silently interleaved an entire run. `--repair N` feeds gate findings back to the
model and retries. Exit codes: `0` pass, `1` below threshold, `2` usage error,
`3` no data.

CI runs on every push and needs no secrets. The corpus text, both extraction runs
and the hand labels are committed, so `report` reproduces these numbers offline.
It fails the build when citation integrity drops, which catches a gate regression
and not only a model one. A second workflow re-extracts a sample against the
labels to catch model drift. That one costs money, so it runs on manual trigger:

```bash
gh workflow run drift.yml -f sample=5
```

## What this doesn't prove

- n = 30, one model, one run per filing. Run-to-run variance is real. The same
  filing returned 6 findings on one pass and 1 on another.
- Public filings are clean HTML. No OCR, no scanned documents, no messy
  enterprise data. That's the harder half of the problem and it isn't here.
- Item 9A only, not whole filings.
- I'm not an auditor. I learned the domain from primary sources over a weekend.
  The rules I applied are in [`docs/audit-notes.md`](docs/audit-notes.md),
  including every filing that caught me out, so you can check my reasoning
  instead of taking it on trust.
- Two filings don't contain their own answer. CubeSmart incorporates management's
  ICFR report by reference to page F-2, and MARKY never states a
  disclosure-controls conclusion at all. No extraction system can be right about
  those from the assigned scope. I labeled them by inference and said so.
