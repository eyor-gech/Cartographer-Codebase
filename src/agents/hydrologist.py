from pathlib import Path
import networkx as nx
from typing import Dict, List, Optional, Set, Tuple

from src.analyzers.sql_lineage import SQLLineageAnalyzer
from src.analyzers.python_dataflow import PythonDataflowAnalyzer
from src.analyzers.dag_config_parser import DAGConfigParser
from src.graph.knowledge_graph import KnowledgeGraph
from src.models.nodes import DatasetNode, TransformationNode
from src.utils.logging_utils import get_logger
from src.utils.graph_cache import GraphCache
from src.models.edges import EdgeType
from src.utils.trace_logger import TraceLogger


class Hydrologist:
    """Reconstructs dataset lineage using SQL parsing."""

    def __init__(
        self,
        repo_path: Path,
        graph: KnowledgeGraph,
        cache: Optional[GraphCache] = None,
        trace: Optional[TraceLogger] = None,
    ):
        self.repo_path = repo_path
        self.graph = graph
        self.analyzer = SQLLineageAnalyzer()  # preserved attribute name
        self.python = PythonDataflowAnalyzer()
        self.config = DAGConfigParser(repo_path)
        self.logger = get_logger(__name__)
        self.cache = cache or GraphCache()
        self.trace = trace

    def analyze(self, include_paths: set[str] | None = None):
        self.logger.info("Hydrologist scanning repository for cross-language lineage")
        if self.trace:
            self.trace.log("Hydrologist", "analyze_start", evidence_source=str(self.repo_path), analysis_method="static")
        events: List[Dict] = []
        events.extend(self._sql_events(include_paths=include_paths))
        events.extend(self._python_events(include_paths=include_paths))
        events.extend(self._config_events(include_paths=include_paths))

        for idx, ev in enumerate(events):
            try:
                self._apply_event(ev, idx)
            except Exception as exc:
                self.logger.error("Hydrologist failed applying event from %s: %s", ev.get("source_file"), exc)
                continue

        # cache invalidation
        self.cache.clear()
        if self.trace:
            self.trace.log(
                "Hydrologist",
                "analyze_end",
                evidence_source=str(self.repo_path),
                analysis_method="static",
                extra={"events": len(events)},
            )

    def _sql_events(self, *, include_paths: set[str] | None = None) -> List[Dict]:
        out: List[Dict] = []
        for path in self.repo_path.rglob("*.sql"):
            rel = str(path.relative_to(self.repo_path))
            if include_paths is not None and rel not in include_paths:
                continue
            try:
                deps = self.analyzer.analyze_file(path)
                if not deps:
                    continue
                out.append(
                    {
                        "source_datasets": deps.get("source_tables", []),
                        "target_datasets": deps.get("target_tables", []) or [path.stem],
                        "transformation_type": "sql",
                        "source_file": rel,
                        "line_range": deps.get("line_range") or [1, 1],
                        "dynamic_reference": False,
                    }
                )
            except Exception as exc:
                self.logger.error("Hydrologist SQL event failure %s: %s", path, exc)
                continue
        return out

    def _python_events(self, *, include_paths: set[str] | None = None) -> List[Dict]:
        out: List[Dict] = []
        for path in self.repo_path.rglob("*.py"):
            rel = str(path.relative_to(self.repo_path))
            if include_paths is not None and rel not in include_paths:
                continue
            try:
                events = self.python.analyze_file(path, repo_root=self.repo_path)
            except Exception as exc:
                self.logger.error("Hydrologist Python event failure %s: %s", path, exc)
                continue

            # Reconcile SQL literals from read_sql/execute into table dependencies
            for ev in events:
                if not ev.get("dynamic_reference") and ev.get("source_datasets"):
                    srcs = ev["source_datasets"]
                    if len(srcs) == 1 and self._looks_like_sql(srcs[0]):
                        sql_text = srcs[0]
                        try:
                            sql_text = self.analyzer.preprocess_dbt(sql_text)
                            sources, targets = self.analyzer.parse_dependencies(sql_text)
                            ev["source_datasets"] = sorted(sources)
                            # Keep existing python target if present; otherwise use sql targets if any
                            if not ev.get("target_datasets") and targets:
                                ev["target_datasets"] = sorted(targets)
                        except Exception as exc:
                            self.logger.debug("Failed reconciling SQL literal in %s: %s", path, exc)
                out.append(ev)
        return out

    def _config_events(self, *, include_paths: set[str] | None = None) -> List[Dict]:
        try:
            events = self.config.extract_lineage_events()
            if include_paths is None:
                return events
            filtered = []
            for ev in events:
                sf = ev.get("source_file")
                if sf and sf in include_paths:
                    filtered.append(ev)
            return filtered
        except Exception as exc:
            self.logger.error("Hydrologist config parse failure: %s", exc)
            return []

    def _apply_event(self, ev: Dict, idx: int) -> None:
        srcs = [self._normalize_dataset(s) for s in ev.get("source_datasets") or [] if s]
        tgts = [self._normalize_dataset(t) for t in ev.get("target_datasets") or [] if t]
        ttype = ev.get("transformation_type") or "unknown"
        source_file = ev.get("source_file") or "<unknown>"
        line_range = ev.get("line_range") or [1, 1]
        dynamic = bool(ev.get("dynamic_reference"))

        transform_id = f"transform:{ttype}:{source_file}:{idx}"
        transform_node = TransformationNode(
            source_datasets=srcs,
            target_datasets=tgts,
            transformation_type=ttype,
            source_file=source_file,
            line_range=line_range,
        )
        self.graph.add_transformation_node(transform_id, **transform_node.model_dump())

        for src in srcs:
            self._add_dataset(src)
            self._add_edge_with_meta(transform_id, src, EdgeType.CONSUMES.value, ttype, source_file, line_range, dynamic)
        for tgt in tgts:
            self._add_dataset(tgt)
            self._add_edge_with_meta(transform_id, tgt, EdgeType.PRODUCES.value, ttype, source_file, line_range, dynamic)

    def _add_dataset(self, name: str) -> None:
        if name not in self.graph.graph.nodes:
            self.graph.add_dataset_node(name, **DatasetNode(name=name).model_dump())

    def _add_edge_with_meta(
        self,
        src: str,
        dst: str,
        edge_type: str,
        transformation_type: str,
        source_file: str,
        line_range: List[int],
        dynamic_reference: bool,
    ) -> None:
        # Do not modify core KnowledgeGraph helpers; write richer edge metadata directly.
        self.graph.graph.add_edge(
            src,
            dst,
            type=edge_type,
            transformation_type=transformation_type,
            source_file=source_file,
            line_range=line_range,
            dynamic_reference=dynamic_reference,
            analysis_method="static",
        )

    def _looks_like_sql(self, text: str) -> bool:
        t = text.lower()
        return ("select" in t and "from" in t) or t.strip().startswith(("with", "insert", "create"))

    def _normalize_dataset(self, name: str) -> str:
        return name.strip().strip("`").strip('"').strip("'")

    # Query helpers
    def blast_radius(self, dataset_name: str):
        """
        Return all downstream datasets reachable from a starting dataset.

        Note: lineage edges are stored as transformation -> dataset for both CONSUMES/PRODUCES,
        so traversal is done via edge-type filtering.
        """
        dataset_name = self._normalize_dataset(dataset_name)
        cached = self.cache.get(dataset_name)
        if cached is not None:
            return cached

        g = self.graph.graph
        if dataset_name not in g:
            self.cache.set(dataset_name, [])
            return []

        downstream: Set[str] = set()
        queue: List[str] = [dataset_name]
        seen: Set[str] = {dataset_name}

        while queue:
            ds = queue.pop(0)
            # Find transformations that CONSUME this dataset (incoming edge from transform -> dataset)
            for t in g.predecessors(ds):
                if g.nodes[t].get("type") != "transformation":
                    continue
                if g.edges[t, ds].get("type") != EdgeType.CONSUMES.value:
                    continue
                # Follow PRODUCES edges from transformation to downstream datasets
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

        result = sorted(downstream)
        self.cache.set(dataset_name, result)
        return result

    def find_sources(self, dataset_name: Optional[str] = None):
        """Datasets not produced by any transformation (or upstream sources for a given dataset)."""
        g = self.graph.graph
        if dataset_name:
            dataset_name = self._normalize_dataset(dataset_name)
            upstream = self._upstream_datasets(dataset_name)
            return [d for d in upstream if not self._has_incoming_edge_type(d, EdgeType.PRODUCES.value)]
        return [n for n, a in g.nodes(data=True) if a.get("type") == "dataset" and not self._has_incoming_edge_type(n, EdgeType.PRODUCES.value)]

    def find_sinks(self, dataset_name: Optional[str] = None):
        """Datasets not consumed by any transformation (or downstream sinks for a given dataset)."""
        g = self.graph.graph
        if dataset_name:
            downstream = self.blast_radius(dataset_name)
            return [d for d in downstream if not self._has_incoming_edge_type(d, EdgeType.CONSUMES.value)]
        return [n for n, a in g.nodes(data=True) if a.get("type") == "dataset" and not self._has_incoming_edge_type(n, EdgeType.CONSUMES.value)]

    def _has_incoming_edge_type(self, dataset: str, edge_type: str) -> bool:
        g = self.graph.graph
        for pred in g.predecessors(dataset):
            try:
                if g.edges[pred, dataset].get("type") == edge_type:
                    return True
            except Exception:
                continue
        return False

    def _upstream_datasets(self, dataset: str) -> Set[str]:
        g = self.graph.graph
        out: Set[str] = set()
        queue: List[str] = [dataset]
        seen: Set[str] = {dataset}
        while queue:
            ds = queue.pop(0)
            for t in g.predecessors(ds):
                if g.nodes[t].get("type") != "transformation":
                    continue
                # If transformation PRODUCES ds, then its consumed datasets are upstream.
                if g.edges[t, ds].get("type") != EdgeType.PRODUCES.value:
                    continue
                for in_ds in g.successors(t):
                    if g.nodes[in_ds].get("type") != "dataset":
                        continue
                    if g.edges[t, in_ds].get("type") != EdgeType.CONSUMES.value:
                        continue
                    out.add(in_ds)
                    if in_ds not in seen:
                        seen.add(in_ds)
                        queue.append(in_ds)
        return out
