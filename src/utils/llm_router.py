from __future__ import annotations
import requests
from typing import Optional

from src.utils.token_budget import TokenBudget


class LLMRouter:

    def __init__(self, token_budget: TokenBudget):
        self.token_budget = token_budget

    def generate(self, prompt: str, task: str) -> str:
        model = self.token_budget.select_model(task)

        if model == "ollama":
            return self._call_ollama(prompt)

        if model == "gemini":
            return self._call_gemini(prompt)

        raise RuntimeError(f"Unknown model: {model}")

    # ---------------------------------------------------------
    # OLLAMA (LOCAL)
    # ---------------------------------------------------------
    def _call_ollama(self, prompt: str) -> str:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2",
                "prompt": prompt,
                "stream": False,
            },
        )

        result = response.json()["response"]

        # rough token estimate
        self.token_budget.record(len(prompt.split()) + len(result.split()))

        return result

    # ---------------------------------------------------------
    # GEMINI (CLOUD)
    # ---------------------------------------------------------
    def _call_gemini(self, prompt: str) -> str:
        # placeholder for API integration
        # future implementation can use google.generativeai

        raise NotImplementedError(
            "Gemini API integration placeholder — add your API key integration here"
        )