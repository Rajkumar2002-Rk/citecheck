from __future__ import annotations

import os
from pathlib import Path

import json

import typer
from rich.console import Console
from rich.table import Table

from . import corpus, labels

app = typer.Typer(add_completion=False, help="Citation verification harness for Item 9A extraction.")
console = Console()


@app.command()
def discover(limit: int = typer.Option(10, help="Candidates per search phrase.")):
    """Search EDGAR for candidate filings and write data/candidates.json."""
    filings, dead = corpus.discover(limit)
    corpus.DATA.mkdir(exist_ok=True)
    (corpus.DATA / "candidates.json").write_text(
        json.dumps([f.__dict__ for f in filings], indent=2), encoding="utf-8"
    )
    table = Table("company", "form", "filed", "period")
    for f in filings:
        table.add_row(f.company[:52], f.form, f.filed, f.period)
    console.print(table)
    for phrase in dead:
        console.print(f"  [yellow]EDGAR 500, phrase skipped:[/] {phrase!r}")
    console.print(f"[green]{len(filings)} candidates ->[/] data/candidates.json")


@app.command()
def build(target: int = typer.Option(corpus.TARGET, help="Corpus size.")):
    """Download candidates, extract Item 9A, and select a balanced corpus."""
    from .edgar import Filing

    raw = json.loads((corpus.DATA / "candidates.json").read_text())
    pool = corpus.extract_pool([Filing(**r) for r in raw])
    chosen = corpus.select(pool, target)
    corpus.write_corpus(chosen)

    table = Table("company", "form", "chars", "404(b)", "MW", "not eff")
    for r in sorted(chosen, key=lambda x: x["company"]):
        table.add_row(
            r["company"].split("(")[0].strip()[:34], r["form"], str(r["length"]),
            "attested" if r["attested"] else "exempt",
            "yes" if r["mentions_material_weakness"] else "-",
            "yes" if r["asserts_not_effective"] else "-",
        )
    console.print(table)
    console.print(
        f"[green]{len(chosen)} filings[/] from a pool of {len(pool)} -> data/manifest.json"
    )




@app.command("label-template")
def label_template(force: bool = typer.Option(False, help="Overwrite an existing labels.csv.")):
    """Write data/labels.csv with one blank row per filing."""
    try:
        path = labels.write_template(force=force)
    except FileExistsError as exc:
        raise typer.Exit(code=2) from exc
    console.print(f"[green]wrote[/] {path} -- {len(labels.COLUMNS)} columns, one row per filing")
    console.print(f"scored fields: {', '.join(labels.SCORED)}")


@app.command()
def show(
    index: int = typer.Argument(..., help="Row number in the manifest, 1-based."),
    full: bool = typer.Option(False, "--full", help="Print the raw section, unsplit."),
):
    """Print one filing's Item 9A, split into subsections, for labeling."""
    from .reader import sections, trim

    filings = json.loads((corpus.DATA / "manifest.json").read_text())["filings"]
    if not 1 <= index <= len(filings):
        console.print(f"[red]index must be 1..{len(filings)}[/]")
        raise typer.Exit(code=2)
    filing = filings[index - 1]
    text = (corpus.TEXT / filing["text_file"]).read_text(encoding="utf-8")

    console.print(f"[bold]{filing['company']}[/]  {filing['form']}  filed {filing['filed']}")
    console.print(f"[dim]filing {index}/{len(filings)}  {filing['length']} chars[/]")
    console.print(f"[dim]{filing['url']}[/]\n")

    if full:
        console.print(text)
        return

    for heading, body in sections(text):
        kept, dropped = trim(body)
        if not kept:
            continue
        note = f"  [dim](-{dropped} boilerplate para)[/]" if dropped else ""
        console.print(f"[bold cyan]{'-' * 70}[/]")
        console.print(f"[bold cyan]{heading}[/]{note}")
        console.print(f"[bold cyan]{'-' * 70}[/]")
        console.print(kept + "\n")


# Exit codes, mirroring medeval-harness so CI can branch on them.
EXIT_OK = 0
EXIT_BELOW_THRESHOLD = 1
EXIT_USAGE = 2
EXIT_NO_DATA = 3


@app.command()
def report(
    fail_under: float = typer.Option(
        None, "--fail-under",
        help="Minimum citation integrity rate (0-1). Exit 1 if any mode falls below."),
    mode: str = typer.Option(None, help="Restrict gating to one mode: span or quote."),
    json_out: bool = typer.Option(False, "--json", help="Print the raw report as JSON."),
):
    """Summarize run artifacts into the defect taxonomy."""
    from .report import build

    data = build()
    if json_out:
        console.print_json(json.dumps(data))
        raise typer.Exit(code=EXIT_OK)

    if mode and mode not in data["modes"]:
        console.print(f"[red]unknown mode {mode!r}[/]")
        raise typer.Exit(code=EXIT_USAGE)

    active = {m: s for m, s in data["modes"].items() if s["filings"]}
    if not active:
        console.print("[red]no completed extractions found[/] -- run the extraction first")
        raise typer.Exit(code=EXIT_NO_DATA)

    console.print(f"corpus {data['corpus_filings']} filings, "
                  f"[{'green' if data['labeled_filings'] else 'yellow'}]"
                  f"{data['labeled_filings']} labeled[/]")

    table = Table("metric", *active)
    rows = [
        ("filings extracted", "filings"),
        ("cited fields", "cited_fields"),
        ("clean filings", "clean_filings"),
        ("A: fabricated quote", "type_a_fabricated"),
        ("A: offset arithmetic", "type_a_arithmetic"),
        ("B: unsupported", "type_b"),
        ("C: wrong location", "type_c"),
        ("D: detected", "type_d_detected"),
        ("D: undetected", "type_d_undetected"),
        ("unadjudicated (no labels)", "unadjudicated"),
        ("cross-field inconsistency", "consistency"),
    ]
    for label, key in rows:
        table.add_row(label, *[str(active[m][key]) for m in active])
    table.add_row("cost (USD)", *[f"${active[m]['cost_usd']:.2f}" for m in active])
    table.add_row("wall clock (min)", *[f"{active[m]['seconds']/60:.0f}" for m in active])
    console.print(table)

    integrity = {}
    for m, s in active.items():
        bad = s["type_a_fabricated"] + s["type_a_arithmetic"] + s["type_b"]
        integrity[m] = 1 - (bad / s["cited_fields"]) if s["cited_fields"] else 0.0
        console.print(f"  {m}: citation integrity {integrity[m]:.1%} "
                      f"({s['cited_fields'] - bad}/{s['cited_fields']} fields)")

    if data["labeled_filings"] < data["corpus_filings"]:
        console.print("[yellow]C and D are unadjudicated: ground truth is incomplete. "
                      "Do not quote a type B rate from this table.[/]")

    if fail_under is None:
        raise typer.Exit(code=EXIT_OK)
    if not 0 <= fail_under <= 1:
        console.print("[red]--fail-under must be between 0 and 1[/]")
        raise typer.Exit(code=EXIT_USAGE)

    checked = {mode: integrity[mode]} if mode else integrity
    failed = {m: v for m, v in checked.items() if v < fail_under}
    for m, v in failed.items():
        console.print(f"[red]FAIL[/] {m}: {v:.1%} < {fail_under:.1%}")
    raise typer.Exit(code=EXIT_BELOW_THRESHOLD if failed else EXIT_OK)


@app.command()
def label(index: int = typer.Argument(None, help="Filing number; omit for the next unlabeled one.")):
    """Guided prompts for one filing's ground-truth row."""
    from .schema import AuditorOpinion, ControlFramework, Effectiveness

    rows = labels.read_rows()
    if index is None:
        pending = [i for i, r in enumerate(rows, 1) if not labels.is_labeled(r)]
        if not pending:
            console.print("[green]all 30 filings labeled[/] -- run `report`")
            raise typer.Exit(code=0)
        index = pending[0]
    if not 1 <= index <= len(rows):
        console.print(f"[red]index must be 1..{len(rows)}[/]")
        raise typer.Exit(code=2)

    row = rows[index - 1]
    done = sum(1 for r in rows if labels.is_labeled(r))
    console.print(f"[bold]{row['company']}[/]")
    console.print(f"[dim]filing {index}/{len(rows)} -- {done} labeled so far[/]\n")

    def ask_effectiveness(prompt: str) -> str:
        console.print("[dim]EFFECTIVE / NOT_EFFECTIVE / NOT_STATED"
                      " (use NOT_STATED when the section never concludes)[/]")
        while True:
            raw = typer.prompt(prompt).strip().upper()
            if raw in {"T", "TRUE", "Y", "YES", "1"}:
                return "EFFECTIVE"
            if raw in {"F", "FALSE", "N", "NO", "0"}:
                return "NOT_EFFECTIVE"
            matches = [o for o in Effectiveness.__members__ if o.startswith(raw)] if raw else []
            if raw in Effectiveness.__members__:
                return raw
            if len(matches) == 1:
                return matches[0]
            console.print("[yellow]enter EFFECTIVE, NOT_EFFECTIVE or NOT_STATED[/]")

    def ask_choice(prompt: str, enum) -> str:
        options = list(enum.__members__)
        console.print(f"[dim]{' / '.join(options)}[/]")
        while True:
            raw = typer.prompt(prompt).strip().upper()
            matches = [o for o in options if o.startswith(raw)] if raw else []
            if raw in options:
                return raw
            if len(matches) == 1:
                console.print(f"[dim]-> {matches[0]}[/]")
                return matches[0]
            console.print("[yellow]no unique match; type more characters[/]")

    values = {
        "disclosure_controls_effective": ask_effectiveness("Disclosure controls"),
        "icfr_effective": ask_effectiveness("ICFR"),
    }
    while True:
        raw = typer.prompt("Material weaknesses OPEN at fiscal year end (count)").strip()
        if raw.isdigit():
            values["material_weakness_count"] = raw
            break
        console.print("[yellow]enter a whole number[/]")
    values["material_weakness_summary"] = typer.prompt(
        "Summary (semicolon-separated, blank if none)", default="", show_default=False)
    values["control_framework"] = ask_choice("Control framework", ControlFramework)
    values["auditor_opinion"] = ask_choice("Auditor opinion", AuditorOpinion)
    values["auditor_name"] = typer.prompt("Auditor name (blank if none)", default="",
                                          show_default=False)
    values["notes"] = typer.prompt("Notes / ambiguities", default="", show_default=False)

    labels.save_row(row["text_file"], values)
    console.print(f"[green]saved[/] filing {index} -- {done + 1}/{len(rows)} labeled")


@app.command()
def drift(
    sample: int = typer.Option(5, help="Filings to re-extract, taken in manifest order."),
    mode: str = typer.Option("quote", help="Citation mode: quote or span."),
    min_integrity: float = typer.Option(0.90, help="Minimum citation integrity."),
    max_claim_errors: int = typer.Option(2, help="Maximum filings with a wrong claim."),
):
    """Re-extract a sample and compare against the committed labels.

    This is the only command that spends money. It exists to catch drift: the
    model changing behaviour, a prompt edit regressing quality, or a gate that
    silently stopped firing. The corpus text and the labels are committed, so
    this needs no network access to EDGAR.
    """
    import anthropic

    from .extract import extract
    from .gates import run_gates
    from .labels import diff, load_labels
    from .report import MODELS

    labels = load_labels()
    if not labels:
        console.print("[red]no labels found[/] -- run `label` first")
        raise typer.Exit(code=EXIT_NO_DATA)

    filings = json.loads((corpus.DATA / "manifest.json").read_text())["filings"][:sample]
    client = anthropic.Anthropic()

    fields = bad = claim_errors = 0
    table = Table("filing", "fields", "citation findings", "wrong claims")
    for filing in filings:
        text = (corpus.TEXT / filing["text_file"]).read_text(encoding="utf-8")
        attempt = extract(client, text, mode=mode)
        if attempt.parsed is None:
            console.print(f"[red]extraction failed[/] {filing['company'][:40]}: {attempt.error}")
            raise typer.Exit(code=EXIT_NO_DATA)

        result = run_gates(attempt.parsed, text, mode=mode)
        record = MODELS[mode].model_validate(attempt.parsed.model_dump(mode="json"))
        mismatches = diff(record, labels.get(filing["text_file"], {}))

        fields += 4 + 2 * len(attempt.parsed.material_weaknesses)
        bad += len(result.findings)
        claim_errors += 1 if mismatches else 0
        table.add_row(filing["company"].split("(")[0].strip()[:30],
                      str(4 + 2 * len(attempt.parsed.material_weaknesses)),
                      str(len(result.findings)),
                      ", ".join(m.field for m in mismatches) or "-")

    console.print(table)
    integrity = 1 - (bad / fields) if fields else 0.0
    console.print(f"citation integrity {integrity:.1%} | filings with a wrong claim "
                  f"{claim_errors}/{len(filings)}")

    failed = []
    if integrity < min_integrity:
        failed.append(f"citation integrity {integrity:.1%} < {min_integrity:.1%}")
    if claim_errors > max_claim_errors:
        failed.append(f"{claim_errors} filings with wrong claims > {max_claim_errors}")
    for reason in failed:
        console.print(f"[red]FAIL[/] {reason}")
    raise typer.Exit(code=EXIT_BELOW_THRESHOLD if failed else EXIT_OK)


@app.command("extract")
def extract_all(
    mode: str = typer.Option("quote", help="Citation mode: quote or span."),
    prompt: int = typer.Option(1, help="Prompt version: 1 baseline, 2 adds the remediation rule."),
    out: Path = typer.Option(None, help="Output JSONL. Defaults to data/<mode>_v<prompt>.jsonl."),
    repair: int = typer.Option(0, help="Extra attempts on gate failure, feeding the findings back."),
    limit: int = typer.Option(0, help="Stop after N filings. 0 means all."),
    model: str = typer.Option(None, help="Model id. Defaults to the project default."),
):
    """Extract every filing, verify it, and write one JSON record per filing.

    Resumable: filings already present in the output file are skipped, so an
    interrupted run costs nothing to continue. A single run is enforced with a
    lockfile, because two processes writing the same file silently interleaved
    an entire pass once.
    """
    import anthropic

    from .extract import MODEL
    from .extract import extract as extract_one
    from .gates import run_gates

    model = model or MODEL

    if mode not in ("span", "quote"):
        console.print(f"[red]unknown mode {mode!r}[/]")
        raise typer.Exit(code=EXIT_USAGE)

    out = out or corpus.DATA / f"{mode}_v{prompt}.jsonl"
    lock = corpus.DATA / f".{out.stem}.lock"
    if lock.exists():
        try:
            os.kill(int(lock.read_text().strip()), 0)
            console.print(f"[red]a run is already active[/] (pid {lock.read_text().strip()})")
            raise typer.Exit(code=EXIT_USAGE)
        except (ProcessLookupError, ValueError):
            pass
    lock.write_text(str(os.getpid()))

    try:
        done = set()
        if out.exists():
            done = {json.loads(line)["text_file"] for line in out.read_text().splitlines()
                    if line.strip() and "extraction" in json.loads(line)}
        if done:
            console.print(f"[dim]resuming: {len(done)} filings already done[/]")

        filings = json.loads((corpus.DATA / "manifest.json").read_text())["filings"]
        if limit:
            filings = filings[:limit]
        client = anthropic.Anthropic()

        with out.open("a") as handle:
            for index, filing in enumerate(filings, 1):
                if filing["text_file"] in done:
                    continue
                text = (corpus.TEXT / filing["text_file"]).read_text(encoding="utf-8")

                feedback, attempt, result = None, None, None
                for _ in range(repair + 1):
                    attempt = extract_one(client, text, mode=mode, version=prompt,
                                          repair=feedback, model=model)
                    if attempt.parsed is None:
                        break
                    result = run_gates(attempt.parsed, text, mode=mode)
                    if result.passed:
                        break
                    feedback = result.repair_prompt()

                record = {"company": filing["company"], "text_file": filing["text_file"],
                          "length": filing["length"], "model": model,
                          "error": attempt.error,
                          "stop": attempt.stop_reason, "in": attempt.input_tokens,
                          "out": attempt.output_tokens, "sec": round(attempt.seconds, 1)}
                if attempt.error and "credit balance" in attempt.error:
                    # Every later call fails identically; writing 20 more error
                    # records helps nobody.
                    console.print("[red]stopping: account is out of credits[/]")
                    break
                if attempt.parsed is not None:
                    record["extraction"] = attempt.parsed.model_dump(mode="json")
                    record["findings"] = [f.as_dict() for f in result.findings]
                    record["passed"] = result.passed

                handle.write(json.dumps(record) + "\n")
                handle.flush()
                tag = "FAILED" if attempt.parsed is None else f"findings={len(record['findings'])}"
                console.print(f"[dim][{index}/{len(filings)}][/] "
                              f"{filing['company'].split('(')[0].strip()[:30]:32} {tag}")
        console.print(f"[green]done[/] -> {out}")
    finally:
        lock.unlink(missing_ok=True)


@app.command("label-citations")
def label_citations(
    run: Path = typer.Option(Path("data/quote_pass1.jsonl"), help="Run to label."),
    start: int = typer.Option(0, help="Skip ahead to this position."),
):
    """Judge each citation one at a time: does the quoted text state the claim?

    This is what makes gate recall measurable. The claim labels only say whether
    a value was right, so a gate that misses every bad citation still scores well
    if the values happened to be correct.
    """
    from .citations import BAD, GOOD, UNSURE, context, iter_citations, load_verdicts, save_verdict

    citations = iter_citations(run)
    done = load_verdicts()
    todo = [c for c in citations if c.key not in done][start:]
    if not todo:
        console.print(f"[green]all {len(citations)} citations labeled[/]")
        raise typer.Exit(code=EXIT_OK)

    console.print(f"[dim]{len(done)}/{len(citations)} done, {len(todo)} to go. "
                  f"g = supports the claim, b = does not, u = unsure, q = stop[/]\n")

    for index, citation in enumerate(todo, 1):
        console.print(f"[bold cyan]{'-' * 74}[/]")
        console.print(f"[dim]{len(done) + index}/{len(citations)}[/]  "
                      f"[bold]{citation.company[:38]}[/]")
        console.print(f"  field  [bold]{citation.field}[/] = [bold]{citation.value}[/]")
        console.print(f"  quote  [yellow]{citation.quote[:300]}[/]")
        console.print(f"[dim]  context ...{' '.join(context(citation).split())[:420]}...[/]")

        while True:
            answer = typer.prompt("  supports it?").strip().lower()[:1]
            if answer in {"g", "b", "u", "q"}:
                break
            console.print("  [yellow]g, b, u or q[/]")
        if answer == "q":
            break
        note = ""
        if answer in {"b", "u"}:
            note = typer.prompt("  why (optional)", default="", show_default=False)
        save_verdict(citation, {"g": GOOD, "b": BAD, "u": UNSURE}[answer], note)

    remaining = len([c for c in citations if c.key not in load_verdicts()])
    console.print(f"\n[green]saved[/]. {len(citations) - remaining}/{len(citations)} labeled, "
                  f"{remaining} left.")


if __name__ == "__main__":
    app()
