from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class SemanticIndex:
    """Persistent semantic analysis cache for Semanticist agent."""

    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, Any] = {
            "modules": {},
            "clusters": {},
            "day_one_brief": {}
        }

        if path.exists():
            self.data = json.loads(path.read_text())


    def update_module(self, module_path: str, info: Dict[str, Any]):

        self.data["modules"][module_path] = info

    def get_module(self, module_path: str) -> dict[str, Any] | None:
        """Retrieve info for a single module, or None if missing."""
        return self.data["modules"].get(module_path)


    def set_clusters(self, clusters):

        formatted = {}
        for k, v in clusters.items():
            formatted[f"domain_{k}"] = v

        self.data["clusters"] = formatted


    def set_day_one(self, summary):

        self.data["day_one_brief"] = summary


    def save(self):

        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.path.write_text(
            json.dumps(self.data, indent=2),
            encoding="utf-8"
        )
    def _label_domains(self, clusters: Dict[str, list[str]]) -> Dict[str, dict[str, Any]]:
        """
        Assign human-readable domain labels per cluster.
        Default deterministic fallback: join module purposes.
        """
        labeled: Dict[str, Dict[str, Any]] = {}
        for domain, modules in clusters.items():
            purposes = [
                self.index.data["modules"].get(m, {}).get("purpose")
                for m in modules
                if self.index.data["modules"].get(m)
            ]
            label = "; ".join(set(purposes)) if purposes else "Miscellaneous"
            labeled[domain] = {"modules": modules, "label": label}
        return labeled
    def set_summary(self, summary: str):
        """Store the architecture summary (for day-one brief)."""
        self.data["day_one_brief"] = summary

    @property
    def summary(self) -> str:
        """Return the stored day-one brief / architecture summary."""
        return self.data.get("day_one_brief", "")
    
    @property
    def clusters(self) -> dict:
        """Return the stored domain clusters."""
        return self.data.get("clusters", {})