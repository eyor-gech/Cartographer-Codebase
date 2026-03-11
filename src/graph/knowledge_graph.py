import json
import networkx as nx
from typing import Any, Dict
from networkx.readwrite import json_graph

from src.models.graph_types import GraphKind
from src.models.edges import EdgeType


class KnowledgeGraph:
    """Wrapper around NetworkX directed graph with typed helpers."""

    def __init__(self, kind: str):
        self.kind = GraphKind(kind)
        self.graph = nx.DiGraph()

    # Node helpers
    def add_module_node(self, node_id: str, **attrs):
        self.graph.add_node(node_id, type="module", **attrs)

    def add_dataset_node(self, node_id: str, **attrs):
        self.graph.add_node(node_id, type="dataset", **attrs)

    def add_transformation_node(self, node_id: str, **attrs):
        self.graph.add_node(node_id, type="transformation", **attrs)

    # Edge helpers
    def add_import_edge(self, src: str, dst: str):
        self.graph.add_edge(src, dst, type=EdgeType.IMPORTS.value)

    def add_calls_edge(self, src: str, dst: str):
        self.graph.add_edge(src, dst, type=EdgeType.CALLS.value)

    def add_defined_in_edge(self, src: str, dst: str):
        self.graph.add_edge(src, dst, type=EdgeType.DEFINED_IN.value)

    def add_consumes_edge(self, consumer: str, dataset: str):
        self.graph.add_edge(consumer, dataset, type=EdgeType.CONSUMES.value)

    def add_produces_edge(self, producer: str, dataset: str):
        self.graph.add_edge(producer, dataset, type=EdgeType.PRODUCES.value)

    def export_json(self) -> Dict[str, Any]:
        data = nx.node_link_data(self.graph)
        data["graph_kind"] = self.kind.value
        return data

    def to_json_str(self) -> str:
        return json.dumps(self.export_json(), indent=2)

    @classmethod
    def load_from_json(cls, payload: Dict[str, Any]) -> "KnowledgeGraph":
        kind = payload.get("graph_kind", "module")
        kg = cls(kind=kind)
        kg.graph = json_graph.node_link_graph(payload)
        return kg
