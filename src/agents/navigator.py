from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx
from rich.console import Console

from src.graph.knowledge_graph import KnowledgeGraph
from src.models.edges import EdgeType
from src.utils.logging_utils import get_logger


class Navigator:
    """
    Interactive query interface over existing cartography artifacts.

    This is intentionally lightweight (no external orchestration dependency required).
    """

    def __init__(self, module_graph: KnowledgeGraph, lineage_graph: KnowledgeGraph, console: Optional[Console] = None):
        self.module_graph = module_graph
        self.lineage_graph = lineage_graph
        self.console = console or Console()
        self.logger = get_logger(__name__)

    @classmethod
    def from_cartography_dir(cls, cartography_dir: Path, console: Optional[Console] = None) -> "Navigator":
        module = KnowledgeGraph.load_from_json(_read_json(cartography_dir / "module_graph.json"))
        lineage = KnowledgeGraph.load_from_json(_read_json(cartography_dir / "lineage_graph.json"))
        return cls(module, lineage, console=console)

    def blast_radius(self, dataset: str) -> List[str]:
        dataset = dataset.strip()
        g = self.lineage_graph.graph
        if dataset not in g:
            return []
        downstream: set[str] = set()
        queue: List[str] = [dataset]
        seen: set[str] = {dataset}
        while queue:
            ds = queue.pop(0)
            for t in g.predecessors(ds):
                if g.nodes[t].get("type") != "transformation":
                    continue
                if g.edges[t, ds].get("type") != EdgeType.CONSUMES.value:
                    continue
                for out_ds in g.successors(t):
                    if g.nodes[out_ds].get("type") != "dataset":
                        continue
                    if g.edges[t, out_ds].get("type") != EdgeType.PRODUCES.value:
                        continue
                    if out_ds not in downstream:
                        downstream.add(out_ds)
                    if out_ds not in seen:
                        seen.add(out_ds)
                        queue.append(out_ds)
        return sorted(downstream)

    def find_sources(self) -> List[str]:
        g = self.lineage_graph.graph
        out: List[str] = []
        for n, a in g.nodes(data=True):
            if a.get("type") != "dataset":
                continue
            produced = any(g.edges[p, n].get("type") == EdgeType.PRODUCES.value for p in g.predecessors(n))
            if not produced:
                out.append(n)
        return sorted(out)

    def find_sinks(self) -> List[str]:
        g = self.lineage_graph.graph
        out: List[str] = []
        for n, a in g.nodes(data=True):
            if a.get("type") != "dataset":
                continue
            consumed = any(g.edges[p, n].get("type") == EdgeType.CONSUMES.value for p in g.predecessors(n))
            if not consumed:
                out.append(n)
        return sorted(out)

    def explain_module(self, module_path: str) -> Dict[str, Any]:
        g = self.module_graph.graph
        if module_path not in g:
            return {}
        return dict(g.nodes[module_path])


def _read_json(path: Path) -> Dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))

