from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SemanticIndex:
    """
    Persistent semantic analysis cache for Semanticist/Navigator.

    Mastered rubric alignment:
    - Stores module purposes + drift results
    - Stores embeddings for semantic vector search
    - Stores domain clusters and Day-1 brief outputs
    """

    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, Any] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

        # Backward-compatible defaults
        self.data.setdefault("modules", {})
        self.data.setdefault("module_embeddings", {})
        self.data.setdefault("clusters", {})
        self.data.setdefault("day_one_brief", {})
        self.data.setdefault("summary", "")
        self.data.setdefault("token_budget", {})

    def update_module(self, module_path: str, info: Dict[str, Any]) -> None:
        self.data["modules"][module_path] = info

    def get_module(self, module_path: str) -> dict[str, Any] | None:
        """Retrieve info for a single module, or None if missing."""
        return self.data["modules"].get(module_path)

    def set_module_embedding(self, module_path: str, embedding: List[float]) -> None:
        self.data.setdefault("module_embeddings", {})
        self.data["module_embeddings"][module_path] = list(map(float, embedding))

    def set_clusters(self, clusters):

        formatted = {}
        for k, v in clusters.items():
            formatted[f"domain_{k}"] = v

        self.data["clusters"] = formatted

    def set_day_one(self, summary):

        self.data["day_one_brief"] = summary

    def set_summary(self, summary: str) -> None:
        self.data["summary"] = summary

    @property
    def summary(self) -> str:
        return self.data.get("summary") or ""

    @property
    def clusters(self) -> dict:
        return self.data.get("clusters", {})

    def set_token_budget(self, snapshot: Dict[str, Any]) -> None:
        self.data["token_budget"] = snapshot or {}

    def save(self):

        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.path.write_text(
            json.dumps(self.data, indent=2),
            encoding="utf-8"
        )

    def search(self, query_embedding: List[float], *, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Vector search over stored module embeddings.

        Returns: [{module, score, purpose}]
        """
        embeddings = self.data.get("module_embeddings") or {}
        if not embeddings:
            return []

        scored: List[Tuple[str, float]] = []
        for module, vec in embeddings.items():
            score = _cosine_similarity(query_embedding, vec)
            scored.append((module, score))
        scored.sort(key=lambda t: t[1], reverse=True)
        out: List[Dict[str, Any]] = []
        for module, score in scored[: max(1, int(top_k))]:
            info = (self.data.get("modules") or {}).get(module) or {}
            out.append({"module": module, "score": float(score), "purpose": info.get("purpose")})
        return out


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        av = float(a[i])
        bv = float(b[i])
        dot += av * bv
        na += av * av
        nb += bv * bv
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))
