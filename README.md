# citecheck

**What happens to an LLM's citations when you check every single one against the
source text?**

I expected to catch it inventing support for things the filing never said.
That's the failure everyone worries about, and it's the one I built this to
check.

It never happened. Not once, across 354 cited fields in 30 real SEC filings.

What I found instead was that my own checking code, the part that never calls a
model and feels like the trustworthy half, was wrong nine separate times. One
of those errors put a false number in this README before I caught it.

---

## The numbers

30 filings from SEC EDGAR. Claude Opus 5 extracts seven fields from each
company's Item 9A internal-control disclosure, with a span-level citation on
every field. Checks that never call a model verify the citations. I hand-labeled
all 30 filings myself to check the claims. Numbers below are Opus 5; Sonnet 5 is
further down.

| | span mode | quote mode |
|---|---|---|
| citation integrity | 74.4% | 98.9% |
| filings with no findings | 12/30 | 28/30 |
| quotes not present in the source | 0 | 0 |
| offset errors | 40 | 0 |
| factual errors vs. hand labels | 4/30 | 3/30 |
| cost | $12.58 | $1.21 |
| wall clock | 70 min | 4 min |

Two citation modes, run as an A/B. In span mode the model reports character
offsets itself. In quote mode it returns the quoted text and the harness finds
it with `str.find`.

The span run is older and could only answer true or false for the two
effectiveness fields. Two of its four factual errors are CubeSmart and MARKY,
which it had no way to get right. The schema section further down covers why.

Three things fall out of that table.

## 1. It never fabricated a quote

Every quoted passage appears verbatim in the filing, in both modes, across every
cited field. Whatever else goes wrong here, the model doesn't invent source
text.

## 2. Self-reported offsets are expensive and pointless

Every offset failure was a constant per-document drift. All 14 filings with
offset errors showed a single consistent shift, usually one character, once 66.
None of them produced scattered offsets. The model knows where the text is. It
just starts counting from a different place than the file does.

So asking for offsets costs ten times more, takes fifteen times longer, and
creates a defect class that wouldn't otherwise exist. If you need character
spans, have the model quote the passage and locate it yourself.

## 3. Good citations don't mean true claims

This is the one that matters.

Citation integrity in quote mode is 98.9%. Three filings still came back with a
factual error, and two of those passed every citation check. The citation was
fine. The claim was wrong.

| filing | hand-labeled | model | |
|---|---|---|---|
| Netlist | `OTHER` | `NOT_STATED` | framework named without a year |
| JAAG Enterprises | `OTHER` | `NOT_STATED` | same, under a later prompt |
| Tribal Rides | 3 | 1 | three weaknesses in one sentence, under-counted |
| Trendmaker | 1 | 2 | counted late SEC filings as a control weakness |

The repeating error is worth naming. Some filings cite COSO's *Internal Control
- Integrated Framework* without saying whether they mean the 1992 or the 2013
version. The model says no framework was stated at all. It turns "named, but no
version given" into "not named", which wipes out a disclosure the company
actually made.

It's the only error that showed up again when I changed the prompt, so it's now
caught by a rule instead:

> `NOT_STATED` is a claim about the absence of something, and you can't verify an
> absence by reading the one passage the model chose to cite.

The check reads the whole section instead. If the framework is named anywhere in
the section, `NOT_STATED` is wrong and the answer should be `OTHER`. Two true
positives, no false positives.

## Does any of this repeat?

A model doesn't give you the same answer twice, so one run of 30 filings is one
measurement with no error bar. I ran the whole thing three more times with
nothing changed and compared.

| run | citation integrity | filings with no findings |
|---|---|---|
| 1 | 97.2% | 25/30 |
| 2 | 97.2% | 25/30 |
| 3 | 97.3% | 25/30 |

The citation numbers barely move. A tenth of a point across three runs, and the
same 25 clean filings every time. These three ran before the schema change
described below, so the level sits a little lower than the table at the top. The
spread is the part that matters, and it's small.

The COSO error repeats too. It showed up on JAAG in all three runs and on
Netlist in two of three. Counting the original run, that's three out of four for
each filing. It's a real failure, not a one off.

The weakness counts are a different story:

| filing | open weaknesses, per run |
|---|---|
| Trendmaker | 2, 1, 2 |
| Tribal Rides | 1, 1, 3 |

Same filing, same prompt, three different sessions, and the count moves. Tribal
Rides came out right once out of three. So the number of filings with a wrong
claim is anywhere from 2 to 4 of 30 depending on which run you look at, and both
of those errors are closer to a coin flip than a consistent bug.

That split is worth more than either number on its own. The citation mechanics
are stable enough to build on. Counting how many weaknesses a filing discloses
is not, and if you were shipping this you'd want that field decided by a rule or
a second pass rather than by one call.

## Is it the model, or is it Claude?

The COSO mistake is the one real model error here, and it had only ever been
seen on one model. So I ran the same 30 filings again on Sonnet 5, same prompt,
same gates, and checked the two filings where the framework is named without a
year.

| model | Netlist | JAAG |
|---|---|---|
| Opus 5 | NOT_STATED, wrong | OTHER, right |
| Sonnet 5 | NOT_STATED, wrong | NOT_STATED, wrong |

Sonnet gets both wrong. Opus gets one wrong here, and got JAAG wrong in all
three of the repeat runs above, so it isn't reliable on that filing either.

Two different models in the same family make the same mistake, which means this
isn't something a bigger model fixes. A rule is the right answer, which is why
there's one.

The rest of the comparison was more lopsided than I expected:

| | Opus 5 | Sonnet 5 |
|---|---|---|
| citation integrity | 96.6% | 83.5% |
| filings with no findings | 25/30 | 15/30 |
| claim errors | 5/30 | 5/30 |
| output tokens | 21,190 | 32,668 |
| cost | $1.19 | $0.59 |
| wall clock | 4 min | 5 min |

Both claim-error counts include CubeSmart and MARKY. This comparison ran with
true or false answers only, before the schema change below, so neither model had
a way to get those two right. Take them out and it's 3 each.

Integrity drops 13 points and the number of completely clean filings falls from
25 to 15, so twice as many filings come back with at least one bad citation.

The saving is smaller than the price list suggests too. Sonnet's rates are 2.5
times lower but it wrote 54% more output, so the bill only halves. It was also
slower on the clock for the same reason.

If citations are the product, halving the model cost and doubling the bad ones
isn't a trade worth making. Sonnet made one kind of error Opus didn't, as well:
it reported Tribal Rides' auditor opinion as NOT_REQUIRED when the filing never
mentions an auditor at all, which should be ABSENT. That's giving a reason the
document doesn't give.

## The schema was causing two of the errors

Two of the seven fields started out typed as a plain true or false:

```python
disclosure_controls_effective: Cited[bool, C]
icfr_effective: Cited[bool, C]
```

Two filings don't contain their own answer. One points to a page outside Item 9A
for management's report. The other explains what disclosure controls are and then
never concludes anything about them. With only true or false available, the model
had to pick one, and so did I when I was labeling.

So I added a third value, NOT_STATED, and ran the corpus again. The result was
better than I expected:

| | true/false | three values |
|---|---|---|
| citation integrity | 96.6% | 97.8% |
| filings with no findings | 25/30 | 26/30 |
| NOT_STATED used | n/a | 2 times |

It used the new value twice, on exactly the two filings that lack a conclusion,
and nowhere else in the other 28. No over-use at all.

So those two wrong answers were never the model's fault. The schema was forcing
them. Give it a way to say the section doesn't say, and it says that instead of
inventing a conclusion.

That's worth knowing if you're designing the output format for something like
this. A schema with no way to represent missing evidence doesn't prevent missing
evidence. It just converts it into a confident wrong answer.

I updated two of my own labels after this run for the same reason. I had recorded
an inferred true or false on those two filings with a note saying the section
never states it. The note was doing work the schema should have been doing.

Those two filings still showed a finding each after this run. That was my
checker, not the model, and it's the ninth bug below. With it fixed the numbers
are 98.9% and 28/30, which is what the table at the top shows.

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

Both prompts are in the repository. An instruction that looks obviously right,
makes no difference when you measure it, and quietly throws away information is
worth writing down.

## The part I didn't expect

The deterministic layer was buggier than the model it was checking.

- 9 defects in the verification layer, each found and fixed
- 4 harness failures that would have been scored as model defects
- 0 citations fabricated by the model

The first version of the support gate reported a 100% defect rate. Roughly 95%
of that was its own bugs. I'd written the patterns from what I assumed audit
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
same. That one mistake produced an apparent 23% claim-error rate. The real
figure is 10%, and the model had been right about every case I was counting
against it.

I built a whole gate on top of that misreading before checking it. The gate
scored zero true positives and one false positive. I reverted it rather than
tuning it, because tuning it would have been fitting noise.

The ninth turned up after the schema change. The check behind NOT_STATED asked
two questions of the whole section: does it state a conclusion anywhere, and
does it mention the subject anywhere. CubeSmart concludes about disclosure
controls and sends its ICFR report to another page. MARKY does the reverse. Both
words were in both sections, just never in the same sentence, so the check
flagged two answers the model had right. Now the subject and the conclusion have
to land in the same sentence. Quote-mode integrity went from 97.8% to 98.9%.

Checking code feels more trustworthy than a model, because you wrote it and you
can read it. Mine was wrong far more often than the model was. Every scary
number it gave me turned out to be worth less than the five minutes it took to
go and check whether the checker was right.

## What do the gates actually catch?

Everything above measures how often the gates fire. It says nothing about what
they miss, and a gate that quietly stopped working would look perfect on a clean
run.

Measuring that properly needs a labeled set of bad citations, and the corpus
barely has any, because the model's citations are mostly fine. I started reading
all 190 by hand and gave it up: past about eighty the answers stop being
considered, and a file of unconsidered verdicts is worse than no file.

So I broke the good citations instead. Take every citation that currently passes,
introduce one specific failure, and see whether the gates notice.

| what I broke | caught | rate |
|---|---|---|
| cited text that isn't in the document | 118/118 | 100% |
| cited the definitional boilerplate | 78/78 | 100% |
| kept the citation, inverted the claim | 108/108 | 100% |
| cited another field's passage | 108/118 | 92% |
| cut the quote before the conclusion | 86/117 | 74% |

Overall 92% of 539 introduced defects. Truncation is the weak spot, and it's
almost entirely one field:

| field | truncated quotes caught |
|---|---|
| control_framework | 93% |
| icfr_effective | 93% |
| disclosure_controls_effective | 87% |
| auditor_opinion | 21% |

That one is my fault and I can trace it. After the false positive rounds I
widened the auditor opinion patterns to accept the many ways filings phrase an
exemption or a cross reference. Those alternations match short fragments, so a
quote cut off before the conclusion still satisfies them. Widening the patterns
to stop them crying wolf cost most of their ability to catch a truncated quote.

I've left it rather than tightening it back, because the last seven times I
tightened a pattern it started flagging correct citations, and I'd rather report
the tradeoff with numbers than keep trading one failure for the other.

This runs in CI and fails the build under 85%.

What it doesn't tell you: these are defects I chose. A failure nobody thought of
is missing from the gates and from this table alike. Recall against real bad
citations is still unmeasured, and the honest reason is that I didn't want to
publish 190 verdicts I hadn't properly made.

## Does telling the model what's wrong help?

Every gate finding is a sentence explaining the problem, so the obvious next
question is whether handing that back to the model fixes anything. The answer
turned out to be yes, with one catch.

I ran it on the seven filings that had a support check finding, two in quote
mode and five in span, with up to two retries each. That cost $4.33.

| | quote | span |
|---|---|---|
| findings resolved | 2 | 13 |
| findings introduced | 0 | 1 |
| claim errors fixed | 1 | 3 |
| claim errors broken | 0 | 0 |

Four real errors corrected and nothing broken, which is better than I expected.

The number I actually cared about was whether it was fixing things or just
satisfying the checker. A model told "your span doesn't mention internal control
over financial reporting" can clear that by pointing somewhere that does, without
the new passage supporting the claim any better.

It didn't do that. Every time it revised an answer, it revised toward the value I
had labeled by hand:

| filing | before | after | my label |
|---|---|---|---|
| CubeSmart | EFFECTIVE | NOT_STATED | NOT_STATED |
| Netlist | NOT_STATED | OTHER | OTHER |
| MARKY | NOT_EFFECTIVE | NOT_STATED | NOT_STATED |
| JAAG | NOT_STATED | OTHER | OTHER |

Three of those are the undated COSO error and the two filings that don't state
their own answer, so gate feedback fixed exactly the failures this project spent
the most time identifying.

The other repair shape was widening a quote rather than changing an answer. Jones
Soda's citation started at "As a result of this assessment, management concluded
that we did not design and maintain effective controls", which never says
"internal control over financial reporting", so the subject check fired. The
repair extended the quote backwards to include the preceding sentence, which
does. Subject and conclusion, both present.

### The catch

One filing came back worse. Jones Soda picked up a new finding on a field that
had been fine:

```
quote is real but offsets are wrong: cited (6142,6510), actual (6265,6633)
```

A repair in span mode regenerates the whole record, so every offset gets
recomputed, and one that had been right came back 123 characters off. The retry
fixed the problem it was asked about and broke something else on the way past.

That's the same split as everywhere else here. Repair helps with the failures
that are about judgment and is a liability on the ones that are about arithmetic.
In quote mode, where the harness resolves offsets itself, there is nothing for a
retry to break: two resolved, none introduced.

Which lands on the same recommendation as the rest of the project. Use quote
mode, find the text yourself, and the repair loop becomes free upside.

## What happens when the document is a scan

Everything above runs on clean HTML from EDGAR, which is the easy half. Real
audit evidence is scanned paper and photographed pages, and I kept listing that
as out of scope. So I had a go at it.

Going to find real scanned filings would have meant losing the ground truth, and
the labels took long enough the first time. Instead the same 30 filings get
rendered to page images, roughed up the way a scanner does, and read back with
tesseract. Two versions of the same document, and the labels still apply.

The first number was not what I expected.

| | exact match | with the resolver |
|---|---|---|
| clean render, no damage | 0/73 | 72/73 |
| office scan | 0/73 | 73/73 |
| bad fax | 0/73 | 71/73 |

Not one citation of 73 survives `str.find` after a scan, including a render with
no degradation applied at all. It isn't OCR accuracy, which came back at 99% or
better. Laying text on a page re-wraps the lines, so the words are identical and
the whitespace isn't, and exact matching is byte exact.

Span resolution is the one gate that never fails on clean input. On a scan it
goes to zero.

The fix is a resolver that matches on a normalized copy and maps the position
back to the original text. Collapsing whitespace is the easy part. The mapping
is what needs care, because a citation that resolves to the wrong offsets is
worse than one that fails to resolve, since it looks checkable and isn't. It
also has to fold hyphens, because a line breaking at "Internal Control-
Integrated Framework" comes back as two words with a space in the middle.

That recovers 97 to 100% of what exact matching loses.

### The model reads a scan about as well as the file

| | clean text | OCR text |
|---|---|---|
| citation integrity | 98.9% | 95.5% |
| filings with no findings | 28/30 | 23/30 |
| wrong claims vs my labels | 3/30 | 2/30 |

Claim accuracy didn't move. Two versus three, and the repeat runs showed the
clean-text number wanders between two and four anyway. Whatever OCR costs you
here, it isn't comprehension.

### The failure that only exists on a scan

One citation traced back to the scan but not to the real document.

```
clean document:  pursuant to rules of the Securities and Exchange Commission
OCR output:      pursuant to tules of the Securities and Exchange Commission
```

One letter. The model then quoted the scan faithfully, "tules" and all. So the
citation resolves exactly against the document the system was handed, every gate
passes, the claim it supports is correct, and the sentence it quotes was never in
the filing.

Nothing in this project can catch that. The only copy the system ever sees is the
scan, and against the scan the citation is perfect. You would need the original
to know, and in a real workflow the scan is the original.

On clean HTML, a citation that resolves is a citation that's true. On a scan
those two come apart, and that is the part I would worry about if I were putting
this anywhere near real evidence.

Once, in 30 filings, so I'm not claiming a rate. The point is that the failure
exists at all and that no amount of verification against the provided document
will surface it.

### What this doesn't cover

The degradation is synthetic. Real scans have coffee stains, staples, skew from a
hand-fed page, and text that was never digital to begin with. My renderer also
wraps lines at hyphens, which creates some of the breakage I then measured, so
part of that 0/73 is my typesetting rather than a scanner. The direction is
right; treat the exact numbers as a floor on the difficulty rather than a
measurement of it.

## How it works

1. Pull Item 9A ("Controls and Procedures") from 30 filings through EDGAR.
   Section boundaries are harder than they look. The table of contents matches
   first, auditors cross-reference the item from inside their own reports, and
   amendments name it in an explanatory note before the section itself.
2. Extract one typed record per filing. Pydantic v2, fixed sets of allowed
   values, and a citation on every field.
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
uv run python -m citecheck.cli mutate --fail-under 0.85
```

`extract` picks up where it left off and refuses to start twice, after two runs
once wrote over each other without any error. `--repair N` feeds gate findings
back to the model and retries, `--only` limits a run to named filings, and
`--model` swaps the model. Exit codes: `0` pass, `1` below threshold, `2`
usage error, `3` no data.

CI runs on every push and needs no secrets. The corpus text, both extraction
runs and the hand labels are committed, so `report` reproduces these numbers
offline. It fails the build when citation integrity drops, which catches a gate
regression and not only a model one. A second workflow re-extracts a sample
against the labels to catch model drift. That one costs money, so it runs on
manual trigger:

```bash
gh workflow run drift.yml -f sample=5
```

## What this doesn't prove

- n = 30, two models, and the citation numbers repeat closely across runs. The
  COSO failure shows up on both models, but two models from one family is not
  the same as testing models generally.
- Public filings are clean HTML. The scan section above degrades them
  synthetically rather than using real scanned evidence, and real scans are
  worse than anything I generated. Messy enterprise data is still untouched.
- Item 9A only, not whole filings.
- I'm not an auditor. I learned the domain from primary sources over a weekend.
  The rules I applied are in [`docs/audit-notes.md`](docs/audit-notes.md),
  including every filing that caught me out, so you can check my reasoning
  instead of taking it on trust.
- Two filings don't contain their own answer. CubeSmart points to page F-2 for
  management's ICFR report, and MARKY never states a disclosure-controls
  conclusion at all. I labeled them by inference at first. Both are NOT_STATED
  now, which is all the section supports.
