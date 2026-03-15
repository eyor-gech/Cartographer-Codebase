from __future__ import annotations
import os
import requests
import json
from typing import Optional, Tuple
from src.utils.token_budget import TokenBudget

class LLMRouter:
    def __init__(self, token_budget: TokenBudget):
        self.token_budget = token_budget
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.ollama_generate_url = f"{self.ollama_base_url}/api/generate"

        self.ollama_cheap_model = os.getenv("OLLAMA_CHEAP_MODEL", "llama3.2")
        # Optional; if unset, we fall back to the cheap model for "expensive" tier.
        self.ollama_expensive_model = os.getenv("OLLAMA_EXPENSIVE_MODEL", "") or self.ollama_cheap_model

        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_cheap_model = os.getenv("GEMINI_CHEAP_MODEL", "gemini-1.5-flash")
        self.gemini_expensive_model = os.getenv("GEMINI_EXPENSIVE_MODEL", "gemini-1.5-pro")

    def generate(self, prompt: str, task: str) -> str:
        tier = self.token_budget.select_tier(task)
        provider, model = self._select_provider_and_model(tier=tier)
        used_provider, used_model = provider, model

        raw = ""
        try:
            if provider == "gemini":
                raw = self._call_gemini(prompt, model_name=model)
            else:
                raw = self._call_ollama(prompt, model_name=model)
        except Exception as exc:
            # Deterministic fallback: try the other provider (if available), else return JSON error.
            try:
                alt_provider, alt_model = self._select_provider_and_model(tier=tier, prefer_other_than=provider)
                used_provider, used_model = alt_provider, alt_model
                if alt_provider == "gemini":
                    raw = self._call_gemini(prompt, model_name=alt_model)
                else:
                    raw = self._call_ollama(prompt, model_name=alt_model)
            except Exception as exc2:
                raw = json.dumps({"error": str(exc2), "fallback_error": str(exc), "provider": provider, "model": model})
                used_provider, used_model = provider, model

        clean = _scrub_markdown_fences(str(raw))
        token_estimate = _estimate_tokens(prompt) + _estimate_tokens(clean)
        # Cost estimation is intentionally conservative; local models are treated as $0.
        cost_estimate = 0.0 if used_provider == "ollama" else _estimate_gemini_cost_usd(token_estimate, tier=tier)
        self.token_budget.record(tokens=token_estimate, cost=cost_estimate)
        return clean.strip()

    def _select_provider_and_model(self, *, tier: str, prefer_other_than: str = "") -> Tuple[str, str]:
        """
        Prefer Gemini for expensive-tier synthesis when a key is available; otherwise Ollama.
        """
        if prefer_other_than == "gemini":
            return "ollama", self.ollama_expensive_model if tier == "expensive" else self.ollama_cheap_model
        if prefer_other_than == "ollama" and self.gemini_api_key:
            return "gemini", self.gemini_expensive_model if tier == "expensive" else self.gemini_cheap_model

        if tier == "expensive" and self.gemini_api_key:
            return "gemini", self.gemini_expensive_model
        return "ollama", self.ollama_cheap_model if tier == "cheap" else self.ollama_expensive_model

    def _call_ollama(self, prompt: str, model_name: str) -> str:
        """Caller for local/remote Ollama-compatible generate endpoints."""
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            # Best-effort structured output for Ollama; callers still scrub/parse defensively.
            "format": "json",
        }

        try:
            response = requests.post(self.ollama_generate_url, json=payload, timeout=60)
            response.raise_for_status()
            full_data = response.json()
            result = full_data.get("response", "")
            if isinstance(result, dict):
                return json.dumps(result)
            return str(result)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _call_gemini(self, prompt: str, model_name: str) -> str:
        """
        Minimal Gemini generateContent integration.

        Reads credentials from environment:
        - GEMINI_API_KEY
        """
        if not self.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        response = requests.post(url, params={"key": self.gemini_api_key}, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json() or {}
        # Best-effort extraction; if shape changes, we fall back to JSON stringifying the payload.
        try:
            candidates = data.get("candidates") or []
            if candidates:
                parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
                if parts and isinstance(parts[0], dict) and "text" in parts[0]:
                    return str(parts[0]["text"])
        except Exception:
            pass
        return json.dumps(data)


def _scrub_markdown_fences(text: str) -> str:
    clean = (text or "").replace("\u00a0", " ").strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        if len(lines) > 2:
            clean = "\n".join(lines[1:-1])
    # Also strip explicit ```json/``` wrappers if they appear mid-string.
    clean = clean.replace("```json", "").replace("```", "").strip()
    return clean


def _estimate_tokens(text: str) -> int:
    # Deterministic heuristic: words * 1.3
    words = len((text or "").split())
    return int(words * 1.3) + 1


def _estimate_gemini_cost_usd(tokens: int, *, tier: str) -> float:
    # Conservative placeholder: allow overriding via env without hardcoding provider pricing.
    env_key = "GEMINI_COST_USD_PER_1K_TOKENS_EXPENSIVE" if tier == "expensive" else "GEMINI_COST_USD_PER_1K_TOKENS_CHEAP"
    per_1k = float(os.getenv(env_key, "0.0") or "0.0")
    return (float(tokens) / 1000.0) * per_1k
