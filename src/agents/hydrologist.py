from pathlib import Path
import networkx as nx

from src.analyzers.sql_lineage import SQLLineageAnalyzer
from src.graph.knowledge_graph import KnowledgeGraph
from src.models.nodes import DatasetNode, TransformationNode
from src.utils.logging_utils import get_logger


class Hydrologist:
    """Reconstructs dataset lineage using SQL parsing."""

    def __init__(self, repo_path: Path, graph: KnowledgeGraph):
        self.repo_path = repo_path
        self.graph = graph
        self.analyzer = SQLLineageAnalyzer()
        self.logger = get_logger(__name__)

    def analyze(self):
        self.logger.info("Hydrologist scanning repository for SQL lineage")
        for path in self.repo_path.rglob("*.sql"):
            rel = str(path.relative_to(self.repo_path))
            try:
                deps = self.analyzer.analyze_file(path)
                if not deps:
                    continue
                sources = deps.get("source_tables", [])
                targets = deps.get("target_tables", []) or [rel]  # default target is file

                # create transformation node per SQL file
                transform_id = f"transform:{rel}"
                transform_node = TransformationNode(
                    source_datasets=sources,
                    target_datasets=targets,
                    source_file=rel,
                    line_range=None,
                )
                self.graph.add_transformation_node(transform_id, **transform_node.model_dump())

                for src in sources:
                    self.graph.add_dataset_node(src, **DatasetNode(name=src).model_dump())
                    self.graph.add_consumes_edge(transform_id, src)
                for tgt in targets:
                    self.graph.add_dataset_node(tgt, **DatasetNode(name=tgt).model_dump())
                    self.graph.add_produces_edge(transform_id, tgt)
            except Exception as exc:
                self.logger.error("Hydrologist failed processing %s: %s", path, exc)
                continue

    # Query helpers
    def blast_radius(self, dataset_name: str):
        """Return all downstream datasets reachable from a starting dataset."""
        g = self.graph.graph
        if dataset_name not in g:
            return []
        downstream = []
        for target in nx.descendants(g, dataset_name):
            if g.nodes[target].get("type") == "dataset":
                downstream.append(target)
        return downstream

    def find_sources(self):
        g = self.graph.graph
        return [n for n in g.nodes if g.in_degree(n) == 0 and g.nodes[n].get("type") == "dataset"]

    def find_sinks(self):
        g = self.graph.graph
        return [n for n in g.nodes if g.out_degree(n) == 0 and g.nodes[n].get("type") == "dataset"]
