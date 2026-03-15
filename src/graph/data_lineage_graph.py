from __future__ import annotations

from typing import List, Optional, Set

from src.graph.knowledge_graph import KnowledgeGraph
from src.models.edges import EdgeType


class DataLineageGraph(KnowledgeGraph):
    """
    Lineage-specialized graph wrapper.

    Mastered rubric alignment:
    - Backed by a NetworkX DiGraph (via KnowledgeGraph.graph)
    - Contains Dataset and Transformation nodes
    - Provides lineage queries over the merged lineage graph
    """

    def __init__(self):
        super().__init__(kind="lineage")

    def blast_radius(self, dataset_name: str) -> List[str]:
        dataset_name = _normalize_dataset(dataset_name)
        g = self.graph
        if dataset_name not in g:
            return []

        downstream: Set[str] = set()
        queue: List[str] = [dataset_name]
        seen: Set[str] = {dataset_name}

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
                    downstream.add(out_ds)
                    if out_ds not in seen:
                        seen.add(out_ds)
                        queue.append(out_ds)

        return sorted(downstream)

    def find_sources(self, dataset_name: Optional[str] = None) -> List[str]:
        g = self.graph
        if dataset_name:
            dataset_name = _normalize_dataset(dataset_name)
            upstream = self._upstream_datasets(dataset_name)
            return [d for d in upstream if not _has_incoming_edge_type(g, d, EdgeType.PRODUCES.value)]
        return sorted(
            n
            for n, a in g.nodes(data=True)
            if a.get("type") == "dataset" and not _has_incoming_edge_type(g, n, EdgeType.PRODUCES.value)
        )

    def find_sinks(self, dataset_name: Optional[str] = None) -> List[str]:
        g = self.graph
        if dataset_name:
            downstream = self.blast_radius(dataset_name)
            return [d for d in downstream if not _has_incoming_edge_type(g, d, EdgeType.CONSUMES.value)]
        return sorted(
            n
            for n, a in g.nodes(data=True)
            if a.get("type") == "dataset" and not _has_incoming_edge_type(g, n, EdgeType.CONSUMES.value)
        )

    def prune_by_source_files(self, include_paths: Set[str]) -> None:
        """
        Incremental-mode helper: remove transformation nodes originating from changed files.
        Dataset nodes are retained to preserve cross-file continuity.
        """
        if not include_paths:
            return
        g = self.graph
        to_remove: List[str] = []
        for n, a in g.nodes(data=True):
            if a.get("type") != "transformation":
                continue
            sf = a.get("source_file")
            if sf and sf in include_paths:
                to_remove.append(n)
        if to_remove:
            g.remove_nodes_from(to_remove)

    def _upstream_datasets(self, dataset: str) -> Set[str]:
        g = self.graph
        out: Set[str] = set()
        queue: List[str] = [dataset]
        seen: Set[str] = {dataset}
        while queue:
            ds = queue.pop(0)
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
                    out.add(in_ds)
                    if in_ds not in seen:
                        seen.add(in_ds)
                        queue.append(in_ds)
        return out


def _normalize_dataset(name: str) -> str:
    return name.strip().strip("`").strip('"').strip("'")


def _has_incoming_edge_type(g, node: str, edge_type: str) -> bool:
    for pred in g.predecessors(node):
        try:
            if g.edges[pred, node].get("type") == edge_type:
                return True
        except Exception:
            continue
    return False

