# File: src/agents/semanticist.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer

from src.utils.semantic_index import SemanticIndex
from src.utils.trace_logger import TraceLogger
from src.utils.llm_router import LLMRouter
from src.utils.token_budget import TokenBudget
from src.utils.semantic_prompts import PURPOSE_PROMPT, DRIFT_PROMPT, DAY_ONE_PROMPT


class Semanticist:
    """
    Semantic reasoning agent with business-domain clustering, docstring drift detection,
    and architecture summary.
    
    Capable of:
      - LLMs: Gemini 3 Flash / Ollama Llama 3.2 via Ollama
      - Deterministic fallback for offline analysis
    """

    def __init__(self, cartography_dir: Path, trace: Optional[TraceLogger] = None):
        self.cartography_dir = cartography_dir
        self.trace = trace

        self.index = SemanticIndex(cartography_dir / "semantic_index.json")
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

        self.token_budget = TokenBudget()
        self.llm_router = LLMRouter(self.token_budget)

    # ---------------------------------------------------------
    # ENTRYPOINT
    # ---------------------------------------------------------
    def analyze_modules(self, modules: List[Path]):
        purposes = {}
        for module in modules:
            result = self._analyze_module(module)
            purposes[str(module)] = result["purpose"]

        clusters = self._cluster_domains(purposes)
        domain_labels = self._label_domains(clusters)
        summary = self._generate_architecture_summary(purposes, domain_labels)

        self.index.set_clusters(domain_labels)
        self.index.set_summary(summary)
        self.index.save()

        if self.trace:
            self.trace.log(
                "Semanticist",
                "full_analysis_complete",
                analysis_method="LLM/deterministic",
                extra={"num_modules": len(modules), "summary": summary}
            )

    # ---------------------------------------------------------
    # MODULE ANALYSIS
    # ---------------------------------------------------------
    def _analyze_module(self, module_path: Path) -> Dict[str, Any]:
        code = module_path.read_text(encoding="utf-8")
        stripped = self._strip_docstrings(code)
        purpose = self._infer_purpose(stripped)
        drift = self._detect_docstring_drift(code)
        result = {"purpose": purpose, "docstring_drift": drift}

        self.index.update_module(str(module_path), result)

        if self.trace:
            self.trace.log(
                "Semanticist",
                "module_analyzed",
                evidence_source=str(module_path),
                extra=result
            )

        return result

    # ---------------------------------------------------------
    # PURPOSE INFERENCE (LLM-based)
    # ---------------------------------------------------------
    def _infer_purpose(self, code: str) -> str:
        try:
            prompt = PURPOSE_PROMPT.format(code=code)
            response = self.llm_router.generate(prompt, task="purpose")
            self.token_budget.record(len(response))  # record token usage

            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                data = {}

            return data.get("purpose", self._fallback_purpose(code))

        except Exception as e:
            if self.trace:
                self.trace.log(
                    "Semanticist",
                    "llm_purpose_failed",
                    extra={"error": str(e)}
                )
            return self._fallback_purpose(code)

    # ---------------------------------------------------------
    # PURPOSE INFERENCE (deterministic fallback)
    # ---------------------------------------------------------
    def _fallback_purpose(self, code: str) -> str:
        code_l = code.lower()

        if "networkx" in code_l:
            return "graph analytics module"
        if "sqlglot" in code_l or "select " in code_l:
            return "SQL parsing module"
        if "pandas" in code_l or "read_csv" in code_l:
            return "tabular data processing module"
        if "spark" in code_l:
            return "distributed processing module"
        if "typer" in code_l:
            return "CLI entrypoint module"

        return "general purpose module"

    # ---------------------------------------------------------
    # DOCSTRING DRIFT
    # ---------------------------------------------------------
    def _detect_docstring_drift(self, code: str) -> Dict[str, Any]:
        doc = self._extract_docstring(code)
        if not doc:
            return {"detected": False, "severity": "none"}

        impl_len = len(self._strip_docstrings(code))
        # deterministic fallback drift
        drift = {"detected": True, "severity": "low"} if len(doc) > 500 and impl_len < 100 else {"detected": False, "severity": "none"}

        # LLM-assisted drift detection
        try:
            prompt = DRIFT_PROMPT.format(docstring=doc, code=code)
            llm_drift = self.llm_router.generate(prompt, task="drift_check")
            self.token_budget.record(len(llm_drift))

            try:
                drift_json = json.loads(llm_drift)
                return drift_json
            except json.JSONDecodeError:
                return drift
        except Exception as e:
            if self.trace:
                self.trace.log(
                    "Semanticist",
                    "llm_drift_failed",
                    extra={"error": str(e)}
                )
            return drift

    # ---------------------------------------------------------
    # DOMAIN CLUSTERING
    # ---------------------------------------------------------
    def _cluster_domains(self, module_purposes: Dict[str, str]) -> Dict[str, List[str]]:
        modules = list(module_purposes.keys())
        texts = list(module_purposes.values())

        if len(texts) < 2:
            return {"domain_0": modules}

        embeddings = self.embedding_model.encode(texts)
        k = max(2, int(len(texts) ** 0.5))
        labels = KMeans(n_clusters=k, random_state=42).fit_predict(embeddings)

        clusters: Dict[str, List[str]] = {}
        for module, label in zip(modules, labels):
            clusters.setdefault(f"domain_{label}", []).append(module)
        return clusters

    # ---------------------------------------------------------
    # DOMAIN LABELING (LLM + fallback)
    # ---------------------------------------------------------
    def _label_domains(self, clusters: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
        labeled: Dict[str, Dict[str, Any]] = {}

        for domain, modules in clusters.items():
            purposes = [self.index.get_module(m)["purpose"] for m in modules if self.index.get_module(m)]

            if not purposes:
                label = "Miscellaneous"
            else:
                safe_code = "\n".join(purposes).replace("{", "{{").replace("}", "}}")
                try:
                    prompt = PURPOSE_PROMPT.format(code=safe_code)
                    label_json = self.llm_router.generate(prompt, task="purpose_label")
                    self.token_budget.record(len(label_json))
                    try:
                        label_dict = json.loads(label_json)
                        label = label_dict.get("purpose", "; ".join(set(purposes)))
                    except json.JSONDecodeError:
                        label = "; ".join(set(purposes))
                except Exception as e:
                    if self.trace:
                        self.trace.log(
                            "Semanticist",
                            "llm_label_failed",
                            extra={"error": str(e)}
                        )
                    label = "; ".join(set(purposes))

            labeled[domain] = {"modules": modules, "label": label}

        return labeled

    # ---------------------------------------------------------
    # DAY-ONE BRIEF
    # ---------------------------------------------------------
    def generate_day_one_brief(self, purposes: Dict[str, str], sources: list[str], sinks: list[str]) -> Dict[str, Any]:
        try:
            prompt = DAY_ONE_PROMPT.format(
                purposes=json.dumps(purposes, indent=2),
                sources=json.dumps(sources, indent=2),
                sinks=json.dumps(sinks, indent=2)
            )
            response = self.llm_router.generate(prompt, task="day_one")
            self.token_budget.record(len(response))

            try:
                result = json.loads(response)
            except json.JSONDecodeError:
                result = {}

            if self.trace:
                self.trace.log(
                    "Semanticist",
                    "day_one_generated",
                    analysis_method="LLM",
                    extra=result
                )

            return result
        except Exception as e:
            if self.trace:
                self.trace.log(
                    "Semanticist",
                    "day_one_fallback",
                    extra={"error": str(e)}
                )

            # deterministic fallback
            return {
                "system_purpose": "Data processing system",
                "critical_modules": list(purposes.keys())[:3],
                "recommended_reading_order": list(purposes.keys()),
                "data_flow_summary": f"Data flows from {sources} to {sinks}"
            }

    # ---------------------------------------------------------
    # ARCHITECTURE SUMMARY
    # ---------------------------------------------------------
    def _generate_architecture_summary(self, purposes: Dict[str, str], domains: Dict[str, Dict[str, Any]]) -> str:
        summary = []
        for dname, info in domains.items():
            label = info.get("label", dname)
            summary.append(f"- {label}: {len(info['modules'])} modules")
        return "\n".join(summary)

    # ---------------------------------------------------------
    # UTILITIES
    # ---------------------------------------------------------
    def _strip_docstrings(self, code: str) -> str:
        return re.sub(r'^\s*[ruRU]?("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')\s*', "", code, count=1)

    def _extract_docstring(self, code: str) -> str:
        m = re.match(r'^\s*[ruRU]?("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', code)
        return m.group(1) if m else ""