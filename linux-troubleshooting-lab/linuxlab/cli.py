#!/usr/bin/env python3
import sys
import os
import time
import argparse
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from linuxlab.config import CATEGORIES, DIFFICULTIES, LEVELS, LEVEL_DESCRIPTIONS
from linuxlab.lab.controller import LabController
from linuxlab.lab.health import check_lab_health
from linuxlab.lab.reset import reset_lab
from linuxlab.scenarios.registry import registry
from linuxlab.state.manager import StateManager
from linuxlab.evaluation.evaluator import IncidentEvaluator
from linuxlab.interview.runner import InterviewRunner

console = Console()
controller = LabController()

def cmd_start(args):
    """Start or verify the disposable lab container."""
    console.print("[bold cyan][linuxlab][/bold cyan] Starting Linux Troubleshooting Lab sandbox...")
    if controller.is_running():
        console.print("[green]✔ Lab container 'linuxlab-sandbox' is already running and ready.[/green]")
    else:
        success = controller.start()
        if success:
            console.print("[bold green]✔ Lab container successfully started.[/bold green]")
        else:
            console.print("[bold red]✘ Failed to start lab container. Ensure Docker is running.[/bold red]")
            sys.exit(1)

    health = check_lab_health(controller)
    console.print(f"Container: [cyan]{health['container']}[/cyan] | Web App: [green]{health['web_app']}[/green] | Payment API: [green]{health['payment_api']}[/green]")
    console.print("\nRun [bold yellow]linuxlab random[/bold yellow] to generate an incident or [bold yellow]linuxlab shell[/bold yellow] to enter.")

def cmd_status(args):
    """Display current lab health and active incident session."""
    session = StateManager.get_session()
    health = check_lab_health(controller)

    table = Table(title="Linux Troubleshooting Lab Status", show_header=True, header_style="bold magenta")
    table.add_column("Property", style="dim", width=22)
    table.add_column("Value", style="bold")

    table.add_row("Sandbox Container", f"[green]{health['status']}[/green]" if health['status'] == "running" else "[red]stopped[/red]")
    table.add_row("Container Name", health['container'])
    table.add_row("web-app.service", f"[green]{health['web_app']}[/green]" if health['web_app'] == "active" else f"[yellow]{health['web_app']}[/yellow]")
    table.add_row("payment-api.service", f"[green]{health['payment_api']}[/green]" if health['payment_api'] == "active" else f"[yellow]{health['payment_api']}[/yellow]")

    if session:
        sc = registry.get(session["scenario_id"])
        elapsed = int(time.time() - session.get("start_time", time.time()))
        mins, secs = divmod(elapsed, 60)
        sc_lvl = getattr(sc, "level", getattr(sc, "difficulty", "EASY")).upper()
        table.add_row("Active Incident", f"{sc.title if sc else session['scenario_id']} ({session['scenario_id']})")
        table.add_row("Learning Level", f"[yellow]{sc_lvl}[/yellow]")
        table.add_row("Elapsed Time", f"{mins}m {secs}s")
        table.add_row("Hints Used", f"{len(session.get('hints_used', []))} of 3")
    else:
        table.add_row("Active Incident", "[dim]None (Run 'linuxlab random')[/dim]")

    console.print(table)

def cmd_random(args):
    """Select a scenario, inject fault into container, and display incident briefing."""
    controller.ensure_running()
    controller.reset()

    recent_ids = StateManager.get_recent_scenario_ids(count=3)
    target_level = getattr(args, "level", None) or getattr(args, "difficulty", None)

    scenario = registry.get_random(
        recent_ids=recent_ids,
        category=args.category,
        difficulty=args.difficulty,
        level=target_level
    )

    if not scenario:
        console.print("[red]No scenarios found matching your criteria.[/red]")
        return

    console.print(f"[dim]Injecting incident fault for {scenario.id}...[/dim]")
    injected = scenario.setup(controller)
    if not injected:
        console.print(f"[bold red]✘ Failed to inject fault for {scenario.id}. Please run 'linuxlab reset'.[/bold red]")
        return

    # Start new session
    StateManager.start_session(scenario.id)

    # Format incident briefing
    briefing = scenario.get_briefing()
    symptoms_text = "\n".join(f"  • {s}" for s in briefing["symptoms"])
    sc_level = briefing.get("level", briefing.get("difficulty", "EASY"))

    guidance_part = ""
    if briefing.get("investigation_guidance"):
        guidance_part = f"\n\n[bold yellow underline]INVESTIGATION GUIDANCE:[/bold yellow underline]\n{briefing['investigation_guidance']}"

    tools_part = ""
    if briefing.get("expected_tools"):
        tools_part = f"\n[dim]Recommended Tools:[/dim] [cyan]{', '.join(briefing['expected_tools'])}[/cyan]"

    body = (
        f"[bold cyan]Category:[/bold cyan] {briefing['category']}   |   [bold cyan]Level:[/bold cyan] [bold yellow]{sc_level}[/bold yellow]{tools_part}\n\n"
        f"[bold white underline]INCIDENT CONTEXT:[/bold white underline]\n{briefing['context']}\n\n"
        f"[bold white underline]REPORTED SYMPTOMS:[/bold white underline]\n{symptoms_text}\n\n"
        f"[bold white underline]YOUR OBJECTIVE:[/bold white underline]\n{briefing['objective']}{guidance_part}\n\n"
        f"[dim]Investigation Tip: Connect to the server using:[/dim] [bold yellow]linuxlab shell[/bold yellow]"
    )

    console.print()
    console.print(Panel(
        body,
        title=f"[bold red]🚨 PRODUCTION INCIDENT: {briefing['title']} (#{briefing['id']})[/bold red]",
        border_style="red",
        expand=False
    ))
    console.print("\n[bold green]# START INVESTIGATION. Use normal Linux commands to diagnose and fix.[/bold green]")
    console.print("When fixed, run: [bold yellow]linuxlab evaluate[/bold yellow]")

def cmd_load(args):
    """Load and inject a specific scenario by its ID."""
    controller.ensure_running()
    controller.reset()

    scenario = registry.get(args.scenario_id)
    if not scenario:
        console.print(f"[bold red]Scenario '{args.scenario_id}' not found. Run 'linuxlab list' to see available IDs.[/bold red]")
        return

    console.print(f"[dim]Injecting incident fault for {scenario.id}...[/dim]")
    injected = scenario.setup(controller)
    if not injected:
        console.print(f"[bold red]✘ Failed to inject fault for {scenario.id}. Please run 'linuxlab reset'.[/bold red]")
        return

    StateManager.start_session(scenario.id)
    briefing = scenario.get_briefing()
    symptoms_text = "\n".join(f"  • {s}" for s in briefing["symptoms"])
    body = (
        f"[bold cyan]Category:[/bold cyan] {briefing['category']}   |   [bold cyan]Difficulty:[/bold cyan] {briefing['difficulty']}\n\n"
        f"[bold white underline]INCIDENT CONTEXT:[/bold white underline]\n{briefing['context']}\n\n"
        f"[bold white underline]REPORTED SYMPTOMS:[/bold white underline]\n{symptoms_text}\n\n"
        f"[bold white underline]YOUR OBJECTIVE:[/bold white underline]\n{briefing['objective']}\n\n"
        f"[dim]Investigation Tip: Connect to the server using:[/dim] [bold yellow]linuxlab shell[/bold yellow]"
    )

    console.print()
    console.print(Panel(
        body,
        title=f"[bold red]🚨 PRODUCTION INCIDENT: {briefing['title']} (#{briefing['id']})[/bold red]",
        border_style="red",
        expand=False
    ))
    console.print("\n[bold green]# START INVESTIGATION. Use normal Linux commands to diagnose and fix.[/bold green]")
    console.print("When fixed, run: [bold yellow]linuxlab evaluate[/bold yellow]")

def cmd_hint(args):
    """Provide progressive hints (Level 1, 2, 3), reducing score."""
    session = StateManager.get_session()
    if not session:
        console.print("[yellow]No active incident session. Run 'linuxlab random' to start an incident.[/yellow]")
        return

    scenario = registry.get(session["scenario_id"])
    if not scenario:
        console.print("[red]Unknown active scenario.[/red]")
        return

    hints_used = session.get("hints_used", [])
    next_level = len(hints_used) + 1

    if next_level > len(scenario.hints):
        console.print("[yellow]All available hints have already been revealed.[/yellow]")
        for i, h in enumerate(scenario.hints, 1):
            console.print(f"[bold cyan]Hint #{i}:[/bold cyan] {h}")
        return

    hint_text = scenario.hints[next_level - 1]
    StateManager.record_hint(next_level)

    hint_descriptions = {
        1: "Level 1 (High-Level Direction - 5 pts penalty)",
        2: "Level 2 (Narrowed Investigation - 10 pts penalty)",
        3: "Level 3 (Command-Level Guidance - 15 pts penalty)"
    }

    desc = hint_descriptions.get(next_level, f"Hint #{next_level}")
    console.print()
    console.print(Panel(
        hint_text,
        title=f"[bold yellow]💡 {desc}[/bold yellow]",
        border_style="yellow"
    ))

def cmd_evaluate(args):
    """Evaluate container state and produce structured report."""
    session = StateManager.get_session()
    if not session:
        console.print("[yellow]No active incident session. Run 'linuxlab random' to start an incident first.[/yellow]")
        return

    explanation = args.explanation
    if explanation is None and sys.stdin.isatty():
        console.print("\n[bold cyan]Before evaluation:[/bold cyan] What was the root cause and how did you resolve it?")
        explanation = Prompt.ask("[green]Your explanation (or press Enter to skip)[/green]", default="")

    explanation = explanation or ""
    evaluator = IncidentEvaluator(controller)
    evaluator.evaluate_current(user_explanation=explanation)

def cmd_reset(args):
    """Clean lab environment and reset baseline services."""
    console.print("[bold cyan][linuxlab][/bold cyan] Resetting lab sandbox environment...")
    success = reset_lab(controller)
    if success:
        console.print("[bold green]✔ Lab reset complete. Active session cleared and services healthy.[/bold green]")
    else:
        console.print("[bold red]✘ Reset encountered an error. Check container status.[/bold red]")

def cmd_shell(args):
    """Open interactive bash terminal directly inside the container."""
    console.print("[bold cyan]Connecting to prod-app-server-01 as 'devops' user...[/bold cyan]")
    console.print("[dim]Type 'exit' to return to host.[/dim]\n")
    controller.interactive_shell(user="devops")

def cmd_list(args):
    """List all available troubleshooting scenarios and categories."""
    table = Table(title="Available Linux Troubleshooting Scenarios", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="bold yellow", width=12)
    table.add_column("Category", style="cyan", width=14)
    table.add_column("Level", style="bold green", width=12)
    table.add_column("Difficulty", style="magenta", width=12)
    table.add_column("Title", style="white")

    scenarios = registry.list_all()
    for sc in scenarios:
        sc_lvl = getattr(sc, "level", getattr(sc, "difficulty", "EASY")).upper()
        table.add_row(sc.id, sc.category.upper(), sc_lvl, sc.difficulty, sc.title)

    console.print(table)
    console.print(f"\nTotal Scenarios: [bold]{len(scenarios)}[/bold] across categories: {', '.join(c.upper() for c in CATEGORIES)}")
    console.print(f"Levels: [bold]{', '.join(LEVELS)}[/bold]")

def cmd_progress(args):
    """Display user progress, solved rate, and category statistics."""
    stats = StateManager.calculate_progress()

    console.print()
    console.print(Panel(
        f"[bold white]Total Incidents Attempted:[/bold white] [bold cyan]{stats['total_incidents']}[/bold cyan]\n"
        f"[bold white]Incidents Solved:[/bold white] [bold green]{stats['solved_count']}[/bold green]\n"
        f"[bold white]Average Score:[/bold white] [bold yellow]{stats['avg_score']}/100[/bold yellow]\n"
        f"[bold white]Hints Used:[/bold white] {stats['total_hints']}\n"
        f"[bold white]Recommended Next Level:[/bold white] [bold green]{stats.get('recommended_next_level', 'EASY')}[/bold green]",
        title="[bold magenta]LINUX TROUBLESHOOTING PROGRESS[/bold magenta]",
        border_style="magenta",
        expand=False
    ))

    # Overall Level Progress
    if "levels" in stats:
        lvl_table = Table(title="Overall Level Progress", show_header=True, header_style="bold yellow")
        lvl_table.add_column("Level", style="bold", width=12)
        lvl_table.add_column("Mastery", style="bold green", width=14)
        lvl_table.add_column("Solved / Target", justify="center", width=16)
        lvl_table.add_column("Success Rate", justify="right", width=14)
        lvl_table.add_column("Average Score", justify="right", width=14)

        for lvl, data in stats["levels"].items():
            rate_style = "green" if data["rate"] >= 80 else ("yellow" if data["rate"] >= 50 else "red")
            lvl_table.add_row(
                lvl,
                f"[green]{data['bar']}[/green]",
                f"{data['solved']} / 5 ({data['progress_pct']}%)",
                f"[{rate_style}]{data['rate']}%[/{rate_style}]",
                f"{data['avg_score']}/100"
            )
        console.print(lvl_table)
        console.print()

    table = Table(title="Category Mastery Breakdown", show_header=True, header_style="bold cyan")
    table.add_column("Category", style="bold", width=16)
    table.add_column("Attempted", justify="center", width=12)
    table.add_column("Solved", justify="center", width=10)
    table.add_column("Success Rate", justify="right", width=14)
    table.add_column("Average Score", justify="right", width=14)

    for cat, data in stats["categories"].items():
        rate_style = "green" if data["rate"] >= 80 else ("yellow" if data["rate"] >= 50 else "red")
        table.add_row(
            cat.upper(),
            str(data["attempted"]),
            str(data["solved"]),
            f"[{rate_style}]{data['rate']}%[/{rate_style}]",
            f"{data['avg_score']}/100"
        )

    console.print(table)

    if stats["weakest"]:
        console.print(f"\n[bold yellow]Focus Areas for Practice:[/bold yellow] {', '.join(w.upper() for w in stats['weakest'])}")
    console.print()

def cmd_interview(args):
    """Launch interactive SRE reasoning interview mode."""
    runner = InterviewRunner()
    runner.run()

def cmd_web(args):
    """Launch the browser-based Linux Troubleshooting Lab web interface."""
    import uvicorn
    port = args.port
    host = args.host
    console.print(f"[bold cyan]Starting Linux Troubleshooting Lab Web UI on[/bold cyan] [bold green]http://localhost:{port}[/bold green]")
    console.print("[dim]Press Ctrl+C to stop the web server.[/dim]\n")
    uvicorn.run("linuxlab.web.app:app", host=host, port=port, log_level="info")

def main():
    parser = argparse.ArgumentParser(
        prog="linuxlab",
        description="Linux Troubleshooting Lab — 2 YOE DevOps Practice Environment"
    )
    subparsers = parser.add_subparsers(dest="command", help="Lab commands")

    # start
    subparsers.add_parser("start", help="Start or verify lab container environment")

    # status
    subparsers.add_parser("status", help="Check lab status and active incident")

    # random
    rand_parser = subparsers.add_parser("random", help="Generate and inject a random incident")
    rand_parser.add_argument("-c", "--category", choices=CATEGORIES, help="Filter by category")
    rand_parser.add_argument("-l", "--level", choices=LEVELS, help="Filter by learning level (EASY, MODERATE, FLUENT, ADVANCED, EXPERT)")
    rand_parser.add_argument("-d", "--difficulty", choices=DIFFICULTIES, help="Filter by difficulty")

    # load
    load_parser = subparsers.add_parser("load", help="Load and inject a specific scenario by ID")
    load_parser.add_argument("scenario_id", type=str, help="Scenario ID (e.g. cpu_001, net_001)")

    # hint
    subparsers.add_parser("hint", help="Get progressive hint (reduces score)")

    # evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Verify actual lab state and score resolution")
    eval_parser.add_argument("-e", "--explanation", type=str, default=None, help="Your explanation of root cause and fix")

    # reset
    subparsers.add_parser("reset", help="Reset lab container to clean baseline")

    # shell
    subparsers.add_parser("shell", help="Enter sandbox container bash shell")

    # list
    subparsers.add_parser("list", help="List all available troubleshooting scenarios")

    # progress
    subparsers.add_parser("progress", help="Display performance statistics and progress")

    # interview
    subparsers.add_parser("interview", help="Run scenario-based SRE interview practice")

    # web
    web_parser = subparsers.add_parser("web", help="Launch browser-based web interface")
    web_parser.add_argument("-p", "--port", type=int, default=8088, help="Web port (default: 8088)")
    web_parser.add_argument("--host", type=str, default="0.0.0.0", help="Web host (default: 0.0.0.0)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handlers = {
        "start": cmd_start,
        "status": cmd_status,
        "random": cmd_random,
        "load": cmd_load,
        "hint": cmd_hint,
        "evaluate": cmd_evaluate,
        "reset": cmd_reset,
        "shell": cmd_shell,
        "list": cmd_list,
        "progress": cmd_progress,
        "interview": cmd_interview,
        "web": cmd_web,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)

if __name__ == "__main__":
    main()
