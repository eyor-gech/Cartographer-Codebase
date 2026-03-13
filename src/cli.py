from pathlib import Path
import tempfile
import typer
from rich.console import Console
from rich.panel import Panel
from git import Repo
import time
import json

from src.orchestrator import Orchestrator
from src.utils.logging_utils import get_logger
from src.agents.navigator import Navigator

console = Console()
app = typer.Typer(help="Brownfield Cartographer CLI")
logger = get_logger(__name__)


@app.command()
def analyze(
    repo_input: str = typer.Argument(..., help="Path to a local repo or a Git URL"),
    incremental: bool = typer.Option(False, "--incremental", help="Re-analyze only files changed since last run"),
):
    """
    Run full cartography analysis on a repository.
    
    You can provide:
    1. A local path to a cloned repository
    2. A Git URL (https://...) to clone temporarily
    """
    start_total = time.perf_counter()

    # --- Case 1: Git URL ---
    if repo_input.startswith("http") and "github.com" in repo_input:
        repo_name = repo_input.rstrip("/").split("/")[-1].removesuffix(".git")
        out_dir = Path.cwd() / ".cartography" / repo_name
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            console.print(f"[cyan]Cloning repository from {repo_input}[/cyan]")
            Repo.clone_from(repo_input, tmpdir)
            repo = Path(tmpdir)
            console.print(Panel.fit(f"Running Brownfield Cartographer on [bold]{repo_name}[/bold] (cloned)"))
            Orchestrator(repo, out_dir, console=console).run(incremental=incremental)
            console.print(f"[green]Artifacts written to {out_dir}[/green]")
            _print_trace_timings(out_dir / "cartography_trace.jsonl")
    else:
        repo = Path(repo_input).resolve()
        if not repo.exists() or not repo.is_dir():
            typer.echo(f"[red]Invalid repository path: {repo}[/red]")
            raise typer.Exit(code=1)
        cartography_dir = repo / ".cartography"
        cartography_dir.mkdir(parents=True, exist_ok=True)
        console.print(Panel.fit(f"Running Brownfield Cartographer on [bold]{repo}[/bold]"))
        Orchestrator(repo, cartography_dir, console=console).run(incremental=incremental)
        _print_trace_timings(cartography_dir / "cartography_trace.jsonl")

    console.print(f"[bold cyan]Total elapsed time: {time.perf_counter() - start_total:.2f}s[/bold cyan]")


@app.command()
def query(target: str = typer.Argument(..., help="Repo path or .cartography directory")):
    """Interactive query over existing cartography artifacts."""
    base = Path(target).resolve()
    cartography_dir = base if (base / "module_graph.json").exists() else (base / ".cartography")
    if not (cartography_dir / "module_graph.json").exists():
        typer.echo(f"[red]No cartography artifacts found in: {cartography_dir}[/red]")
        raise typer.Exit(code=1)

    nav = Navigator.from_cartography_dir(cartography_dir, console=console)
    console.print(Panel.fit(f"Navigator loaded artifacts from [bold]{cartography_dir}[/bold]"))
    console.print("Commands: blast <dataset>, sources, sinks, explain <module>, exit")

    while True:
        try:
            raw = console.input("cartographer> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            continue
        if raw in ("exit", "quit"):
            break
        if raw == "sources":
            console.print("\n".join(nav.find_sources()) or "(none)")
            continue
        if raw == "sinks":
            console.print("\n".join(nav.find_sinks()) or "(none)")
            continue
        if raw.startswith("blast "):
            ds = raw.split(" ", 1)[1].strip()
            console.print("\n".join(nav.blast_radius(ds)) or "(none)")
            continue
        if raw.startswith("explain "):
            mod = raw.split(" ", 1)[1].strip()
            data = nav.explain_module(mod)
            console.print(json.dumps(data, indent=2) if data else "(not found)")
            continue
        console.print("Unknown command. Try: blast <dataset>, sources, sinks, explain <module>, exit")


def _print_trace_timings(trace_path: Path) -> None:
    if not trace_path.exists():
        return
    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
        entries = [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return

    def ts(e):
        return e.get("timestamp", "")

    by_action = {}
    for e in entries:
        by_action.setdefault((e.get("agent_name"), e.get("action")), []).append(e)

    # Best-effort: show that agents emitted start/end markers.
    for agent in ("Surveyor", "Hydrologist", "Archivist", "Orchestrator"):
        started = any(a == agent and act.endswith("start") for (a, act) in by_action.keys())
        ended = any(a == agent and act.endswith("end") for (a, act) in by_action.keys())
        if started or ended:
            console.print(f"[dim]{agent}: trace start={started} end={ended} ({trace_path})[/dim]")


if __name__ == "__main__":
    app()
