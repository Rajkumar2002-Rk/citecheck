# Item 9A in plain English

Notes I made while hand-labeling 30 filings for the ground-truth set.

## What the document is

Every US public company must assess its own financial controls once a year and
report the result in **Item 9A** of its 10-K. Two separate assessments:

1. **Disclosure controls** (SEC Rules 13a-15(e)/15d-15(e)) — do we capture the
   right information and get it into our filings on time? The CEO and CFO
   personally conclude effective or not effective.
2. **ICFR**, internal control over financial reporting (SOX §404(a)) — are the
   accounting processes reliable enough that the numbers can be trusted?
   Management must name the framework it measured against, almost always
   *COSO Internal Control – Integrated Framework (2013)*.

A third piece appears only for larger companies: the **auditor's attestation**
under SOX §404(b), a separate opinion from the audit firm on ICFR. Smaller
reporting companies and non-accelerated filers are exempt and say so.

## The severity ladder

- **Control deficiency** — a control doesn't work as designed. Not disclosed.
- **Significant deficiency** — reported to the audit committee. Usually not
  disclosed in Item 9A.
- **Material weakness** — *"a deficiency, or combination of deficiencies, such
  that there is a reasonable possibility that a material misstatement will not
  be prevented or detected on a timely basis."*

Note what the definition does not say: nothing was necessarily misstated. It is
about **possibility**. Financial statements can be correct and the controls that
produced them still deficient.

## The load-bearing rule

**If a material weakness exists at fiscal year end, ICFR cannot be effective.**
That is a rule, not a heuristic.

But it turns on *existing at year end*, which is where the judgment lives:

| the filing says | does it count? |
|---|---|
| "remediated as of [year-end date]" | **No** — fixed, historical |
| "continues to exist as of [year-end date]" | **Yes** — still open |
| newly identified this year | **Yes** |
| "we will implement a remediation plan" | **Yes** — not fixed yet |

A filing can list three weaknesses and have one open. It can also bury two
still-open ones from prior years inside a single paragraph. Read to the end of
the paragraph every time.

Quick check: if the word **"weaknesses"** (plural) never appears in the section,
the answer is 0 or 1 and there is nothing to hunt for.

## Auditor opinion, in order

1. Filing says the auditor is not required to report, or management's report was
   not subject to attestation → **NOT_REQUIRED** (common; small filers)
2. There is an actual auditor letter containing "In our opinion":
   - "…maintained, in all material respects, effective internal control…" →
     **UNQUALIFIED**
   - "…has not maintained effective internal control…" → **ADVERSE**
     (note: the adverse sentence rarely contains the word "adverse")
3. The report is mentioned but printed elsewhere, e.g. "in the F-pages" →
   **CROSS_REFERENCED**
4. No mention of an auditor anywhere → **ABSENT**

## Traps I actually hit

- **Alta Equipment** — three weaknesses mentioned, two remediated during the
  year. Answer is 1, not 3.
- **Southport Acquisition** — three weaknesses in one unbroken paragraph, two of
  them carried over from prior years and explicitly "continuing to exist".
  Answer is 3, not 1.
- **Advance Auto Parts** — reads as if there might be several; the word
  "weaknesses" appears zero times. Answer is 1.
- **FlexShopper** — two weaknesses, one remediated and one open in the same
  section. Answer is 1.
- **CubeSmart** — management's ICFR conclusion is incorporated by reference to
  page F-2 and is not in Item 9A at all.
- **Netlist** — names COSO but gives no year, so the framework is not cleanly
  COSO_2013.
- **SkyWater** — a page number (`107`) sits inside a sentence, splitting the
  conclusion in half.

## Two extraction errors the labels caught

Both the same failure: the model counted a material weakness the filing said had
been remediated.

- SkyWater: model 2, correct 1.
- Empire State Realty: model 1, correct 0.

A remediated weakness and a live one have opposite consequences in an audit, so
conflating them is not a rounding error.
