"""Build the Item 9A corpus: discover candidates, extract, then balance."""
from __future__ import annotations

import json
from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from .classify import describe
from .edgar import Filing, fetch_document, resolve_primary_document, search
from .sections import SUSPECT_BODY, SectionNotFound, find_item_9a
from .textify import html_to_text

DATA = Path("data")
RAW = DATA / "raw"
TEXT = DATA / "text"
POOL = DATA / "pool.json"
MANIFEST = DATA / "manifest.json"

# Phrases that tend to sit in Item 9A itself rather than in risk factors. Still
# only candidate generators -- every label is made by reading the section.
ADVERSE_PHRASES = [
    "we identified a material weakness",
    "the following material weaknesses",
    "did not maintain effective internal control over financial reporting",
    "material weakness in our internal control over financial reporting",
    "remediation of the material weakness",
]
CLEAN_PHRASES = [
    "concluded that our internal control over financial reporting was effective",
    "our internal control over financial reporting was effective as of December 31, 2024",
    "expressed an unqualified opinion on the effectiveness",
]

# Amendments are over-represented by adverse-language search because companies
# that restate are exactly who amends. They are also unusually confusing prose,
# which would inflate the headline defect rate for reasons that have nothing to
# do with the model. Cap them.
MAX_AMENDMENTS = 6
TARGET = 30


def discover(limit_per_phrase: int = 10) -> tuple[list[Filing], list[str]]:
    """Returns (candidates, phrases that failed).

    Some phrases 500 persistently while others succeed in the same run; EDGAR
    appears to give up on queries whose terms are individually very common. A
    dead phrase must not take the whole discovery run with it.
    """
    seen: dict[str, Filing] = {}
    dead: list[str] = []
    with httpx.Client() as client:
        for phrase in ADVERSE_PHRASES + CLEAN_PHRASES:
            try:
                hits = search(client, phrase)
            except httpx.HTTPError:
                dead.append(phrase)
                continue
            for filing in hits[:limit_per_phrase]:
                # Prefer an original 10-K over an amendment for the same issuer.
                prior = seen.get(filing.cik)
                if prior is None or (prior.form != "10-K" and filing.form == "10-K"):
                    seen[filing.cik] = filing
    return list(seen.values()), dead


def extract_pool(filings: list[Filing]) -> list[dict]:
    """Download and extract every candidate, keeping raw HTML cached on disk."""
    for directory in (RAW, TEXT):
        directory.mkdir(parents=True, exist_ok=True)

    pool, failures = [], []
    with httpx.Client() as client:
        for filing in filings:
            try:
                filing = resolve_primary_document(client, filing)
                raw_path = RAW / f"{filing.slug}.htm"
                if raw_path.exists():
                    raw = raw_path.read_text(encoding="utf-8", errors="replace")
                else:
                    raw = fetch_document(client, filing)
                    raw_path.write_text(raw, encoding="utf-8")
                section = find_item_9a(html_to_text(raw))
            except (httpx.HTTPError, SectionNotFound) as exc:
                failures.append({**asdict(filing), "error": f"{type(exc).__name__}: {exc}"})
                continue

            pool.append({
                **asdict(filing),
                "url": filing.url,
                "text_file": f"{filing.slug}.txt",
                "doc_offset": section.start,
                "length": section.length,
                "suspect_length": section.length > SUSPECT_BODY,
                "section": section.text,
                **describe(section.text),
            })

    DATA.mkdir(exist_ok=True)
    POOL.write_text(json.dumps({"pool": pool, "failures": failures}, indent=2), encoding="utf-8")
    return pool


def select(pool: list[dict], target: int = TARGET) -> list[dict]:
    """Pick a balanced subset: originals over amendments, attested vs exempt
    roughly even, and enough disclosed weaknesses to produce a rate."""
    half = target // 2
    quotas = {("attested", True): half, ("attested", False): target - half}
    # Balance disclosed weaknesses against clean filings. An all-adverse corpus
    # cannot measure fabrication: a model can only invent a material weakness
    # in a filing that does not disclose one.
    mw_quota = {True: half, False: target - half}
    chosen: list[dict] = []
    amendments = 0

    def fits(rec: dict) -> bool:
        nonlocal amendments
        if rec["form"] != "10-K" and amendments >= MAX_AMENDMENTS:
            return False
        if mw_quota[rec["mentions_material_weakness"]] <= 0:
            return False
        return quotas.get(("attested", rec["attested"]), 0) > 0

    # Originals first, then weakness-bearing filings, so the adverse cases that
    # survive are the ones carrying real disclosures.
    # Dual registrants (a REIT and its operating partnership, say) file one
    # combined document under two CIKs. Their Item 9A text is all but
    # identical, so keeping both would double-count a single disclosure.
    # An exact fingerprint does not catch these: the two filings differ only by
    # the registrant's own name appearing throughout, so compare by similarity.
    deduped: list[dict] = []
    for rec in pool:
        if rec["suspect_length"]:
            continue
        head = " ".join(rec["section"].split())[:2000].lower()
        if any(SequenceMatcher(None, head, seen).quick_ratio() > 0.92
               and SequenceMatcher(None, head, seen).ratio() > 0.92
               for seen in (d["_head"] for d in deduped)):
            continue
        deduped.append({**rec, "_head": head})
    for rec in deduped:
        rec.pop("_head")

    ordered = sorted(
        deduped,
        key=lambda r: (r["form"] != "10-K", not r["mentions_material_weakness"], -r["length"]),
    )
    for rec in ordered:
        if len(chosen) >= target or not fits(rec):
            continue
        quotas[("attested", rec["attested"])] -= 1
        mw_quota[rec["mentions_material_weakness"]] -= 1
        if rec["form"] != "10-K":
            amendments += 1
        chosen.append(rec)

    # Quotas are a preference, not a hard constraint: intersecting them exactly
    # can leave the corpus short. Top up with the best remaining candidates.
    if len(chosen) < target:
        picked = {r["accession"] for r in chosen}
        for rec in ordered:
            if len(chosen) >= target:
                break
            if rec["accession"] in picked:
                continue
            if rec["form"] != "10-K" and amendments >= MAX_AMENDMENTS:
                continue
            if rec["form"] != "10-K":
                amendments += 1
            chosen.append(rec)
    return chosen


def write_corpus(chosen: list[dict]) -> dict:
    TEXT.mkdir(parents=True, exist_ok=True)
    for stale in TEXT.glob("*.txt"):
        stale.unlink()

    records = []
    for rec in chosen:
        rec = dict(rec)
        section = rec.pop("section")
        (TEXT / rec["text_file"]).write_text(section, encoding="utf-8")
        records.append(rec)

    manifest = {"filings": records}
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
