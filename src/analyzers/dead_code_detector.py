from __future__ import annotations

from pathlib import Path
from typing import List

from src.graph.knowledge_graph import KnowledgeGraph


def detect_dead_code_candidates(module_graph: KnowledgeGraph) -> List[str]:
    """
    More conservative dead-code detector over the module import graph.

    Excludes obvious entrypoints and test modules. Returns a list of module node ids (paths).
    """
    g = module_graph.graph
    candidates: List[str] = []

    for node, attrs in g.nodes(data=True):
        if attrs.get("type") != "module":
            continue
        p = Path(node)
        name = p.name.lower()
        if name in ("cli.py", "__init__.py"):
            continue
        if "test" in p.parts or name.startswith("test_"):
            continue
        if node.endswith("__main__.py"):
            continue

        # If no other modules import it (in-degree == 0), it may be dead.
        # Keep compatibility with existing Surveyor flag when present.
        if attrs.get("is_dead_code_candidate") or g.in_degree(node) == 0:
            candidates.append(node)

    return sorted(set(candidates))

