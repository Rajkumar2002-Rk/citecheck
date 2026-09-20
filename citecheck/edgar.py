"""SEC EDGAR client.

EDGAR needs no API key, but it does need a declared User-Agent carrying a real
contact address -- requests without one get blocked. The published ceiling is
10 requests/second; we stay well under it because nothing here is urgent.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace

import httpx

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data"

_MIN_INTERVAL = 0.2  # 5 req/s, half the published ceiling
_last_request = 0.0


def user_agent() -> str:
    ua = os.environ.get("EDGAR_USER_AGENT", "").strip()
    if not ua:
        raise RuntimeError(
            "Set EDGAR_USER_AGENT to 'Your Name your@email.com'. "
            "SEC blocks requests that do not declare a contact."
        )
    return ua


def _throttle() -> None:
    global _last_request
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _get(client: httpx.Client, url: str, *, attempts: int = 4, **kwargs) -> httpx.Response:
    """GET with backoff.

    EDGAR's full-text endpoint returns intermittent 500s that succeed on an
    identical retry seconds later -- observed on the same phrase three times in
    a row. Treat 5xx and timeouts as transient; let 4xx through immediately so a
    blocked User-Agent fails loudly instead of retrying into a ban.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        _throttle()
        try:
            resp = client.get(url, headers={"User-Agent": user_agent()}, timeout=30.0, **kwargs)
            if resp.status_code >= 500:
                last = httpx.HTTPStatusError(f"{resp.status_code} from {url}", request=resp.request, response=resp)
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise last


@dataclass(frozen=True)
class Filing:
    cik: str
    company: str
    form: str
    filed: str
    period: str
    accession: str
    document: str

    @property
    def slug(self) -> str:
        return f"{self.cik}_{self.accession.replace('-', '')}"

    @property
    def url(self) -> str:
        return f"{ARCHIVE}/{int(self.cik)}/{self.accession.replace('-', '')}/{self.document}"


def search(client: httpx.Client, phrase: str, *, forms: str = "10-K",
           start: str = "2023-01-01", end: str = "2025-12-31") -> list[Filing]:
    """Full-text search.

    Note: a hit means the phrase appears *somewhere* in the filing, very often
    in Item 1A risk-factor boilerplate rather than Item 9A. These results are
    candidates to read, never labels.
    """
    resp = _get(client, FTS_URL, params={
        "q": f'"{phrase}"', "forms": forms,
        "dateRange": "custom", "startdt": start, "enddt": end,
    })
    out = []
    for hit in resp.json()["hits"]["hits"]:
        src = hit["_source"]
        accession, _, document = hit["_id"].partition(":")
        out.append(Filing(
            cik=src["ciks"][0],
            company=src["display_names"][0],
            form=src["form"],
            filed=src["file_date"],
            period=src.get("period_ending", ""),
            accession=accession,
            document=document,
        ))
    return out


def resolve_primary_document(client: httpx.Client, filing: Filing) -> Filing:
    """Replace the full-text-search hit with the filing's primary document.

    Full-text search reports which *document* matched, which is frequently an
    exhibit rather than the 10-K itself -- Netlist's hit was the auditor consent
    letter (EX-23), 2kB of text with no Item 9A in it. The submissions API is
    authoritative about which document is the form.
    """
    data = _get(client, SUBMISSIONS.format(cik=filing.cik)).json()
    recent = data.get("filings", {}).get("recent", {})
    for accession, primary in zip(recent.get("accessionNumber", []),
                                  recent.get("primaryDocument", [])):
        if accession == filing.accession and primary:
            return replace(filing, document=primary)
    return filing


def fetch_document(client: httpx.Client, filing: Filing) -> str:
    return _get(client, filing.url).text
