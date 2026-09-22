"""What a scan costs, measured on documents we hold clean copies of."""
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from citecheck.citations import iter_citations
from citecheck.corpus import TEXT
from citecheck.resolve import resolve
from citecheck.scan import Degradation, scan

LEVELS = {"clean render": Degradation.clean(),
          "office scan": Degradation(),
          "bad fax": Degradation.rough()}


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


citations = {}
for c in iter_citations(Path("data/quote_pass1.jsonl")):
    citations.setdefault(c.text_file, []).append(c)

sample = json.loads(Path("data/manifest.json").read_text())["filings"][:10]

print(f"{'level':14} {'char sim':>9} {'exact':>8} {'+resolver':>11} {'lost':>6} {'recovered':>11}")
for label, how in LEVELS.items():
    sims = Counter()
    exact = found = total = 0
    for filing in sample:
        clean = (TEXT / filing["text_file"]).read_text(encoding="utf-8")
        scanned = scan(clean, how)
        sims[label] += SequenceMatcher(None, norm(clean), norm(scanned)).ratio()
        for c in citations.get(filing["text_file"], []):
            total += 1
            hit = resolve(c.quote, scanned)
            exact += bool(hit and hit.exact)
            found += bool(hit)
    sim = sims[label] / len(sample)
    print(f"{label:14} {sim:>8.1%} {exact:>5}/{total:<3} {found:>7}/{total:<3} "
          f"{total - found:>5} {(found - exact) / total:>10.0%}")

print("\nOffsets the resolver returns are into the scanned text, so a citation it")
print("recovers still points at the right passage rather than merely existing.")
