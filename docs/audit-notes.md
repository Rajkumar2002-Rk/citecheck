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

## Naming the control framework

Almost every filing uses COSO's *Internal Control - Integrated Framework*. What
varies is whether they tell you which version. Seven spellings seen in 30
filings:

| how it appears | answer |
|---|---|
| "Integrated Framework (2013)" | COSO_2013 |
| "(2013 Framework)" / "(2013 framework)" | COSO_2013 |
| "issued by ... the Treadway Commission **in 2013**" | COSO_2013 |
| "("COSO - 2013")" / "("COSO-2013")" | COSO_2013 |
| "(commonly referred to as the "2013 COSO" framework)" | COSO_2013 |
| named once without a year, then again **with** it | COSO_2013 |
| COSO framework named, **no year anywhere** | OTHER |
| no framework named at all | NOT_STATED |

Two traps here. AEI names the framework twice and only the second mention
carries "(2013)", so stopping at the first occurrence gives the wrong answer.
And **OTHER is not the same as NOT_STATED**: OTHER means a framework is named
but you cannot pin the version (JAAG, Netlist); NOT_STATED means no framework is
named at all (CubeSmart).

## Auditor opinion, in order

1. Filing says the auditor is not required to report, or management's report was
   not subject to attestation → **NOT_REQUIRED** (common; small filers)
2. There is an actual auditor letter containing "In our opinion":
   - "…maintained, in all material respects, effective internal control…" →
     **UNQUALIFIED**
   - "…has not maintained effective internal control…" → **ADVERSE**
     (note: the adverse sentence rarely contains the word "adverse")
3. The report is mentioned but printed elsewhere, e.g. "included in Part II,
   Item 8", "appearing on page F-2", "which follows below" →
   **CROSS_REFERENCED**
4. No mention of an auditor anywhere → **ABSENT**

Two distinctions that caught me:

**CROSS_REFERENCED vs a real opinion.** The test is not where the report is
printed, it is whether Item 9A tells you what it concluded. Acme United says the
report "expresses an unqualified opinion" and then points elsewhere for the text
— you can answer, so answer UNQUALIFIED. Mayville says only that Deloitte "has
issued an attestation report ... which follows below" and never says what it
found, so CROSS_REFERENCED.

**NOT_REQUIRED vs ABSENT.** Both mean no opinion, but one is an explanation and
the other is a silence. NOT_REQUIRED is the filing telling you why there is no
report; the reasons vary and all count the same: smaller reporting company,
non-accelerated filer, emerging growth company, the permanent Section 404(b)
exemption, or "rules of the SEC that permit us to provide only management's
report". ABSENT is no mention of an auditor, attestation, accounting firm or
opinion anywhere in the section (Tribal Rides, INKY, MARKY). Silence is the more
interesting case for a citation tool, because there is nothing to cite.

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
- **Trendmaker** — the same weakness described twice, first plural then
  singular: *"identified material **weaknesses** related to the lack of requisite
  U.S. GAAP expertise of our Chief Financial Officer and our internal
  bookkeeper. This lack of expertise ... **constitutes a material weakness**."*
  Two people lacking one skill is one weakness. Answer is 1, not 2.
  The same filing then concludes ICFR ineffective *"due to the identified
  material weakness **and internal control deficiency** ... and the fact that the
  Company has failed to stay current in the filing of required periodic
  reports."* Only the first of those three is a material weakness — a
  **deficiency is a lower rung on the severity ladder**, and late filings are a
  consequence, not a control failure.
- **Titan Pharmaceuticals** — three paragraphs recounting last year's failure
  before stating this year's result. The sentence reading "disclosure controls
  and procedures ... were not effective" is dated **December 31, 2023** in a
  FY2024 filing. The current-year conclusion is in the opening paragraph and
  says effective.
- **Video Display** — fiscal year ends **February 28**, not December 31. The
  "not effective" conclusion belongs to the quarter ended November 30, and the
  weakness was remediated in Q4. Always read the date attached to a conclusion.
- **Endeavor Group** — two audit firms. Deloitte signs the opinion, but it reads
  *"based on our audit **and the report of KPMG LLP**"* — KPMG audited a
  subsidiary that is 39% of revenue. The auditor of record is Deloitte; the
  opinion depends on another firm's report that is not in the document.
- **Tribal Rides** — three weaknesses in one sentence: *"deficiencies involving
  lack of segregation of duties, lack of governance/oversight, and lack of
  internal control documentation that we believe to be material weaknesses."*
  The filing then refers to "this material weaknesses" and "the material
  weakness" in the singular throughout. Answer is 3.
- **INKY** and **MARKY** — weaknesses given as a numbered list, 1 through 4 and
  1 through 3. The easiest counts in the set once you find the list. INKY also
  dates its ICFR conclusion "November 31, 2022", a day that does not exist.
- **Acme United** — the attestation report lives elsewhere, but Item 9A states
  its outcome outright: *"which expresses an unqualified opinion"*. Answer the
  question when the section answers it.
- **CompX International** — the disclosure-controls conclusion is the last
  sentence of a 200-word paragraph that spends the first 190 defining what
  disclosure controls are. Nothing is hidden; it is just buried.
- **WidFit** — disclosure controls not effective, ICFR effective, and no material
  weakness disclosed anywhere. Legal, since disclosure controls are broader than
  ICFR, but unusual. The sentence itself reads *"are designed at a reasonable
  assurance level and are not effective"*, which looks like a template where
  both branches survived editing.
- **Annovis Bio** — exempt as an **emerging growth company**, a fourth distinct
  reason for NOT_REQUIRED.
- **MARKY** — Item 9A defines disclosure controls and then never states a
  conclusion about them. The answer is not in the section. Worth knowing because
  the model, asked for it anyway, cited the *ICFR* conclusion instead — it
  reached for the nearest adjacent sentence when the required one did not exist.

## Habits that prevent most errors

1. **Check the date on every conclusion.** A filing narrates last year before
   stating this year. If the sentence names the prior year end, it is history.
2. **Search for "weaknesses" plural.** If it never appears, the answer is 0 or 1
   and there is nothing hidden to hunt for.
3. **Read to the end of the paragraph.** Filings pack several weaknesses into
   one unbroken block with no bullets.
4. **A deficiency is not a material weakness.** Neither is a late filing.
5. **Scan for the word "concluded".** Every filing has it, and it sits exactly
   where the answer is. Faster than looking for headings, which vary.
6. **Check every mention of "Framework".** The version may only appear on the
   second one.

## What the labels caught

Three factual errors across 30 filings. Two are the same one.

| filing | labeled | model | |
|---|---|---|---|
| Netlist | OTHER | NOT_STATED | COSO framework named, no year given |
| JAAG Enterprises | OTHER | NOT_STATED | same, under a later prompt version |
| Tribal Rides | 3 | 1 | three weaknesses in one sentence |
| Trendmaker | 1 | 2 | counted late SEC filings as a weakness |

The repeating error is the undated framework. When a filing cites COSO's
*Internal Control - Integrated Framework* without saying 1992 or 2013, the model
reports that no framework was stated. That is not a small difference: the
company did name a framework, and reporting otherwise erases a disclosure it
made.

An earlier version of these notes claimed eight errors, almost all of them
material weakness counts. That was wrong, and the mistake is worth recording.
The comparison had been checking the hand-labeled count of weaknesses *open at
year end* against the number of weaknesses the model *listed* — which includes
remediated ones, each correctly tagged REMEDIATED. Two different definitions of
"count". The model had identified every remediated weakness correctly; the
scoring was what got it wrong.
