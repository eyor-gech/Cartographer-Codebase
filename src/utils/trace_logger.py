from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class TraceLogger:
    """Append-only JSONL trace log for auditability across agents."""

    path: Path

    def log(
        self,
        agent_name: str,
        action: str,
        *,
        confidence: float = 0.7,
        evidence_source: str = "",
        analysis_method: str = "static",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_name": agent_name,
            "action": action,
            "confidence": float(confidence),
            "evidence_source": evidence_source,
            "analysis_method": analysis_method,
        }
        if extra:
            entry.update(extra)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

