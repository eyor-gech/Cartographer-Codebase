from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

from src.graph.knowledge_graph import KnowledgeGraph
from src.utils.file_utils import write_json
from src.utils.logging_utils import get_logger
from src.utils.trace_logger import TraceLogger


class Archivist:
    """Generates living documentation artifacts from computed graphs/signals."""

    def __init__(self, console: Optional[Console] = None, trace: Optional[TraceLogger] = None):
        self.console = console or Console()
        self.logger = get_logger(__name__)
        self.trace = trace

    def generate(
        self,
        cartography_dir: Path,
        *,
        module_graph: KnowledgeGraph,
        lineage_graph: KnowledgeGraph,
        knowledge_graph: KnowledgeGraph,
        architecture_signals: Dict[str, Any],
    ) -> None:
        cartography_dir.mkdir(parents=True, exist_ok=True)

        if self.trace:
            self.trace.log(
                "Archivist",
                "generate_docs_start",
                evidence_source=str(cartography_dir),
                analysis_method="static",
            )

        self._write_codebase_md(cartography_dir, architecture_signals, lineage_graph)
        self._write_onboarding_brief(cartography_dir, architecture_signals, lineage_graph)

        if self.trace:
            self.trace.log(
                "Archivist",
                "generate_docs_end",
                evidence_source=str(cartography_dir),
                analysis_method="static",
            )

    def _write_codebase_md(self, cartography_dir: Path, signals: Dict[str, Any], lineage_graph: KnowledgeGraph) -> None:
        critical = signals.get("critical_modules", []) or []
        risk = signals.get("risk_modules", []) or []
        dead = signals.get("dead_code_candidates", []) or []

        sources = self._dataset_sources(lineage_graph)
        sinks = self._dataset_sinks(lineage_graph)

        lines = []
        lines.append("# CODEBASE\n")
        lines.append("## Architecture Overview\n")
        lines.append("- Graph artifacts: module_graph.json, lineage_graph.json, knowledge_graph.json\n")
        lines.append("- Agents: Surveyor (structure), Hydrologist (lineage), Archivist (docs)\n\n")

        lines.append("## Critical Path\n")
        for item in critical[:10]:
            node = item.get("module") or item.get("node") or ""
            lines.append(f"- {node}\n")
        if not critical:
            lines.append("- (none)\n")
        lines.append("\n")

        lines.append("## Data Sources & Sinks\n")
        lines.append("### Sources\n")
        for ds in sources[:25]:
            lines.append(f"- {ds}\n")
        if not sources:
            lines.append("- (none)\n")
        lines.append("\n### Sinks\n")
        for ds in sinks[:25]:
            lines.append(f"- {ds}\n")
        if not sinks:
            lines.append("- (none)\n")
        lines.append("\n")

        lines.append("## Known Debt\n")
        for d in dead[:25]:
            lines.append(f"- Dead code candidate: {d}\n")
        if not dead:
            lines.append("- (none)\n")
        lines.append("\n")

        lines.append("## High-Velocity Files\n")
        for item in risk[:10]:
            node = item.get("module") or item.get("node") or ""
            lines.append(f"- {node}\n")
        if not risk:
            lines.append("- (none)\n")
        lines.append("\n")

        lines.append("## Module Purpose Index\n")
        lines.append("- (populated by Semanticist when enabled)\n")

        (cartography_dir / "CODEBASE.md").write_text("".join(lines), encoding="utf-8")

    def _write_onboarding_brief(self, cartography_dir: Path, signals: Dict[str, Any], lineage_graph: KnowledgeGraph) -> None:
        critical = signals.get("critical_modules", []) or []
        sources = self._dataset_sources(lineage_graph)
        sinks = self._dataset_sinks(lineage_graph)

        lines = []
        lines.append("# Onboarding Brief\n\n")
        lines.append("## What this system is\n")
        lines.append("- Populate after first analysis run; update as drift is detected.\n\n")

        lines.append("## Critical modules to read first\n")
        for item in critical[:10]:
            node = item.get("module") or item.get("node") or ""
            lines.append(f"- {node}\n")
        if not critical:
            lines.append("- (none)\n")
        lines.append("\n")

        lines.append("## Top data sources\n")
        for ds in sources[:10]:
            lines.append(f"- {ds}\n")
        if not sources:
            lines.append("- (none)\n")
        lines.append("\n")

        lines.append("## Top sinks / outputs\n")
        for ds in sinks[:10]:
            lines.append(f"- {ds}\n")
        if not sinks:
            lines.append("- (none)\n")
        lines.append("\n")

        (cartography_dir / "onboarding_brief.md").write_text("".join(lines), encoding="utf-8")

    def _dataset_sources(self, lineage_graph: KnowledgeGraph) -> list[str]:
        g = lineage_graph.graph
        out: list[str] = []
        for n, a in g.nodes(data=True):
            if a.get("type") != "dataset":
                continue
            produced = False
            for pred in g.predecessors(n):
                if g.edges[pred, n].get("type") == "produces":
                    produced = True
                    break
            if not produced:
                out.append(n)
        return sorted(out)

    def _dataset_sinks(self, lineage_graph: KnowledgeGraph) -> list[str]:
        g = lineage_graph.graph
        out: list[str] = []
        for n, a in g.nodes(data=True):
            if a.get("type") != "dataset":
                continue
            consumed = False
            for pred in g.predecessors(n):
                if g.edges[pred, n].get("type") == "consumes":
                    consumed = True
                    break
            if not consumed:
                out.append(n)
        return sorted(out)

