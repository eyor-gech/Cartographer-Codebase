from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenBudget:
    model: str
    tokens_used: int = 0
    cost_estimate: float = 0.0
    hard_limit_tokens: int = 250_000

    def add_usage(self, tokens: int, cost: float = 0.0) -> None:
        self.tokens_used += int(tokens)
        self.cost_estimate += float(cost)
        if self.tokens_used > self.hard_limit_tokens:
            raise RuntimeError(f"Token budget exceeded: {self.tokens_used} > {self.hard_limit_tokens}")

