"""Did feeding gate findings back to the model actually fix anything?

"The gate stopped firing" is not the same as "the citation is now right". A
model told its span doesn't mention the subject can satisfy that by pointing
somewhere else that does, without the new passage supporting the claim any
better. So this reports what changed, not just whether the finding cleared.
"""
import json
from pathlib import Path

from citecheck.labels import diff, load_labels
from citecheck.schema import QuoteExtraction, SpanExtraction

labels = load_labels()
PAIRS = [("quote", "data/quote_pass1.jsonl", "data/repair_quote.jsonl", QuoteExtraction),
         ("span", "data/span_pass1.jsonl", "data/repair_span.jsonl", SpanExtraction)]

for mode, base_path, repair_path, cls in PAIRS:
    if not Path(repair_path).exists():
        print(f"{mode}: no repair run yet\n")
        continue
    base = {json.loads(l)["text_file"]: json.loads(l)
            for l in Path(base_path).read_text().splitlines()
            if l.strip() and "extraction" in json.loads(l)}

    resolved = introduced = fixed_claims = broke_claims = 0
    value_edits = quote_edits = both = 0
    print(f"===== {mode} =====")
    for line in Path(repair_path).read_text().splitlines():
        if not line.strip():
            continue
        after = json.loads(line)
        if "extraction" not in after:
            continue
        before = base[after["text_file"]]
        name = after["company"].split("(")[0].strip()[:24]

        was = {f["field"] for f in before.get("findings", [])}
        now = {f["field"] for f in after.get("findings", [])}
        resolved += len(was - now)
        introduced += len(now - was)

        bl = {m.field for m in diff(cls.model_validate(before["extraction"]),
                                    labels.get(after["text_file"], {}))}
        al = {m.field for m in diff(cls.model_validate(after["extraction"]),
                                    labels.get(after["text_file"], {}))}
        fixed_claims += len(bl - al)
        broke_claims += len(al - bl)

        for field in sorted(was):
            fb = before["extraction"].get(field)
            fa = after["extraction"].get(field)
            if not isinstance(fb, dict) or not isinstance(fa, dict):
                continue
            v = fb["value"] != fa["value"]
            q = fb["citation"]["quote"] != fa["citation"]["quote"]
            kind = "value+quote" if v and q else "value" if v else "quote" if q else "no change"
            both += v and q; value_edits += v and not q; quote_edits += q and not v
            state = "cleared" if field not in now else "still flagged"
            print(f"  {name:26} {field[:30]:32} {kind:12} {state}")

    print(f"\n  findings resolved {resolved}, newly introduced {introduced}")
    print(f"  claim errors fixed {fixed_claims}, newly broken {broke_claims}")
    print(f"  edit type: value only {value_edits}, quote only {quote_edits}, both {both}\n")
