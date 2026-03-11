from pathlib import Path
import tempfile
import typer
from rich.console import Console
from rich.panel import Panel
from git import Repo
import time
from shutil import rmtree

from src.orchestrator import Orchestrator
from src.utils.logging_utils import get_logger

console = Console()
app = typer.Typer(help="Brownfield Cartographer CLI")
logger = get_logger(__name__)


@app.command()
def analyze(repo_input: str = typer.Argument(..., help="Path to a local repo or a Git URL")):
    """
    Run full cartography analysis on a repository.
    
    You can provide:
    1. A local path to a cloned repository
    2. A Git URL (https://...) to clone temporarily
    """
    start_total = time.perf_counter()
    repo: Path

    # --- Case 1: Git URL ---
    if repo_input.startswith("http") and "github.com" in repo_input:
        start_clone = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmpdir:
            console.print(f"[cyan]Cloning repository from {repo_input}[/cyan]")
            Repo.clone_from(repo_input, tmpdir)
            repo = Path(tmpdir)
        console.print(f"[green]Cloning completed in {time.perf_counter() - start_clone:.2f}s[/green]")

    # --- Case 2: Local folder ---
    else:
        repo = Path(repo_input).resolve()
        if not repo.exists() or not repo.is_dir():
            typer.echo(f"[red]Invalid repository path: {repo}[/red]")
            raise typer.Exit(code=1)

    console.print(Panel.fit(f"Running Brownfield Cartographer on [bold]{repo}[/bold]"))

    # --- Prepare cartography subfolder ---
    start_prep = time.perf_counter()
    base_cartography_dir = Path("C:/Users/Eyor.G/Documents/Tenx/Cartographer-Codebase/.cartography")
    cartography_dir = base_cartography_dir / repo.name
    if cartography_dir.exists():
        rmtree(cartography_dir)
    cartography_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]Cartography directory prepared in {time.perf_counter() - start_prep:.2f}s[/green]")

    # --- Run Orchestrator with step-level timing ---
    start_orch = time.perf_counter()
    orchestrator = Orchestrator(repo, cartography_dir, console=console)

    step_times = {}

    # Wrap Orchestrator steps
    import functools

    # Save original run to wrap
    original_run = orchestrator.run

    def timed_run():
        from src.agents.surveyor import Surveyor
        from src.agents.hydrologist import Hydrologist
        from src.intelligence.importance_engine import ImportanceEngine
        from src.utils.file_utils import write_json
        from pathlib import Path
        import time
        from rich.progress import Progress, SpinnerColumn, TextColumn

        orchestrator.logger.info("Starting orchestration pipeline")
        module_graph = orchestrator.module_graph if hasattr(orchestrator, "module_graph") else KnowledgeGraph(kind="module")
        lineage_graph = orchestrator.lineage_graph if hasattr(orchestrator, "lineage_graph") else KnowledgeGraph(kind="lineage")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=orchestrator.console,
        ) as progress:
            progress.add_task("Repository discovery", total=None)

            # Surveyor
            t0 = time.perf_counter()
            surveyor = Surveyor(orchestrator.repo_path, module_graph)
            try:
                surveyor.analyze()
            except Exception as e:
                orchestrator.logger.error("Surveyor encountered an error: %s", e)
            step_times["Surveyor analysis"] = time.perf_counter() - t0
            progress.update(0, description=f"Surveyor done ({step_times['Surveyor analysis']:.2f}s)")

            # Hydrologist
            t0 = time.perf_counter()
            hydrologist = Hydrologist(orchestrator.repo_path, lineage_graph)
            try:
                hydrologist.analyze()
            except Exception as e:
                orchestrator.logger.error("Hydrologist encountered an error: %s", e)
            step_times["Hydrologist analysis"] = time.perf_counter() - t0
            progress.update(0, description=f"Hydrologist done ({step_times['Hydrologist analysis']:.2f}s)")

            # Importance Engine
            t0 = time.perf_counter()
            importance_engine = ImportanceEngine(module_graph, surveyor.git_change_velocity)
            try:
                signals = importance_engine.compute_signals()
            except Exception as e:
                orchestrator.logger.error("Importance computation failed: %s", e)
                signals = {}
            step_times["Importance computation"] = time.perf_counter() - t0
            progress.update(0, description=f"Importance ranking done ({step_times['Importance computation']:.2f}s)")

            # Serialization
            t0 = time.perf_counter()
            orchestrator.cartography_dir = cartography_dir
            orchestrator.cartography_dir.mkdir(parents=True, exist_ok=True)
            write_json(orchestrator.cartography_dir / "module_graph.json", module_graph.export_json())
            write_json(orchestrator.cartography_dir / "lineage_graph.json", lineage_graph.export_json())
            write_json(orchestrator.cartography_dir / "architecture_signals.json", signals)
            step_times["Serialization"] = time.perf_counter() - t0
            progress.update(0, description=f"Artifacts serialized ({step_times['Serialization']:.2f}s)")

    # Run timed orchestrator
    timed_run()
    console.print(f"[green]Orchestration completed in {time.perf_counter() - start_orch:.2f}s[/green]")

    # --- Print step-level timing ---
    console.print("[bold yellow]Step timings:[/bold yellow]")
    for step, t in step_times.items():
        console.print(f"  {step}: {t:.2f}s")

    # --- Total time ---
    total_elapsed = time.perf_counter() - start_total
    console.print(f"[bold cyan]Total elapsed time: {total_elapsed:.2f}s[/bold cyan]")


if __name__ == "__main__":
    app()