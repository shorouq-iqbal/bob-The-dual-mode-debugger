"""
healx_cli.py — Rich/Typer CLI for HealX Autonomous Debugger.

Usage:
    python healx_cli.py run [TEST_PATH]
    python healx_cli.py run tests/test_deterministic_bug.py
"""

import os
import sys
import time
import threading
from datetime import datetime

import typer
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

app = typer.Typer(
    help="HealX — Autonomous AI Debugger powered by IBM Granite",
    invoke_without_command=True,
    no_args_is_help=False,
)
console = Console()

BANNER = (
    "HH   HH EEEEE   AAA   LL      XX   XX\n"
    "HH   HH EE     AA AA  LL       XX XX \n"
    "HHHHHHH EEEEE AAAAAAA LL        XXX  \n"
    "HH   HH EE   AA   AA  LL       XX XX \n"
    "HH   HH EEEEE AA   AA LLLLLLL XX   XX"
)

GRANITE_BADGE = "[bold cyan]IBM Granite[/bold cyan] [dim]via watsonx.ai[/dim]"


def print_banner():
    console.print()
    console.print(Panel(
        Align.center(
            Text(BANNER.strip(), style="bold blue") 
        ),
        subtitle=GRANITE_BADGE,
        border_style="blue",
        padding=(0, 4),
    ))
    console.print()


def build_triage_table(results: list) -> Table:
    t = Table(title="Triage Results", box=box.ROUNDED, border_style="blue", show_header=True)
    t.add_column("Run", style="bold", justify="center", width=6)
    t.add_column("Status", justify="center", width=12)
    for i, passed in enumerate(results, 1):
        icon = "[green]● PASS[/green]" if passed else "[red]● FAIL[/red]"
        t.add_row(str(i), icon)
    return t


def build_subagent_table(statuses: dict) -> Table:
    t = Table(title="Parallel Subagent Race (IBM Granite)", box=box.SIMPLE_HEAVY, border_style="cyan")
    t.add_column("Subagent", style="bold", width=14)
    t.add_column("Hypothesis", width=26)
    t.add_column("Status", justify="center", width=14)

    icons = {
        "PENDING": "[dim]⏳ PENDING[/dim]",
        "ANALYZING": "[yellow]🔬 ANALYZING[/yellow]",
        "PASSED": "[green]✅ PASSED[/green]",
        "FAILED": "[red]❌ FAILED[/red]",
    }
    hypotheses = {
        "timing": "Unmocked sleep / async",
        "state": "Shared global state leak",
        "randomness": "Unseeded random generator",
    }
    for kind in ["timing", "state", "randomness"]:
        status = statuses.get(kind, "PENDING")
        t.add_row(f"🧠 {kind.capitalize()}", hypotheses[kind], icons.get(status, status))
    return t


@app.command()
def run(
    test_path: str = typer.Argument(
        os.path.join("tests", "test_deterministic_bug.py"),
        help="Relative path to the pytest test file inside sample_repo/",
    ),
    no_report: bool = typer.Option(False, "--no-report", help="Skip writing Markdown report"),
):
    """Run HealX on the given test path and autonomously fix the bug."""
    # Import orchestrator lazily so missing env vars don't crash --help
    import importlib, sys

    # Ensure watsonx_client is loaded with deferred credential validation
    import orchestrator
    import reporter

    print_banner()
    console.print(Rule("[bold blue]Starting HealX Run[/bold blue]"))
    console.print(f"  [dim]Target:[/dim] [cyan]{test_path}[/cyan]")
    console.print(f"  [dim]Time:  [/dim] [cyan]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/cyan]")
    console.print()

    # ---- TRIAGE PHASE ----
    console.print(Rule("[bold yellow]Phase 1 — Triage[/bold yellow]"))
    triage_results = []
    verdict = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Running triage ({orchestrator.TRIAGE_RUNS}x)...", total=orchestrator.TRIAGE_RUNS)
        for _ in range(orchestrator.TRIAGE_RUNS):
            passed = orchestrator.run_test(orchestrator.REPO_PATH, test_path)["passed"]
            triage_results.append(passed)
            progress.advance(task)

    # Classify
    if all(r == triage_results[0] for r in triage_results):
        verdict = "MODE_A" if not triage_results[0] else "NO_BUG"
    else:
        verdict = "MODE_B"

    console.print(build_triage_table(triage_results))
    console.print()

    verdict_labels = {
        "MODE_A": ("[bold red]DETERMINISTIC BUG[/bold red]", "Routing to Mode A — Debug Loop"),
        "MODE_B": ("[bold yellow]FLAKY TEST[/bold yellow]", "Routing to Mode B — FlakyGuard"),
        "NO_BUG": ("[bold green]NO BUG DETECTED[/bold green]", "All tests passing. Nothing to fix."),
    }
    label, desc = verdict_labels.get(verdict, (verdict, ""))
    console.print(Panel(f"  Classification: {label}\n  {desc}", border_style="yellow"))
    console.print()

    if verdict == "NO_BUG":
        console.print("[bold green]✓ No issues found. HealX run complete.[/bold green]")
        return

    # ---- MODE A ----
    result = {}
    subagent_statuses = {"timing": "PENDING", "state": "PENDING", "randomness": "PENDING"}

    if verdict == "MODE_A":
        console.print(Rule("[bold red]Phase 2 — Mode A: Debug Loop[/bold red]"))

        diagnosis_text = ""
        diff_text = ""

        # Event sink for live updates
        live_table_holder = {}
        lock = threading.Lock()

        def on_event(kind, data):
            nonlocal diagnosis_text, diff_text
            if kind == "diagnosis":
                diagnosis_text = data.get("text", "")
            elif kind == "attempt_result":
                diff_text = data.get("diff", "")

        with console.status("[bold cyan]🤖 IBM Granite diagnosing failure...[/bold cyan]", spinner="dots"):
            result = orchestrator.run_debug_loop(test_path, event_cb=on_event)

        if diagnosis_text:
            console.print(Panel(
                Markdown(f"**IBM Granite Root-Cause Analysis**\n\n{diagnosis_text}"),
                border_style="cyan",
                title="[bold cyan]Granite Diagnosis[/bold cyan]",
            ))
            console.print()

        if diff_text:
            console.print(Rule("[bold green]Code Diff Applied[/bold green]"))
            console.print(Syntax(diff_text, "diff", theme="monokai", line_numbers=False))
            console.print()

    # ---- MODE B ----
    elif verdict == "MODE_B":
        console.print(Rule("[bold yellow]Phase 2 — Mode B: FlakyGuard[/bold yellow]"))
        console.print("[dim]Dispatching 3 IBM Granite subagents in parallel...[/dim]\n")

        with Live(build_subagent_table(subagent_statuses), console=console, refresh_per_second=4) as live:
            def on_event(kind, data):
                if kind == "subagent_status":
                    k = data["kind"]
                    subagent_statuses[k] = data["status"]
                    live.update(build_subagent_table(subagent_statuses))

            result = orchestrator.run_flakyguard(test_path, event_cb=on_event)

        console.print()
        if result.get("diff"):
            console.print(Rule("[bold green]Winning Fix Diff[/bold green]"))
            console.print(Syntax(result["diff"], "diff", theme="monokai"))
            console.print()

    # ---- STRESS VERIFICATION ----
    stress_passes = result.get("stress_passes", 0)
    stress_total = result.get("stress_total", 0)

    if stress_total:
        console.print(Rule("[bold blue]Final Stress Verification[/bold blue]"))
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[green]{task.completed}[/] / {task.total} passed"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Stress verifying fix...", total=stress_total)
            progress.update(task, completed=stress_passes)

        pct = int(100 * stress_passes / stress_total) if stress_total else 0
        console.print(f"\n  [bold]Pass rate:[/bold] [{'green' if pct == 100 else 'yellow'}]{stress_passes}/{stress_total} ({pct}%)[/]")
        console.print()

    # ---- RESULT SUMMARY ----
    console.print(Rule())
    if result.get("success"):
        console.print(Panel(
            "[bold green]✅  HealX Successfully Fixed the Bug![/bold green]\n\n"
            f"Fix applied to: [cyan]{result.get('target_file', test_path)}[/cyan]\n"
            f"Mode used: [bold]{result.get('mode', verdict)}[/bold]",
            border_style="green",
            title="[bold green]RUN COMPLETE[/bold green]",
        ))
    else:
        console.print(Panel(
            "[bold red]❌  HealX could not fully verify a fix.[/bold red]\n"
            f"Diagnosis: {result.get('diagnosis', 'N/A')}",
            border_style="red",
            title="[bold red]RUN FAILED[/bold red]",
        ))

    # ---- REPORT ----
    if not no_report:
        report_path = reporter.generate_report(
            test_name=test_path,
            triage_results=triage_results,
            verdict=verdict,
            result=result,
        )
        console.print(f"\n  [dim]📄 Audit report saved to:[/dim] [cyan]{report_path}[/cyan]")
    console.print()


if __name__ == "__main__":
    app()
