# src/agents/archivist.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
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
            module_graph,
            lineage_graph,
            architecture_signals,
        )
        self._write_onboarding_brief(
            cartography_dir,
            semantic_index,
            module_graph,
            lineage_graph,
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
        module_graph: KnowledgeGraph,
        lineage_graph: KnowledgeGraph,
        architecture_signals: Dict[str, Any],
    ) -> None:

        lines: List[str] = []
        lines.append("# CODEBASE.md\n\n")
        lines.append(f"Generated: {datetime.utcnow().isoformat()} UTC\n\n")

        lines.append("## Architecture Overview\n")
        summary = (semantic_index.get("summary") or "").strip()
        if summary:
            lines.append(summary + "\n\n")
        else:
            lines.append("- (No semantic summary found; run analysis to populate.)\n\n")

        lines.append("## Critical Path\n")
        critical = [
            (item.get("module") or item.get("node"))
            for item in (architecture_signals.get("critical_modules") or [])
            if (item.get("module") or item.get("node"))
        ]
        critical = [c for c in critical if isinstance(c, str)]
        for mod in critical[:15]:
            lines.append(f"- {mod}\n")
        if not critical:
            lines.append("- (No critical path computed.)\n")
        lines.append("\n")

        lines.append("## Data Sources & Sinks\n")
        sources = self._dataset_sources(lineage_graph)[:25]
        sinks = self._dataset_sinks(lineage_graph)[:25]
        lines.append("### Sources\n")
        for s in sources or ["(none detected)"]:
            lines.append(f"- {s}\n")
        lines.append("\n### Sinks\n")
        for s in sinks or ["(none detected)"]:
            lines.append(f"- {s}\n")
        lines.append("\n")

        lines.append("## Known Debt\n")
        debt_items: List[str] = []
        debt_items.extend((architecture_signals.get("dead_code_candidates") or [])[:15])
        debt_items.extend((architecture_signals.get("dead_code_candidates_v2") or [])[:15])
        risk = architecture_signals.get("risk_modules") or []
        for r in risk[:10]:
            node = r.get("module") or r.get("node")
            if node:
                debt_items.append(str(node))
        debt_items = [d for d in dict.fromkeys(debt_items) if d]
        for d in debt_items[:20] or ["(none detected)"]:
            lines.append(f"- {d}\n")
        lines.append("\n")

        lines.append("## High Velocity Files\n")
        for mod, vel in self._top_velocity_modules(module_graph, limit=20):
            lines.append(f"- {mod} (30d commits: {vel})\n")
        if not module_graph.graph.nodes:
            lines.append("- (no module graph nodes)\n")
        lines.append("\n")

        lines.append("## Module Purpose Index\n")
        lines.append("| Module | Purpose | Docstring Drift |\n")
        lines.append("|--------|---------|----------------|\n")
        for module, info in (semantic_index.get("modules") or {}).items():
            purpose = (info or {}).get("purpose", "") if isinstance(info, dict) else ""
            drift = ((info or {}).get("docstring_drift") or {}).get("severity", "low") if isinstance(info, dict) else "low"
            lines.append(f"| {module} | {purpose} | {drift} |\n")

        (cartography_dir / "CODEBASE.md").write_text("".join(lines), encoding="utf-8")
        if self.trace:
            self.trace.log("Archivist", "codebase_md_written", evidence_source=str(cartography_dir / "CODEBASE.md"), analysis_method="static")

    # ---------------------------------------------------------
    # ONBOARDING BRIEF
    # ---------------------------------------------------------
    def _write_onboarding_brief(
        self,
        cartography_dir: Path,
        semantic_index: Dict[str, Any],
        module_graph: KnowledgeGraph,
        lineage_graph: KnowledgeGraph,
    ) -> None:

        lines: List[str] = []
        lines.append("# onboarding_brief.md\n\n")
        lines.append("Derived from Surveyor (module graph), Hydrologist (lineage graph), and Semanticist outputs.\n\n")

        day_one = semantic_index.get("day_one_brief") or {}
        questions = day_one.get("questions") if isinstance(day_one, dict) else None
        if not isinstance(questions, list) or not questions:
            lines.append("## Day-1 Questions\n")
            lines.append("- (Day-1 synthesis missing. Re-run analysis to populate.)\n")
        else:
            lines.append("## Day-1 Questions\n")
            for item in questions[:5]:
                q = (item or {}).get("question", "")
                a = (item or {}).get("answer", "")
                cites = (item or {}).get("citations", [])
                lines.append(f"### {q}\n")
                lines.append(f"{a}\n\n")
                if cites:
                    lines.append("Evidence:\n")
                    for c in cites[:10]:
                        lines.append(f"- {c}\n")
                    lines.append("\n")

        (cartography_dir / "onboarding_brief.md").write_text("".join(lines), encoding="utf-8")
        if self.trace:
            self.trace.log("Archivist", "onboarding_brief_written", evidence_source=str(cartography_dir / "onboarding_brief.md"), analysis_method="static")

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

    def _top_velocity_modules(self, module_graph: KnowledgeGraph, *, limit: int = 20):
        g = module_graph.graph
        scored = []
        for n, a in g.nodes(data=True):
            if a.get("type") != "module":
                continue
            vel = int(a.get("change_velocity_30d") or 0)
            scored.append((n, vel))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[: max(1, int(limit))]
