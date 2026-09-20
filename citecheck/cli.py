from __future__ import annotations

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
    from .schema import AuditorOpinion, ControlFramework

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

    def ask_bool(field: str, prompt: str) -> str:
        while True:
            raw = typer.prompt(prompt).strip().lower()
            if raw in {"t", "true", "y", "yes", "1"}:
                return "true"
            if raw in {"f", "false", "n", "no", "0"}:
                return "false"
            console.print("[yellow]enter true or false[/]")

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
        "disclosure_controls_effective": ask_bool(
            "disclosure_controls_effective", "Disclosure controls effective? (true/false)"),
        "icfr_effective": ask_bool("icfr_effective", "ICFR effective? (true/false)"),
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


if __name__ == "__main__":
    app()
