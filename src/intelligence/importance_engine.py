from typing import Dict, List
import networkx as nx

from src.graph.knowledge_graph import KnowledgeGraph
from src.utils.logging_utils import get_logger


class ImportanceEngine:
    """Combines graph centrality and git change velocity to find hotspots."""

    def __init__(self, module_graph: KnowledgeGraph, change_velocity: Dict[str, int]):
        self.graph = module_graph
        self.change_velocity = change_velocity or {}
        self.logger = get_logger(__name__)

    def compute_signals(self) -> Dict:
        g = self.graph.graph
        if g.number_of_nodes() == 0:
            return {}

        pagerank = nx.pagerank(g) if g.number_of_edges() > 0 else {n: 0.0 for n in g.nodes}
        betweenness = nx.betweenness_centrality(g) if g.number_of_edges() > 0 else {n: 0.0 for n in g.nodes}
        max_vel = max(self.change_velocity.values()) if self.change_velocity else 1

        critical: List[Dict] = []
        risk: List[Dict] = []
        dead: List[str] = []

        for node in g.nodes:
            pr = pagerank.get(node, 0.0)
            bt = betweenness.get(node, 0.0)
            vel_raw = self.change_velocity.get(node, 0)
            vel_norm = vel_raw / max_vel if max_vel else 0
            importance_score = 0.5 * pr + 0.3 * bt + 0.2 * vel_norm

            attrs = g.nodes[node]
            attrs["pagerank"] = pr
            attrs["betweenness"] = bt
            attrs["change_velocity_30d"] = vel_raw
            attrs["importance_score"] = importance_score

            record = {
                #"module": node,
                "node": node,
                "pagerank": pr,
                "betweenness": bt,
                "change_velocity": vel_raw,
                "importance_score": importance_score,
            }
            critical.append(record)
            if pr > 0.05 and vel_norm > 0.3:
                risk.append(record)
            if attrs.get("is_dead_code_candidate"):
                dead.append(node)

        # sort by importance
        critical_sorted = sorted(critical, key=lambda x: x["importance_score"], reverse=True)[:25]
        risk_sorted = sorted(risk, key=lambda x: x["importance_score"], reverse=True)[:25]

        signals = {
            "critical_modules": critical_sorted,
            "risk_modules": risk_sorted,
            "dead_code_candidates": dead,
        }
        # self.logger.info("Importance engine computed signals for %d modules", len(critical_sorted))
        self.logger.info(
            "Importance engine computed signals for %d graph nodes", len(critical_sorted)
        )
        return signals
