from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional


class TraceLogger:
    """
    Append-only JSONL trace log used for auditing agent decisions.
    """

    def __init__(self, path: Path):

        self.path = path

        self.path.parent.mkdir(parents=True, exist_ok=True)

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
            "agent": agent_name,
            "action": action,
            "confidence": float(confidence),
            "evidence": evidence_source,
            "method": analysis_method,
        }

        if extra:
            entry.update(extra)

        with self.path.open("a", encoding="utf-8") as f:

            f.write(json.dumps(entry) + "\n")