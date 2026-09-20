# citecheck

I wanted to know how an LLM fabricates provenance when you force it to cite its
sources. So I built a harness that checks span-level citations against the
source text, using deterministic checks that never call a model, and ran it over
30 real SEC filings with ground truth I labeled by hand.

It didn't fabricate anything. The interesting failure was somewhere else.

## The headline

Over 30 filings and 178 cited fields, asking Claude Opus 5 to extract audit
conclusions with a citation on every field:

**96.6% of citations were valid. 3 of 30 filings still carried a factual error,
and 2 of those passed every citation check.**

Citation integrity and claim correctness are different properties. Verifying the
first tells you very little about the second, which is the entire point of the
exercise.

## What the model actually got wrong

Three errors across 30 filings. Two of them are the same failure:

| filing | hand-labeled | model | |
|---|---|---|---|
| Netlist | `OTHER` | `NOT_STATED` | framework named without a year |
| JAAG Enterprises | `OTHER` | `NOT_STATED` | same, under the v2 prompt |
| Tribal Rides | 3 | 1 | three weaknesses in one sentence, under-counted |
| Trendmaker | 1 | 2 | counted "failed to stay current in SEC filings" as a weakness |

The repeating one is worth naming. Some filings cite COSO's *Internal Control -
Integrated Framework* without saying which version, 1992 or 2013. The model
reports that **no framework was stated at all**. It collapses "named but
ambiguous" into "not named", which in audit terms erases a disclosure the
company actually made.

It is the only error that reproduced across prompt versions, and it is now
caught deterministically. `NOT_STATED` is a claim about the *absence* of
something, and an absence cannot be verified by reading the one passage the
model chose to cite. The check reads the whole section instead: if the framework
is named anywhere, `NOT_STATED` is refuted and the answer should be `OTHER`.
Two true positives, no false positives.

## A prompt fix that fixed nothing

Before the labels existed, the apparent failure was that the model counted
material weaknesses the filing said were already remediated. So I added one
instruction telling it to count only weaknesses open at the fiscal year end, and
re-ran the whole corpus.

| | baseline | + remediation rule |
|---|---|---|
| citation integrity | **96.6%** | 96.4% |
| filings with a wrong claim | **3** | **3** |
| remediated weaknesses reported | **7** | **0** |

No improvement in accuracy, and it silently deleted a category of disclosure.
The baseline had been reporting remediated weaknesses correctly all along, each
tagged with its own status; the "fix" simply stopped reporting them. It also
traded one error for another, repairing Tribal Rides and breaking JAAG.

Both prompts are in the repository. A targeted instruction that looks obviously
correct, measures as no better, and quietly removes information seemed worth
recording.

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

- **8** defects in the verification layer, each found and fixed
- **4** harness failures that would have been recorded as model defects
- **0** citations fabricated by the model

The eighth one was the worst, and it was in the headline. My diff compared the
hand-labeled count of weaknesses *open at year end* against the number of
weaknesses the extraction *listed*, which includes remediated ones carrying a
`REMEDIATED` status. Two different definitions, compared as though identical.
That single mistake produced an apparent 23% claim-error rate. The real figure
is 10%, and the model had been right about every one of the cases I was counting
against it.

I built a whole gate on top of that misreading before checking it. The gate
scored zero true positives and one false positive, and has been reverted rather
than tuned, because tuning it would have been fitting noise.

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

I mention this because a verification layer feels authoritative in a way the
model does not, and mine was wrong far more often than the model was. Every
scary number it produced was worth less than the five minutes it took to check
whether the checker was right.

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
