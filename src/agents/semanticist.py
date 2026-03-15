# File: src/agents/semanticist.py
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore[assignment]

from src.graph.knowledge_graph import KnowledgeGraph
from src.utils.semantic_index import SemanticIndex
from src.utils.trace_logger import TraceLogger
from src.utils.llm_router import LLMRouter
from src.utils.token_budget import TokenBudget
from src.utils.semantic_prompts import PURPOSE_PROMPT, DRIFT_PROMPT, DOMAIN_LABEL_PROMPT
from src.utils.deterministic_semantics import infer_purpose_from_code


class Semanticist:
    def __init__(self, cartography_dir: Path, repo_root: Optional[Path] = None, trace: Optional[TraceLogger] = None):
        self.cartography_dir = cartography_dir
        self.repo_root = repo_root
        self.trace = trace

        self.index = SemanticIndex(cartography_dir / "semantic_index.json")

        self.embedding_model = None
        if SentenceTransformer is not None:
            try:
                self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                self.embedding_model = None

        self.token_budget = TokenBudget()
        self.llm_router = LLMRouter(self.token_budget)

    def analyze_modules(self, modules: List[Path]) -> None:
        purposes: Dict[str, str] = {}
        for module in modules:
            result = self._analyze_module(module)
            purposes[result["module_path"]] = result["purpose"]

        clusters = self._cluster_domains(purposes)
        domain_labels = self._label_domains(clusters)
        summary = self._generate_architecture_summary(domain_labels)

        self.index.set_clusters(domain_labels)
        self.index.set_summary(summary)
        self.index.set_token_budget(self.token_budget.snapshot())
        self.index.save()

        if self.trace:
            self.trace.log(
                "Semanticist",
                "full_analysis_complete",
                analysis_method="LLM/deterministic",
                extra={"num_modules": len(modules), "summary": summary, "token_budget": self.token_budget.snapshot()},
            )

    def synthesize_day_one_questions(
        self,
        *,
        module_graph: KnowledgeGraph,
        lineage_graph: KnowledgeGraph,
        architecture_signals: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Answer five Day-1 questions by combining Surveyor (module graph) + Hydrologist (lineage graph).
        Results are structured and include citations.
        """
        architecture_signals = architecture_signals or {}
        critical = [
            (item.get("module") or item.get("node"))
            for item in (architecture_signals.get("critical_modules") or [])
            if (item.get("module") or item.get("node"))
        ]
        critical = [c for c in critical if isinstance(c, str)]
        critical = critical[:10] if critical else self._top_modules_by_importance(module_graph, limit=10)

        sources = _dataset_sources(lineage_graph)[:10]
        sinks = _dataset_sinks(lineage_graph)[:10]

        q = []
        q.append(
            {
                "question": "What is the system's primary objective?",
                "answer": self._system_objective_answer(critical=critical, sources=sources, sinks=sinks),
                "citations": [f"{m}:1" for m in critical[:3]],
            }
        )
        q.append(
            {
                "question": "What is the critical execution path (where should I start reading)?",
                "answer": "Start with the CLI/orchestrator, then follow the most-connected modules: "
                + ", ".join(critical[:5]),
                "citations": [f"{m}:1" for m in critical[:5]],
            }
        )
        q.append(
            {
                "question": "What are the primary data sources and sinks?",
                "answer": "Sources: "
                + ", ".join(sources or ["(none detected)"])
                + ". Sinks: "
                + ", ".join(sinks or ["(none detected)"])
                + ".",
                "citations": _cite_datasets(lineage_graph, (sources or []) + (sinks or []))[:10],
            }
        )
        q.append(
            {
                "question": "Which files are highest risk to change?",
                "answer": "Highest-risk files are high-velocity and central modules: " + ", ".join(critical[:8]),
                "citations": [f"{m}:1" for m in critical[:8]],
            }
        )
        q.append(
            {
                "question": "If I change a dataset, what else breaks?",
                "answer": "Use the lineage blast radius to see downstream datasets; start from key sinks like: "
                + ", ".join(sinks[:3] or sources[:3] or []),
                "citations": _cite_datasets(lineage_graph, (sinks[:3] or sources[:3] or [])),
            }
        )

        payload = {"questions": q}
        self.index.set_day_one(payload)
        self.index.save()

        if self.trace:
            self.trace.log(
                "Semanticist",
                "day_one_synthesized",
                analysis_method="static/LLM",
                extra={"questions": len(q)},
            )
        return payload

    def infer_module_purpose(self, module_path: Path) -> Dict[str, Any]:
        return self._analyze_module(module_path)

    def _analyze_module(self, module_path: Path) -> Dict[str, Any]:
        code = module_path.read_text(encoding="utf-8", errors="ignore")
        doc = self._extract_docstring(code)
        signals, evidence_list = self._extract_implementation_signals(code, module_path=module_path)

        purpose = self._infer_purpose(signals)
        drift = self._detect_docstring_drift(module_path=module_path, docstring=doc, purpose=purpose, evidence_list=evidence_list)

        key = self._module_key(module_path)
        result = {"module_path": key, "purpose": purpose, "docstring_drift": drift}

        self.index.update_module(key, {"purpose": purpose, "docstring_drift": drift})
        emb = self._embed_texts([purpose])[0]
        if emb:
            self.index.set_module_embedding(key, emb)

        if self.trace:
            self.trace.log("Semanticist", "module_analyzed", evidence_source=key, analysis_method="LLM", extra=result)

        return result

    def _infer_purpose(self, signals: Dict[str, str]) -> str:
        if not signals or all(not (v or "").strip() for v in signals.values()):
            return "utility module (insufficient implementation evidence for analysis)"

        prompt = PURPOSE_PROMPT.format(
            imports=signals.get("imports", "(none)"),
            signatures=signals.get("signatures", "(none)"),
            io_operations=signals.get("io_operations", "(none)"),
            control_flow=signals.get("control_flow", "(none)"),
        )

        raw_response = ""
        try:
            raw_response = self.llm_router.generate(prompt, task="purpose")
            
            data = self._extract_json(raw_response)
            if isinstance(data, dict) and isinstance(data.get("purpose"), str) and data["purpose"].strip():
                return data["purpose"].strip()
        except Exception as exc:
            if self.trace:
                self.trace.log("Semanticist", "llm_purpose_failed", analysis_method="LLM", extra={"error": str(exc), "raw": raw_response[:200]})

        return self._fallback_purpose(signals)

    def _fallback_purpose(self, signals: Dict[str, str]) -> str:
        blob = "\n".join((signals.get("imports", ""), signals.get("signatures", ""), signals.get("io_operations", ""))).lower()
        return infer_purpose_from_code(blob)

    def _detect_docstring_drift(
        self,
        *,
        module_path: Path,
        docstring: str,
        purpose: str,
        evidence_list: List[str],
    ) -> Dict[str, Any]:
        if not docstring:
            return {"detected": False, "severity": "low", "contradictions": []}

        prompt = DRIFT_PROMPT.format(
            module_path=self._module_key(module_path),
            docstring=docstring,
            purpose=purpose,
            evidence_list="\n".join(evidence_list) if evidence_list else f"{self._module_key(module_path)}:1",
        )
        raw = ""
        try:
            raw = self.llm_router.generate(prompt, task="drift_check")
            data = self._extract_json(raw)
            if isinstance(data, dict):
                return {
                    "detected": bool(data.get("detected", False)),
                    "severity": str(data.get("severity") or "low"),
                    "contradictions": data.get("contradictions") if isinstance(data.get("contradictions"), list) else [],
                }
        except Exception as exc:
            if self.trace:
                self.trace.log("Semanticist", "llm_drift_failed", analysis_method="LLM", extra={"error": str(exc), "raw": raw[:200]})
        return {"detected": False, "severity": "low", "contradictions": []}

    def _cluster_domains(self, module_purposes: Dict[str, str]) -> Dict[str, List[str]]:
        modules = list(module_purposes.keys())
        texts = [module_purposes[m] for m in modules]
        if len(texts) < 2:
            return {"domain_0": modules}

        vectors = self._embed_texts(texts)
        k = max(2, int(len(texts) ** 0.5))
        k = min(k, len(texts))
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(vectors)

        clusters: Dict[str, List[str]] = {}
        for module, label in zip(modules, labels):
            clusters.setdefault(f"domain_{label}", []).append(module)
        return clusters

    def _label_domains(self, clusters: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
        labeled: Dict[str, Dict[str, Any]] = {}
        for domain, modules in clusters.items():
            purposes = [
                (self.index.get_module(m) or {}).get("purpose", "")
                for m in modules
                if self.index.get_module(m)
            ]
            purposes = [p for p in purposes if p]

            label = ""
            if purposes:
                try:
                    prompt = DOMAIN_LABEL_PROMPT.format(purposes="\n".join(purposes[:25]))
                    raw = self.llm_router.generate(prompt, task="domain_label")
                    data = self._extract_json(raw)
                    if isinstance(data, dict):
                        label = str(data.get("label") or "").strip()
                except Exception:
                    label = ""

            if not label:
                label = self._keyword_domain_label(purposes, modules)

            labeled[domain] = {"modules": modules, "label": label}
        return labeled

    def _generate_architecture_summary(self, domains: Dict[str, Dict[str, Any]]) -> str:
        lines: List[str] = []
        for dname, info in domains.items():
            label = info.get("label", dname)
            lines.append(f"- {label}: {len(info.get('modules') or [])} modules")
        return "\n".join(lines)

    def _module_key(self, module_path: Path) -> str:
        if self.repo_root:
            try:
                return str(module_path.relative_to(self.repo_root))
            except Exception:
                return str(module_path)
        return str(module_path)

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        texts = [t or "" for t in texts]
        if self.embedding_model is not None:
            try:
                vecs = self.embedding_model.encode(texts)
                return [list(map(float, v)) for v in vecs]
            except Exception:
                pass
        vect = TfidfVectorizer(max_features=512, stop_words="english")
        mat = vect.fit_transform(texts).toarray()
        return [list(map(float, row)) for row in mat]

    def _keyword_domain_label(self, purposes: List[str], modules: List[str]) -> str:
        text = " ".join(purposes) if purposes else " ".join(modules)
        vect = TfidfVectorizer(stop_words="english", max_features=32)
        top: List[str] = []
        try:
            mat = vect.fit_transform([text]).toarray()[0]
            terms = list(vect.get_feature_names_out())
            scored = sorted(zip(terms, mat), key=lambda t: t[1], reverse=True)
            top = [t for t, s in scored[:3] if s > 0][:3]
        except Exception:
            top = []
        if not top:
            digest = abs(hash(text)) % 10_000
            return f"Domain {digest}"
        return " ".join(w.title() for w in top[:2])

    def _extract_docstring(self, code: str) -> str:
        m = re.match(r'^\s*[ruRU]?("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', code)
        return m.group(1) if m else ""

    def _extract_implementation_signals(self, code: str, *, module_path: Path) -> Tuple[Dict[str, str], List[str]]:
        imports: List[str] = []
        signatures: List[str] = []
        io_ops: List[str] = []
        evidence: List[str] = []
        control = {"if": 0, "for": 0, "while": 0, "try": 0, "with": 0}

        try:
            tree = ast.parse(code)
        except Exception:
            key = self._module_key(module_path)
            return {"imports": "(unparsed)", "signatures": "(unparsed)", "io_operations": "(unparsed)", "control_flow": "(unparsed)"}, [f"{key}:1"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imports.append(f"import {a.name}" + (f" as {a.asname}" if a.asname else ""))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = ", ".join(a.name for a in node.names)
                imports.append(f"from {mod} import {names}".strip())
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                line = getattr(node, "lineno", 1) or 1
                signatures.append(f"def {node.name}({', '.join(args)})  (line {line})")
                evidence.append(f"{self._module_key(module_path)}:{line}")
            elif isinstance(node, ast.ClassDef):
                line = getattr(node, "lineno", 1) or 1
                signatures.append(f"class {node.name}  (line {line})")
                evidence.append(f"{self._module_key(module_path)}:{line}")
            elif isinstance(node, ast.If):
                control["if"] += 1
            elif isinstance(node, ast.For):
                control["for"] += 1
            elif isinstance(node, ast.While):
                control["while"] += 1
            elif isinstance(node, ast.Try):
                control["try"] += 1
            elif isinstance(node, ast.With):
                control["with"] += 1
            elif isinstance(node, ast.Call):
                name = _ast_dotted_name(node.func)
                if not name:
                    continue
                if name == "open" or name.endswith((".read_csv", ".read_parquet", ".read_sql", ".to_sql", ".to_parquet")) or name.startswith("spark.read") or ".write." in name or name.endswith(".execute"):
                    line = getattr(node, "lineno", 1) or 1
                    io_ops.append(f"{name}  (line {line})")
                    evidence.append(f"{self._module_key(module_path)}:{line}")

        imports_s = "\n".join(sorted(set(imports))[:80]) or "(none)"
        sig_s = "\n".join(signatures[:120]) or "(none)"
        io_s = "\n".join(io_ops[:120]) or "(none)"
        control_s = ", ".join(f"{k}={v}" for k, v in control.items()) or "(none)"

        ev = sorted(set(evidence))[:200] if evidence else [f"{self._module_key(module_path)}:1"]
        return {"imports": imports_s, "signatures": sig_s, "io_operations": io_s, "control_flow": control_s}, ev

    def _top_modules_by_importance(self, module_graph: KnowledgeGraph, *, limit: int) -> List[str]:
        g = module_graph.graph
        scored = []
        for n, a in g.nodes(data=True):
            if a.get("type") != "module":
                continue
            scored.append((n, float(a.get("importance_score") or a.get("pagerank") or 0.0)))
        scored.sort(key=lambda t: t[1], reverse=True)
        return [n for n, _ in scored[: max(1, int(limit))]]

    def _system_objective_answer(self, *, critical: List[str], sources: List[str], sinks: List[str]) -> str:
        parts = []
        if sources:
            parts.append(f"ingests data from {', '.join(sources[:3])}")
        if sinks:
            parts.append(f"produces outputs to {', '.join(sinks[:3])}")
        if critical:
            parts.append(f"centered around modules like {', '.join(critical[:3])}")
        return "The system appears to be a data pipeline that " + ("; ".join(parts) if parts else "connects modules and datasets discovered by static analysis.") + "."

    def _extract_json(self, text: str) -> Dict[str, Any]:
        if not text or not isinstance(text, str):
            return {}
        text = text.replace("\u00a0", " ").strip()
        match = re.search(r"(\\{.*\\})", text, re.DOTALL)
        if match:
            blob = match.group(1)
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                clean = re.sub(r"```json|```", "", blob).strip()
                try:
                    return json.loads(clean)
                except Exception:
                    return {}
        return {}


def _ast_dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _ast_dotted_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def _dataset_sources(lineage_graph: KnowledgeGraph) -> List[str]:
    g = lineage_graph.graph
    out: List[str] = []
    for n, a in g.nodes(data=True):
        if a.get("type") != "dataset":
            continue
        produced = any(g.edges[p, n].get("type") == "produces" for p in g.predecessors(n))
        if not produced:
            out.append(n)
    return sorted(out)


def _dataset_sinks(lineage_graph: KnowledgeGraph) -> List[str]:
    g = lineage_graph.graph
    out: List[str] = []
    for n, a in g.nodes(data=True):
        if a.get("type") != "dataset":
            continue
        consumed = any(g.edges[p, n].get("type") == "consumes" for p in g.predecessors(n))
        if not consumed:
            out.append(n)
    return sorted(out)


def _cite_datasets(lineage_graph: KnowledgeGraph, datasets: List[str]) -> List[str]:
    g = lineage_graph.graph
    citations: List[str] = []
    for ds in datasets:
        if ds not in g:
            continue
        for pred in g.predecessors(ds):
            if g.nodes[pred].get("type") != "transformation":
                continue
            sf = g.edges[pred, ds].get("source_file") or g.nodes[pred].get("source_file")
            lr = g.edges[pred, ds].get("line_range") or g.nodes[pred].get("line_range") or [1, 1]
            if sf:
                citations.append(f"{sf}:{int(lr[0] if isinstance(lr, list) and lr else 1)}")
                break
    return citations
