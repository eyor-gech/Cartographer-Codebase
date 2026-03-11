from pathlib import Path
from typing import Optional
from shutil import rmtree
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.agents.surveyor import Surveyor
from src.agents.hydrologist import Hydrologist
from src.graph.knowledge_graph import KnowledgeGraph
from src.intelligence.importance_engine import ImportanceEngine
from src.utils.logging_utils import get_logger
from src.utils.file_utils import write_json


class Orchestrator:
    """Coordinates multi-agent analysis to produce cartography artifacts."""

    def __init__(self, repo_path: Path, cartography_dir: Path, console: Optional[Console] = None):
        self.repo_path = repo_path
        self.cartography_dir = cartography_dir
        self.console = console or Console()
        self.logger = get_logger(__name__)

    def run(self):
        self.logger.info("Starting orchestration pipeline")
        module_graph = KnowledgeGraph(kind="module")
        lineage_graph = KnowledgeGraph(kind="lineage")

        # Determine subfolder name from repo folder
        repo_name = self.repo_path.name
        base_cartography_dir = Path("C:/Users/Eyor.G/Documents/Tenx/Cartographer-Codebase/.cartography")
        self.cartography_dir = base_cartography_dir / repo_name

        # If folder exists, remove it first
        if self.cartography_dir.exists():
            rmtree(self.cartography_dir)
        self.cartography_dir.mkdir(parents=True, exist_ok=True)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            progress.add_task("Repository discovery", total=None)
            surveyor = Surveyor(self.repo_path, module_graph)
            hydrologist = Hydrologist(self.repo_path, lineage_graph)

            progress.update(0, description="Surveyor: structural analysis")
            try:
                surveyor.analyze()
            except Exception as exc:
                self.logger.error("Surveyor encountered an error: %s", exc)

            progress.update(0, description="Hydrologist: lineage analysis")
            try:
                hydrologist.analyze()
            except Exception as exc:
                self.logger.error("Hydrologist encountered an error: %s", exc)

            progress.update(0, description="Importance ranking")
            importance_engine = ImportanceEngine(module_graph, surveyor.git_change_velocity)
            try:
                signals = importance_engine.compute_signals()
            except Exception as exc:
                self.logger.error("Importance computation failed: %s", exc)
                signals = {}

            progress.update(0, description="Serializing artifacts")
            write_json(self.cartography_dir / "module_graph.json", module_graph.export_json())
            write_json(self.cartography_dir / "lineage_graph.json", lineage_graph.export_json())
            write_json(self.cartography_dir / "architecture_signals.json", signals)

        self.logger.info("Analysis complete. Artifacts written to %s", self.cartography_dir)