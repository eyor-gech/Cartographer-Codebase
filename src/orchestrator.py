from pathlib import Path
from typing import Optional
import os
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.agents.surveyor import Surveyor
from src.agents.hydrologist import Hydrologist
from src.agents.archivist import Archivist
from src.graph.knowledge_graph import KnowledgeGraph
from src.graph.data_lineage_graph import DataLineageGraph
from src.intelligence.importance_engine import ImportanceEngine
from src.utils.logging_utils import get_logger
from src.utils.file_utils import write_json
from datetime import datetime

from src.utils.trace_logger import TraceLogger
from src.utils.state_utils import AnalysisState, current_state_for_repo
from src.utils.git_utils import changed_files_since
from src.analyzers.dead_code_detector import detect_dead_code_candidates
from src.agents.semanticist import Semanticist


class Orchestrator:
    """Coordinates multi-agent analysis to produce cartography artifacts."""

    def __init__(self, repo_path: Path, cartography_dir: Path, console: Optional[Console] = None):
        self.repo_path = repo_path
        self.cartography_dir = cartography_dir
        self.console = console or Console()
        self.logger = get_logger(__name__)

    def run(self, *, incremental: bool = False):
        self.logger.info("Starting orchestration pipeline")
        module_graph: KnowledgeGraph
        lineage_graph: KnowledgeGraph

        self.cartography_dir.mkdir(parents=True, exist_ok=True)
        trace = TraceLogger(self.cartography_dir / "cartography_trace.jsonl")
        state_path = self.cartography_dir / "state.json"
        previous_state = AnalysisState.load(state_path)
        include_paths = None
        if incremental and previous_state and previous_state.last_run_utc:
            try:
                since = datetime.fromisoformat(previous_state.last_run_utc.replace("Z", "+00:00"))
                raw = changed_files_since(self.repo_path, since)
                include_paths = {_normalize_rel_path(p) for p in raw}
                trace.log(
                    "Orchestrator",
                    "incremental_detected",
                    evidence_source=str(state_path),
                    analysis_method="static",
                    extra={"changed_files": len(include_paths)},
                )
            except Exception as exc:
                trace.log(
                    "Orchestrator",
                    "incremental_failed",
                    confidence=0.3,
                    evidence_source=str(state_path),
                    analysis_method="static",
                    extra={"error": str(exc)},
                )
                include_paths = None

        trace.log("Orchestrator", "run_start", evidence_source=str(self.repo_path), analysis_method="static")

        # Incremental mode: load prior artifacts and only re-analyze changed files.
        if incremental and include_paths is not None:
            module_graph = _load_or_new(self.cartography_dir / "module_graph.json", kind="module")
            loaded_lineage = _load_or_new(self.cartography_dir / "lineage_graph.json", kind="lineage")
            lineage_graph = DataLineageGraph()
            lineage_graph.graph = loaded_lineage.graph

            _prune_module_graph(module_graph, include_paths)
            lineage_graph.prune_by_source_files(include_paths)
        else:
            module_graph = KnowledgeGraph(kind="module")
            lineage_graph = DataLineageGraph()

        knowledge_graph = KnowledgeGraph(kind="knowledge")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            progress.add_task("Repository discovery", total=None)
            surveyor = Surveyor(self.repo_path, module_graph, trace=trace)
            hydrologist = Hydrologist(self.repo_path, lineage_graph, trace=trace)

            progress.update(0, description="Surveyor: structural analysis")
            try:
                py_only = {p for p in include_paths} if include_paths is not None else None
                if py_only is not None:
                    py_only = {p for p in py_only if p.endswith(".py")}
                surveyor.analyze(include_paths=py_only)
            except Exception as exc:
                self.logger.error("Surveyor encountered an error: %s", exc)
                trace.log("Surveyor", "analyze_error", confidence=0.2, evidence_source=str(self.repo_path), analysis_method="static", extra={"error": str(exc)})

            progress.update(0, description="Hydrologist: lineage analysis")
            try:
                hydrologist.analyze(include_paths=include_paths)
            except Exception as exc:
                self.logger.error("Hydrologist encountered an error: %s", exc)
                trace.log("Hydrologist", "analyze_error", confidence=0.2, evidence_source=str(self.repo_path), analysis_method="static", extra={"error": str(exc)})

            progress.update(0, description="Merging graphs")
            try:
                knowledge_graph.merge(module_graph)
                knowledge_graph.merge(lineage_graph)
            except Exception as exc:
                self.logger.error("Graph merge failed: %s", exc)
                trace.log("Orchestrator", "merge_error", confidence=0.2, evidence_source=str(self.repo_path), analysis_method="static", extra={"error": str(exc)})

            progress.update(0, description="Importance ranking")
            importance_engine = ImportanceEngine(module_graph, surveyor.git_change_velocity)
            try:
                signals = importance_engine.compute_signals()
            except Exception as exc:
                self.logger.error("Importance computation failed: %s", exc)
                signals = {}
                trace.log("Orchestrator", "importance_error", confidence=0.2, evidence_source=str(self.repo_path), analysis_method="static", extra={"error": str(exc)})

            progress.update(0, description="Dead code (v2)")
            try:
                signals["dead_code_candidates_v2"] = detect_dead_code_candidates(module_graph)
            except Exception as exc:
                trace.log("Orchestrator", "dead_code_v2_error", confidence=0.3, evidence_source=str(self.repo_path), analysis_method="static", extra={"error": str(exc)})
            """
            progress.update(0, description="Semanticist: purpose (offline)")
            try:
                #semanticist = Semanticist(trace=trace)
                semanticist = Semanticist(cartography_dir=self.cartography_dir, trace=trace)
                for item in (signals.get("critical_modules") or [])[:15]:
                    node = item.get("module") or item.get("node")
                    if not node:
                        continue
                    p = self.repo_path / node
                    if not p.exists() or not p.is_file():
                        continue
                    #result = semanticist.infer_module_purpose(p)
                    result = semanticist._analyze_module(p)
                    if node in module_graph.graph.nodes:
                        module_graph.graph.nodes[node]["purpose_statement"] = result.get("purpose_statement")
                        module_graph.graph.nodes[node]["docstring_drift"] = result.get("drift")
            except Exception as exc:
                trace.log("Semanticist", "purpose_error", confidence=0.2, evidence_source=str(self.repo_path), analysis_method="LLM", extra={"error": str(exc)})
            """
            progress.update(0, description="Semanticist: purpose (LLM)")
            try:
                semanticist = Semanticist(cartography_dir=self.cartography_dir, repo_root=self.repo_path, trace=trace)

                if incremental and include_paths is not None:
                    rel_py = [p for p in include_paths if p.endswith(".py")]
                    modules_to_analyze = [self.repo_path / p for p in rel_py if (self.repo_path / p).exists()]
                    if modules_to_analyze:
                        semanticist.analyze_modules(modules_to_analyze)
                else:
                    modules_to_analyze = [
                        self.repo_path / n
                        for n, a in module_graph.graph.nodes(data=True)
                        if a.get("type") == "module" and (self.repo_path / n).exists()
                    ]
                    semanticist.analyze_modules(modules_to_analyze)  # THIS triggers the LLM
                semanticist.synthesize_day_one_questions(
                    module_graph=module_graph, lineage_graph=lineage_graph, architecture_signals=signals
                )

                # Update the module graph with results (keys are repo-relative paths)
                for mod in modules_to_analyze:
                    key = str(mod.relative_to(self.repo_path)) if mod.is_absolute() else str(mod)
                    data = semanticist.index.get_module(key)
                    if data and key in module_graph.graph.nodes:
                        module_graph.graph.nodes[key]["purpose_statement"] = data.get("purpose")
                        module_graph.graph.nodes[key]["docstring_drift"] = data.get("docstring_drift")
            except Exception as exc:
                trace.log("Semanticist", "purpose_error", confidence=0.2, evidence_source=str(self.repo_path), analysis_method="LLM", extra={"error": str(exc)})

            progress.update(0, description="Serializing artifacts")
            try:
                write_json(self.cartography_dir / "module_graph.json", module_graph.export_json())
                write_json(self.cartography_dir / "lineage_graph.json", lineage_graph.export_json())
                write_json(self.cartography_dir / "knowledge_graph.json", knowledge_graph.export_json())
                write_json(self.cartography_dir / "architecture_signals.json", signals)
            except Exception as exc:
                self.logger.error("Artifact serialization failed: %s", exc)
                trace.log("Orchestrator", "serialize_error", confidence=0.2, evidence_source=str(self.cartography_dir), analysis_method="static", extra={"error": str(exc)})

            progress.update(0, description="Archivist: generating docs")
            try:
                Archivist(console=self.console, trace=trace).generate(
                    self.cartography_dir,
                    module_graph=module_graph,
                    lineage_graph=lineage_graph,
                    knowledge_graph=knowledge_graph,
                    architecture_signals=signals,
                )
            except Exception as exc:
                self.logger.error("Archivist failed: %s", exc)
                trace.log("Archivist", "generate_error", confidence=0.2, evidence_source=str(self.cartography_dir), analysis_method="static", extra={"error": str(exc)})

        trace.log("Orchestrator", "run_end", evidence_source=str(self.cartography_dir), analysis_method="static")
        try:
            current_state_for_repo(self.repo_path).save(state_path)
        except Exception:
            pass
        self.logger.info("Analysis complete. Artifacts written to %s", self.cartography_dir)


def _load_or_new(path: Path, *, kind: str) -> KnowledgeGraph:
    if path.exists():
        try:
            return KnowledgeGraph.load_from_json(_read_json(path))
        except Exception:
            return KnowledgeGraph(kind=kind)
    return KnowledgeGraph(kind=kind)


def _read_json(path: Path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_rel_path(p: str) -> str:
    # Git often emits forward slashes on Windows; normalize to platform separator for consistent matching.
    return str(p).replace("/", os.sep).replace("\\", os.sep)


def _prune_module_graph(module_graph: KnowledgeGraph, include_paths: set[str]) -> None:
    g = module_graph.graph
    for p in include_paths:
        if not p.endswith(".py"):
            continue
        if p not in g.nodes or g.nodes[p].get("type") != "module":
            continue
        # Preserve incoming edges from unchanged importers; prune outgoing edges so changed module dependencies refresh.
        out_edges = list(g.out_edges(p))
        for src, dst in out_edges:
            try:
                g.remove_edge(src, dst)
            except Exception:
                continue
