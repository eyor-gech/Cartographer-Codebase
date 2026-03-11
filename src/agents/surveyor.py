from pathlib import Path
from typing import Dict, List
import os
import networkx as nx

from src.analyzers.tree_sitter_analyzer import TreeSitterAnalyzer
from src.graph.knowledge_graph import KnowledgeGraph
from src.models.nodes import ModuleNode
from src.utils.git_utils import change_velocity_last_30d
from src.utils.logging_utils import get_logger


class Surveyor:
    """Builds structural module graph using Tree-sitter and git signals."""

    def __init__(self, repo_path: Path, graph: KnowledgeGraph):
        self.repo_path = repo_path
        self.graph = graph
        self.analyzer = TreeSitterAnalyzer()
        self.logger = get_logger(__name__)
        self.git_change_velocity: Dict[str, int] = {}

    def analyze(self):
        self.logger.info("Surveyor scanning repository for Python modules")
        self.git_change_velocity = change_velocity_last_30d(self.repo_path)

        module_exports: Dict[str, List[str]] = {}
        module_import_targets: Dict[str, List[str]] = {}

        for path in self.repo_path.rglob("*.py"):
            try:
                rel = str(path.relative_to(self.repo_path))
                analysis = self.analyzer.analyze(path)

                imports = analysis.get("imports", [])
                functions = analysis.get("functions", [])
                classes = analysis.get("classes", [])

                module_exports[rel] = functions + classes
                module_import_targets[rel] = imports

                velocity = self.git_change_velocity.get(rel, 0)
                stat = path.stat()

                node = ModuleNode(
                    path=rel,
                    language="python",
                    complexity_score=len(functions) + len(classes) + len(imports),
                    change_velocity_30d=velocity,
                    last_modified=str(stat.st_mtime),
                )

                self.graph.add_module_node(rel, **node.model_dump())

            except Exception as exc:
                self.logger.error("Surveyor failed processing %s: %s", path, exc)
                continue

        # build import edges
        for src, imports in module_import_targets.items():
            for imp in imports:
                target = self._resolve_import_to_module(imp, module_import_targets.keys())
                if target:
                    self.graph.add_import_edge(src, target)

        # architectural signals
        self._mark_dead_code(module_exports, module_import_targets)
        self._mark_cycles()
        self._mark_high_velocity_modules()

        # compute graph centrality
        self._compute_centrality()

    def _resolve_import_to_module(self, import_stmt: str, known_modules) -> str:
        candidates = []
        for mod in known_modules:
            mod_dot = mod.replace(os.sep, ".").rstrip(".py")
            if mod_dot in import_stmt:
                candidates.append(mod)
        return candidates[0] if candidates else ""

    def _mark_dead_code(self, exports: Dict[str, List[str]], imports: Dict[str, List[str]]):
        imported_modules = set()
        for imp_list in imports.values():
            for imp in imp_list:
                for module in exports.keys():
                    mod_dot = module.replace(os.sep, ".").rstrip(".py")
                    if mod_dot in imp:
                        imported_modules.add(module)

        for module, symbols in exports.items():
            if symbols and module not in imported_modules:
                if module in self.graph.graph.nodes:
                    self.graph.graph.nodes[module]["is_dead_code_candidate"] = True

    def _mark_cycles(self):
        g = self.graph.graph
        cycles = [c for c in nx.strongly_connected_components(g) if len(c) > 1]
        for component in cycles:
            for node in component:
                if node in g.nodes:
                    g.nodes[node]["in_cycle"] = True

    def _mark_high_velocity_modules(self):
        if not self.git_change_velocity:
            return
        velocities = list(self.git_change_velocity.values())
        if not velocities:
            return
        threshold_index = max(0, int(len(velocities) * 0.8) - 1)
        sorted_vel = sorted(velocities)
        threshold = sorted_vel[threshold_index]
        g = self.graph.graph
        for module, vel in self.git_change_velocity.items():
            if vel >= threshold and module in g.nodes:
                g.nodes[module]["high_velocity"] = True
    
    # Centrality Function
    def _compute_centrality(self):
        g = self.graph.graph

        if len(g.nodes) == 0:
            return

        pagerank = nx.pagerank(g)
        betweenness = nx.betweenness_centrality(g)

        for node in g.nodes:
            g.nodes[node]["pagerank"] = pagerank.get(node, 0.0)
            g.nodes[node]["betweenness"] = betweenness.get(node, 0.0)
