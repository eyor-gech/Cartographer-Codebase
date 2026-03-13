from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class GraphCache:
    """Lightweight in-memory memoization for graph query results."""

    blast_radius_cache: Dict[str, List[str]] = field(default_factory=dict)

    def get(self, dataset: str) -> Optional[List[str]]:
        return self.blast_radius_cache.get(dataset)

    def set(self, dataset: str, downstream: List[str]) -> None:
        self.blast_radius_cache[dataset] = downstream

    def clear(self) -> None:
        self.blast_radius_cache.clear()

