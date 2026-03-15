from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
from rich.console import Console

from src.graph.knowledge_graph import KnowledgeGraph
from src.utils.semantic_index import SemanticIndex
from src.models.edges import EdgeType
from src.utils.logging_utils import get_logger

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore[assignment]


class Navigator:
    """
    Interactive query interface over existing cartography artifacts.

    Implemented as a lightweight tool-orchestration loop (agent-style dispatcher).
    """

    def __init__(
        self,
        module_graph: KnowledgeGraph,
        lineage_graph: KnowledgeGraph,
        *,
        semantic_index: Optional[SemanticIndex] = None,
        repo_root: Optional[Path] = None,
        console: Optional[Console] = None,
    ):
        self.module_graph = module_graph
        self.lineage_graph = lineage_graph
        self.semantic_index = semantic_index
        self.repo_root = repo_root
        self.console = console or Console()
        self.logger = get_logger(__name__)
        self._embedding_model = None
        if SentenceTransformer is not None:
            try:
                self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                self._embedding_model = None

    @classmethod
    def from_cartography_dir(cls, cartography_dir: Path, console: Optional[Console] = None) -> "Navigator":
        module = KnowledgeGraph.load_from_json(_read_json(cartography_dir / "module_graph.json"))
        lineage = KnowledgeGraph.load_from_json(_read_json(cartography_dir / "lineage_graph.json"))
        sem_path = cartography_dir / "semantic_index.json"
        sem = SemanticIndex(sem_path) if sem_path.exists() else None
        repo_root = cartography_dir.parent if cartography_dir.name == ".cartography" else None
        return cls(module, lineage, semantic_index=sem, repo_root=repo_root, console=console)

    # ---------------------------------------------------------------------
    # Tool orchestration loop (agent-style dispatcher)
    # ---------------------------------------------------------------------
    def run_query(self, query: str) -> Dict[str, Any]:
        """
        Route a user query to a tool and return a structured response.

        Response schema:
        {
          "tool": "...",
          "result": ...,
          "evidence": [{"source_file": "...", "line_range": [a,b], "analysis_method": "..."}]
        }
        """
        query = (query or "").strip()
        if not query:
            return {"tool": "noop", "result": "", "evidence": []}

        # Explicit tool commands
        lowered = query.lower()
        if lowered.startswith("find "):
            return self.find_implementation(query.split(" ", 1)[1].strip())
        if lowered.startswith("trace "):
            rest = query.split(" ", 1)[1].strip()
            dataset, direction = _split_dataset_direction(rest)
            return self.trace_lineage(dataset, direction=direction)
        if lowered.startswith("blastmod "):
            target = query.split(" ", 1)[1].strip()
            out = self.blast_radius(target)
            evidence = [{"source_file": m, "line_range": self._file_line_range(m), "analysis_method": "static"} for m in out[:25]]
            return {"tool": "blast_radius", "result": out, "evidence": evidence}
        if lowered.startswith("explain "):
            return self.explain_module(query.split(" ", 1)[1].strip())

        # Heuristic routing
        if "lineage" in lowered or "dataset" in lowered:
            return self.trace_lineage(query, direction="downstream")
        if "purpose" in lowered or "explain" in lowered:
            return self.explain_module(query)
        return self.find_implementation(query)

    # ---------------------------------------------------------------------
    # Lineage tools
    # ---------------------------------------------------------------------
    def blast_radius(self, node: str) -> List[str]:
        """
        Overloaded blast radius:
        - If `node` is a module path in the module graph: return downstream impacted modules (reverse imports).
        - Otherwise: treat as a dataset name and return downstream datasets.
        """
        node = node.strip()
        mg = self.module_graph.graph
        if node in mg and mg.nodes[node].get("type") == "module":
            impacted: set[str] = set()
            queue: List[str] = [node]
            seen: set[str] = {node}
            while queue:
                m = queue.pop(0)
                for importer in mg.predecessors(m):
                    if mg.edges[importer, m].get("type") != EdgeType.IMPORTS.value:
                        continue
                    impacted.add(importer)
                    if importer not in seen:
                        seen.add(importer)
                        queue.append(importer)
            return sorted(impacted)

        dataset = node.strip().strip("`").strip('"').strip("'")
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

    def trace_lineage(self, dataset: str, *, direction: str = "downstream") -> Dict[str, Any]:
        dataset = dataset.strip().strip("`").strip('"').strip("'")
        g = self.lineage_graph.graph
        if dataset not in g:
            return {"tool": "trace_lineage", "result": [], "evidence": [], "error": "dataset_not_found"}

        direction = (direction or "downstream").lower()
        downstream = direction in {"down", "downstream", "to_sinks"}

        visited: set[str] = {dataset}
        queue: List[str] = [dataset]
        results: List[str] = []
        evidence: List[Dict[str, Any]] = []

        while queue:
            ds = queue.pop(0)
            if downstream:
                # dataset -> transformations that consume it -> produced datasets
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
                        if out_ds not in visited:
                            visited.add(out_ds)
                            queue.append(out_ds)
                            results.append(out_ds)
                            ev = _edge_evidence(g, t, out_ds) or _edge_evidence(g, t, ds)
                            if ev:
                                evidence.append(ev)
            else:
                # dataset -> transformations that produce it -> consumed datasets
                for t in g.predecessors(ds):
                    if g.nodes[t].get("type") != "transformation":
                        continue
                    if g.edges[t, ds].get("type") != EdgeType.PRODUCES.value:
                        continue
                    for in_ds in g.successors(t):
                        if g.nodes[in_ds].get("type") != "dataset":
                            continue
                        if g.edges[t, in_ds].get("type") != EdgeType.CONSUMES.value:
                            continue
                        if in_ds not in visited:
                            visited.add(in_ds)
                            queue.append(in_ds)
                            results.append(in_ds)
                            ev = _edge_evidence(g, t, in_ds) or _edge_evidence(g, t, ds)
                            if ev:
                                evidence.append(ev)

        return {"tool": "trace_lineage", "result": results, "evidence": evidence, "analysis_method": "static"}

    # ---------------------------------------------------------------------
    # Semantic tools
    # ---------------------------------------------------------------------
    def find_implementation(self, concept: str, *, top_k: int = 5) -> Dict[str, Any]:
        if not self.semantic_index or not self._embedding_model:
            return {"tool": "find_implementation", "result": [], "evidence": [], "error": "semantic_index_unavailable"}
        concept = (concept or "").strip()
        if not concept:
            return {"tool": "find_implementation", "result": [], "evidence": []}

        query_vec = self._embedding_model.encode([concept])[0]
        hits = self.semantic_index.search(list(map(float, query_vec)), top_k=top_k)
        evidence = [{"source_file": h["module"], "line_range": self._file_line_range(h["module"]), "analysis_method": "semantic_vector"} for h in hits]
        return {"tool": "find_implementation", "result": hits, "evidence": evidence}

    # ---------------------------------------------------------------------
    # Module impact tools
    # ---------------------------------------------------------------------
    def explain_module(self, module_path: str) -> Dict[str, Any]:
        module_path = module_path.strip()
        g = self.module_graph.graph
        if module_path not in g and self.semantic_index and self.semantic_index.get_module(module_path) is None:
            return {"tool": "explain_module", "result": {}, "evidence": [], "error": "module_not_found"}

        semantic = (self.semantic_index.get_module(module_path) if self.semantic_index else None) or {}
        node_attrs = dict(g.nodes[module_path]) if module_path in g else {}

        related = self._related_lineage_for_source_file(module_path)
        evidence: List[Dict[str, Any]] = []
        evidence.append({"source_file": module_path, "line_range": self._file_line_range(module_path), "analysis_method": "static"})
        for ev in related.get("evidence", [])[:10]:
            evidence.append(ev)

        result = {
            "module": module_path,
            "purpose": semantic.get("purpose") or node_attrs.get("purpose_statement"),
            "docstring_drift": semantic.get("docstring_drift") or node_attrs.get("docstring_drift"),
            "related_lineage": related.get("datasets", {}),
        }
        return {"tool": "explain_module", "result": result, "evidence": evidence}

    def _related_lineage_for_source_file(self, source_file: str) -> Dict[str, Any]:
        g = self.lineage_graph.graph
        datasets_in: set[str] = set()
        datasets_out: set[str] = set()
        evidence: List[Dict[str, Any]] = []

        for n, a in g.nodes(data=True):
            if a.get("type") != "transformation":
                continue
            if (a.get("source_file") or "") != source_file:
                continue
            for ds in g.successors(n):
                if g.nodes[ds].get("type") == "dataset":
                    et = g.edges[n, ds].get("type")
                    if et == EdgeType.CONSUMES.value:
                        datasets_in.add(ds)
                    elif et == EdgeType.PRODUCES.value:
                        datasets_out.add(ds)
                    ev = _edge_evidence(g, n, ds)
                    if ev:
                        evidence.append(ev)

        return {"datasets": {"consumes": sorted(datasets_in), "produces": sorted(datasets_out)}, "evidence": evidence}

    def _file_line_range(self, module_path: str) -> List[int]:
        if not self.repo_root:
            return [1, 1]
        p = self.repo_root / module_path
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            lines = text.count("\n") + 1 if text else 1
            return [1, int(lines)]
        except Exception:
            return [1, 1]


def _read_json(path: Path) -> Dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _edge_evidence(g: nx.DiGraph, src: str, dst: str) -> Optional[Dict[str, Any]]:
    attrs = g.edges[src, dst]
    sf = attrs.get("source_file") or g.nodes[src].get("source_file")
    lr = attrs.get("line_range") or g.nodes[src].get("line_range") or [1, 1]
    if not sf:
        return None
    if isinstance(lr, list) and len(lr) >= 2:
        line_range = [int(lr[0] or 1), int(lr[1] or lr[0] or 1)]
    else:
        line_range = [1, 1]
    return {"source_file": sf, "line_range": line_range, "analysis_method": "static"}


def _split_dataset_direction(text: str) -> Tuple[str, str]:
    parts = (text or "").split()
    if not parts:
        return "", "downstream"
    if len(parts) == 1:
        return parts[0], "downstream"
    return parts[0], parts[1]
