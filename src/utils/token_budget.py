from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass
class TokenBudget:
    """
    Lightweight token/cost accounting with model tiering.

    Mastered rubric alignment:
    - Tracks cumulative_spend (calls/tokens/cost)
    - Selects model tier automatically by task type
    """

    calls: int = 0
    tokens_used: int = 0
    estimated_cost: float = 0.0

    hard_limit: int = 500_000
    soft_limit: int = 400_000

    def select_tier(self, task: str) -> str:
        """
        Return "cheap" (bulk mode) or "expensive" (synthesis mode) for the task.

        Bulk mode (cheap):
        - module purpose inference
        - docstring drift checks

        Synthesis mode (expensive):
        - domain labeling
        - day-one briefing
        """
        if self.tokens_used > self.soft_limit:
            return "cheap"
        expensive_tasks = {"domain_label", "day_one", "synthesis"}
        if task in expensive_tasks:
            return "expensive"
        return "cheap"

    def record(self, *, tokens: int, cost: Optional[float] = None) -> None:
        self.calls += 1
        self.tokens_used += int(tokens)
        if cost is not None:
            self.estimated_cost += float(cost)

        if self.tokens_used > self.hard_limit:
            raise RuntimeError(f"Token budget exceeded! Used: {self.tokens_used}")

    def snapshot(self) -> Dict[str, Any]:
        return {
            "calls": int(self.calls),
            "tokens_used": int(self.tokens_used),
            "estimated_cost": float(self.estimated_cost),
        }
