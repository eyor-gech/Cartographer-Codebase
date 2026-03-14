# src/agents/archivist.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from rich.console import Console
from rich.table import Table

from src.graph.knowledge_graph import KnowledgeGraph
from src.utils.trace_logger import TraceLogger
from src.utils.logging_utils import get_logger


class Archivist:
    """
    Generates living documentation artifacts from system analysis.

    Features:
    - CODEBASE.md with modules, purposes, criticality, docstring drift
    - Onboarding brief (high-level system summary)
    - Maintains trace logs for all artifact generation steps
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        trace: Optional[TraceLogger] = None,
    ):
        self.console = console or Console()
        self.logger = get_logger(__name__)
        self.trace = trace

    # ---------------------------------------------------------
    # PUBLIC ENTRYPOINT
    # ---------------------------------------------------------
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

        semantic_index = self._load_semantic_index(cartography_dir)
        critical_modules = architecture_signals.get("critical_modules", [])

        self._write_codebase_md(
            cartography_dir,
            semantic_index,
            lineage_graph,
            critical_modules,
        )
        self._write_onboarding_brief(
            cartography_dir,
            semantic_index,
            lineage_graph,
            critical_modules,
        )

        if self.trace:
            self.trace.log(
                "Archivist",
                "generate_docs_end",
                evidence_source=str(cartography_dir),
                analysis_method="static",
            )

    # ---------------------------------------------------------
    # CODEBASE.MD GENERATION
    # ---------------------------------------------------------
    def _write_codebase_md(
        self,
        cartography_dir: Path,
        semantic_index: Dict[str, Any],
        lineage_graph: KnowledgeGraph,
        critical_modules: list,
    ) -> None:

        lines = []
        lines.append(f"# CODEBASE – Living Architectural Memory\n\n")
        lines.append(f"Generated: {datetime.utcnow().isoformat()} UTC\n\n")

        # System overview
        lines.append("## System Overview\n")
        lines.append("- Repository: _auto-fill after CLI run_\n")
        lines.append("- Domain: _auto-detect (analytics/dbt/etc)_\n")
        lines.append("- Primary languages: _Python, SQL, YAML_\n\n")

        # Critical Modules
        lines.append("## Critical Modules\n")
        for mod in critical_modules[:15]:
            node = mod.get("module") or mod.get("node")
            lines.append(f"- {node}\n")
        lines.append("\n")

        # Data Sources / Sinks
        sources = self._dataset_sources(lineage_graph)
        sinks = self._dataset_sinks(lineage_graph)

        lines.append("## Primary Data Sources\n")
        for s in sources[:20]:
            lines.append(f"- {s}\n")
        lines.append("\n## Primary Data Sinks\n")
        for s in sinks[:20]:
            lines.append(f"- {s}\n")
        lines.append("\n")

        # Module Purpose Table
        lines.append("## Module Purpose Index\n")
        lines.append("| Module | Purpose | Critical | Docstring Drift |\n")
        lines.append("|--------|--------|---------|----------------|\n")

        for module, info in semantic_index.get("modules", {}).items():
            purpose = info.get("purpose", "")
            drift = info.get("docstring_drift", {}).get("severity", "none")
            critical = "Yes" if module in [c.get("module") or c.get("node") for c in critical_modules] else "No"
            lines.append(f"| {module} | {purpose} | {critical} | {drift} |\n")

        # Write CODEBASE.md
        (cartography_dir / "CODEBASE.md").write_text("".join(lines), encoding="utf-8")

    # ---------------------------------------------------------
    # ONBOARDING BRIEF
    # ---------------------------------------------------------
    def _write_onboarding_brief(
        self,
        cartography_dir: Path,
        semantic_index: Dict[str, Any],
        lineage_graph: KnowledgeGraph,
        critical_modules: list,
    ) -> None:

        lines = []
        lines.append("# Onboarding Brief\n\n")
        lines.append("## Overview\n")
        lines.append("Derived from semantic and lineage analysis.\n\n")

        # Critical modules
        lines.append("## Critical Modules\n")
        for mod in critical_modules[:10]:
            node = mod.get("module") or mod.get("node")
            lines.append(f"- {node}\n")
        lines.append("\n")

        # Data flow
        sources = self._dataset_sources(lineage_graph)
        sinks = self._dataset_sinks(lineage_graph)
        lines.append("## Primary Data Sources\n")
        for s in sources[:10]:
            lines.append(f"- {s}\n")
        lines.append("\n## Primary Data Outputs\n")
        for s in sinks[:10]:
            lines.append(f"- {s}\n")

        # Write onboarding_brief.md
        (cartography_dir / "onboarding_brief.md").write_text("".join(lines), encoding="utf-8")

    # ---------------------------------------------------------
    # DATASET UTILITIES
    # ---------------------------------------------------------
    def _dataset_sources(self, lineage_graph: KnowledgeGraph):
        g = lineage_graph.graph
        return sorted(
            n for n, a in g.nodes(data=True)
            if a.get("type") == "dataset" and g.in_degree(n) == 0
        )

    def _dataset_sinks(self, lineage_graph: KnowledgeGraph):
        g = lineage_graph.graph
        return sorted(
            n for n, a in g.nodes(data=True)
            if a.get("type") == "dataset" and g.out_degree(n) == 0
        )

    # ---------------------------------------------------------
    # SEMANTIC INDEX LOADER
    # ---------------------------------------------------------
    def _load_semantic_index(self, cartography_dir: Path):
        path = cartography_dir / "semantic_index.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {"modules": {}}
        return {"modules": {}}