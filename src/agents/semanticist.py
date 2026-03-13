from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import re

from src.utils.logging_utils import get_logger
from src.utils.token_budget import TokenBudget
from src.utils.trace_logger import TraceLogger


@dataclass
class DriftResult:
    drift: bool
    severity: str
    explanation: str

    def to_dict(self) -> Dict:
        return {"drift": self.drift, "severity": self.severity, "explanation": self.explanation}


class Semanticist:
    """
    Semantic reasoning agent.

    In production, this can be backed by local Ollama or API models. For now, it provides
    deterministic, offline purpose inference and docstring drift checks.
    """

    def __init__(self, trace: Optional[TraceLogger] = None, budget: Optional[TokenBudget] = None):
        self.logger = get_logger(__name__)
        self.trace = trace
        self.budget = budget

    def infer_module_purpose(self, module_path: Path) -> Dict:
        code = module_path.read_text(encoding="utf-8", errors="ignore")
        purpose = self._infer_from_implementation(code)
        drift = self._docstring_drift(code, purpose)
        if self.trace:
            self.trace.log(
                "Semanticist",
                "infer_module_purpose",
                evidence_source=str(module_path),
                analysis_method="LLM",
                confidence=0.55,
                extra={"purpose_statement": purpose, "drift": drift.to_dict()},
            )
        return {"purpose_statement": purpose, "drift": drift.to_dict()}

    def _infer_from_implementation(self, code: str) -> str:
        # Explicitly ignore docstrings by removing top-level triple-quoted strings.
        stripped = re.sub(r'^\s*[ruRU]?("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')\s*', "", code, count=1)
        lowered = stripped.lower()
        signals = []
        if "sqlglot" in lowered or "select " in lowered:
            signals.append("SQL transformation or query execution")
        if "pandas" in lowered or ".to_sql" in lowered or "read_csv" in lowered:
            signals.append("tabular data ingestion/transformation")
        if "spark" in lowered or ".read." in lowered:
            signals.append("distributed data processing")
        if "typer" in lowered:
            signals.append("CLI entrypoint")
        if "networkx" in lowered or "pagerank" in lowered:
            signals.append("graph analytics")

        if not signals:
            return "General-purpose module; purpose unclear from implementation-only heuristics."
        return "; ".join(signals) + "."

    def _docstring_drift(self, code: str, purpose: str) -> DriftResult:
        doc = self._first_docstring(code)
        if not doc:
            return DriftResult(drift=False, severity="low", explanation="No docstring found.")
        doc_l = doc.lower()
        purpose_l = purpose.lower()
        overlap = sum(1 for w in ("sql", "data", "graph", "cli", "spark", "pandas") if w in doc_l and w in purpose_l)
        if overlap >= 2:
            return DriftResult(drift=False, severity="low", explanation="Docstring broadly matches inferred purpose.")
        return DriftResult(drift=True, severity="medium", explanation="Docstring may not reflect implementation intent.")

    def _first_docstring(self, code: str) -> Optional[str]:
        m = re.match(r'^\s*[ruRU]?("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', code)
        if not m:
            return None
        s = m.group(1)
        if s.startswith('"""') and s.endswith('"""'):
            return s[3:-3]
        if s.startswith("'''") and s.endswith("'''"):
            return s[3:-3]
        return None

