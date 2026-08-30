"""
healx_cli.py — Rich/Typer CLI for HealX Autonomous Debugger.

Usage:
    python healx_cli.py [TEST_PATH]
    python healx_cli.py --repo /path/to/project tests/test_foo.py
    heal-x tests/test_deterministic_bug.py          (after pip install -e .)
"""

import os
import threading
from datetime import datetime

import typer
from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ---------------------------------------------------------------------------
# IBM-branded color theme
# ---------------------------------------------------------------------------
HEALX_THEME = Theme({
    "pass":      "bold #3fb950",
    "fail":      "bold #f85149",
    "pending":   "dim #8b949e",
    "analyzing": "bold #e3b341",
    "granite":   "bold #58a6ff",
    "info":      "#58a6ff",
    "muted":     "dim #8b949e",
    "banner":    "bold #1f6feb",
    "success":   "bold #3fb950",
    "error":     "bold #f85149",
})

app = typer.Typer(
    help="HealX — Autonomous AI Debugger powered by IBM Granite",
    invoke_without_command=True,
    no_args_is_help=False,
)
console = Console(theme=HEALX_THEME)

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
_BANNER_LINES = [
    (" ██╗  ██╗███████╗ █████╗ ██╗     ██╗  ██╗", "#1f6feb"),
    (" ██║  ██║██╔════╝██╔══██╗██║     ╚██╗██╔╝", "#2979d4"),
    (" ███████║█████╗  ███████║██║      ╚███╔╝ ", "#388bfd"),
    (" ██╔══██║██╔══╝  ██╔══██║██║      ██╔██╗ ", "#4d9cf7"),
    (" ██║  ██║███████╗██║  ██║███████╗██╔╝ ██╗", "#58a6ff"),
    (" ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝", "#79c0ff"),
]


def print_banner():
    banner_text = Text()
    for line, color in _BANNER_LINES:
        banner_text.append(line + "\n", style=f"bold {color}")

    subtitle = Text()
    subtitle.append("Powered by ", style="dim")
    subtitle.append("IBM Granite", style="granite")
    subtitle.append(" · ", style="dim")
    subtitle.append("watsonx.ai", style="info")

    console.print()
    console.print(Panel(
        Align.center(banner_text),
        subtitle=Align.center(subtitle),
        border_style="banner",
        padding=(0, 6),
    ))
    console.print()


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

def build_triage_table(results: list) -> Table:
    t = Table(title="[granite]Triage Results[/granite]", box=box.ROUNDED,
              border_style="info", show_header=True, header_style="muted")
    t.add_column("Run", style="bold", justify="center", width=6)
    t.add_column("Status", justify="center", width=14)
    for i, passed in enumerate(results, 1):
        status = "[pass]● PASS[/pass]" if passed else "[fail]● FAIL[/fail]"
        t.add_row(str(i), status)
    return t


def build_subagent_table(statuses: dict) -> Table:
    t = Table(
        title="[granite]Parallel Subagent Race · IBM Granite[/granite]",
        box=box.SIMPLE_HEAVY, border_style="granite",
        header_style="muted",
    )
    t.add_column("Subagent",   style="bold",  width=16)
    t.add_column("Hypothesis", style="muted", width=28)
    t.add_column("Status",     justify="center", width=16)

    icons = {
        "PENDING":   "[pending]○ PENDING[/pending]",
        "ANALYZING": "[analyzing]◎ ANALYZING[/analyzing]",
        "PASSED":    "[pass]✓ PASSED[/pass]",
        "FAILED":    "[fail]✗ FAILED[/fail]",
    }
    hypotheses = {
        "timing":     "Unmocked sleep / async",
        "state":      "Shared global state leak",
        "randomness": "Unseeded random generator",
    }
    for kind in ["timing", "state", "randomness"]:
        status = statuses.get(kind, "PENDING")
        t.add_row(
            f"[granite]▸[/granite] {kind.capitalize()}",
            hypotheses[kind],
            icons.get(status, status),
        )
    return t


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

@app.command()
def run(
    test_path: str = typer.Argument(
        os.path.join("tests", "test_deterministic_bug.py"),
        help="Relative path to the pytest test file inside the target repo.",
    ),
    repo: str = typer.Option(
        None,
        "--repo", "-r",
        help="Path to the target repository root. Defaults to current directory.",
    ),
    no_report: bool = typer.Option(False, "--no-report", help="Skip writing Markdown report"),
):
    """Run HealX on the given test path and autonomously fix the bug."""
    import orchestrator
    import reporter

    # Resolve repo path: --repo flag > CWD
    repo_path = os.path.abspath(repo) if repo else os.getcwd()

    print_banner()
    console.print(Rule("[banner]Starting HealX Run[/banner]"))
    console.print(f"  [muted]Repo:  [/muted] [info]{repo_path}[/info]")
    console.print(f"  [muted]Target:[/muted] [info]{test_path}[/info]")
    console.print(f"  [muted]Time:  [/muted] [info]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/info]")
    console.print()

    # ---- TRIAGE PHASE ----
    console.print(Rule("[analyzing]Phase 1 — Triage[/analyzing]"))
    triage_results = []

    with Progress(
        SpinnerColumn(style="granite"),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30, style="info", complete_style="pass"),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Running triage ({orchestrator.TRIAGE_RUNS}x)...",
            total=orchestrator.TRIAGE_RUNS,
        )
        for _ in range(orchestrator.TRIAGE_RUNS):
            passed = orchestrator.run_test(repo_path, test_path)["passed"]
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
        "MODE_A": ("[fail]DETERMINISTIC BUG[/fail]",   "Routing to Mode A — Debug Loop"),
        "MODE_B": ("[analyzing]FLAKY TEST[/analyzing]", "Routing to Mode B — FlakyGuard"),
        "NO_BUG": ("[pass]NO BUG DETECTED[/pass]",      "All tests passing. Nothing to fix."),
    }
    label, desc = verdict_labels.get(verdict, (verdict, ""))
    console.print(Panel(
        f"  Classification: {label}\n  [muted]{desc}[/muted]",
        border_style="analyzing",
        padding=(0, 2),
    ))
    console.print()

    if verdict == "NO_BUG":
        console.print("[pass]✓ No issues found. HealX run complete.[/pass]")
        return

    result = {}
    subagent_statuses = {"timing": "PENDING", "state": "PENDING", "randomness": "PENDING"}

    # ---- MODE A ----
    if verdict == "MODE_A":
        console.print(Rule("[fail]Phase 2 — Mode A: Debug Loop[/fail]"))

        diagnosis_text = ""
        diff_text = ""

        def on_event(kind, data):
            nonlocal diagnosis_text, diff_text
            if kind == "diagnosis":
                diagnosis_text = data.get("text", "")
            elif kind == "attempt_result":
                diff_text = data.get("diff", "")

        with console.status(
            "[granite]IBM Granite diagnosing failure...[/granite]", spinner="dots"
        ):
            result = orchestrator.run_debug_loop(test_path, repo_path=repo_path, event_cb=on_event)

        if diagnosis_text:
            console.print(Panel(
                Markdown(f"**IBM Granite Root-Cause Analysis**\n\n{diagnosis_text}"),
                border_style="granite",
                title="[granite]Granite Diagnosis[/granite]",
            ))
            console.print()

        if diff_text:
            console.print(Rule("[pass]Code Diff Applied[/pass]"))
            console.print(Syntax(diff_text, "diff", theme="monokai", line_numbers=False))
            console.print()

    # ---- MODE B ----
    elif verdict == "MODE_B":
        console.print(Rule("[analyzing]Phase 2 — Mode B: FlakyGuard[/analyzing]"))
        console.print("[muted]Dispatching 3 IBM Granite subagents in parallel...[/muted]\n")

        with Live(build_subagent_table(subagent_statuses), console=console, refresh_per_second=4) as live:
            def on_event(kind, data):
                if kind == "subagent_status":
                    subagent_statuses[data["kind"]] = data["status"]
                    live.update(build_subagent_table(subagent_statuses))

            result = orchestrator.run_flakyguard(test_path, repo_path=repo_path, event_cb=on_event)

        console.print()
        if result.get("diff"):
            console.print(Rule("[pass]Winning Fix Diff[/pass]"))
            console.print(Syntax(result["diff"], "diff", theme="monokai"))
            console.print()

    # ---- STRESS VERIFICATION ----
    stress_passes = result.get("stress_passes", 0)
    stress_total  = result.get("stress_total",  0)

    if stress_total:
        console.print(Rule("[banner]Final Stress Verification[/banner]"))
        with Progress(
            SpinnerColumn(style="granite"),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=40, style="info", complete_style="pass"),
            TextColumn("[pass]{task.completed}[/pass] / {task.total} passed"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Stress verifying fix...", total=stress_total)
            progress.update(task, completed=stress_passes)

        pct = int(100 * stress_passes / stress_total) if stress_total else 0
        color = "pass" if pct == 100 else "analyzing"
        console.print(
            f"\n  [bold]Pass rate:[/bold] [{color}]{stress_passes}/{stress_total} ({pct}%)[/{color}]"
        )
        console.print()

    # ---- RESULT SUMMARY ----
    console.print(Rule())
    if result.get("success"):
        console.print(Panel(
            "[pass]✓  HealX Successfully Fixed the Bug![/pass]\n\n"
            f"  [muted]Fix applied to:[/muted] [info]{result.get('target_file', test_path)}[/info]\n"
            f"  [muted]Mode used:[/muted]      [bold]{result.get('mode', verdict)}[/bold]",
            border_style="pass",
            title="[pass]RUN COMPLETE[/pass]",
        ))
    else:
        console.print(Panel(
            "[fail]✗  HealX could not fully verify a fix.[/fail]\n\n"
            f"  [muted]Diagnosis:[/muted] {result.get('diagnosis', 'N/A')}",
            border_style="fail",
            title="[fail]RUN FAILED[/fail]",
        ))

    # ---- REPORT ----
    if not no_report:
        report_path = reporter.generate_report(
            test_name=test_path,
            triage_results=triage_results,
            verdict=verdict,
            result=result,
        )
        console.print(
            f"\n  [muted]Audit report:[/muted] [info]{report_path}[/info]"
        )
    console.print()


if __name__ == "__main__":
    app()
