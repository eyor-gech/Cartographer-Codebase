from __future__ import annotations
from dataclasses import dataclass


@dataclass
class TokenBudget:
    tokens_used: int = 0
    hard_limit: int = 250_000
    soft_limit: int = 200_000

    cheap_model: str = "ollama"
    expensive_model: str = "gemini"

    def select_model(self, task: str) -> str:
        """
        Select which model to use depending on task importance
        and remaining token budget.
        """

        # If near token exhaustion use cheap model only
        if self.tokens_used > self.soft_limit:
            return self.cheap_model

        if task in {"purpose", "embedding"}:
            return self.cheap_model

        if task in {"synthesis", "day_one", "doc_drift"}:
            return self.expensive_model

        return self.cheap_model

    def record(self, tokens: int):
        self.tokens_used += tokens

        if self.tokens_used > self.hard_limit:
            raise RuntimeError("Token budget exceeded")