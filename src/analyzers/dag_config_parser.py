from pathlib import Path
from typing import Dict, List, Optional
import logging
import re

import yaml

from src.analyzers.sql_lineage import SQLLineageAnalyzer


class DbtProjectDetector:
    """Heuristic detector for dbt projects and lightweight metadata extraction."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def is_dbt_project(self) -> bool:
        return (self.repo_path / "dbt_project.yml").exists() and (self.repo_path / "models").exists()

    def list_models(self) -> List[str]:
        if not self.is_dbt_project():
            return []
        return [str(p.relative_to(self.repo_path)) for p in self.repo_path.rglob("models/**/*.sql")]

    def metadata(self) -> Dict:
        return {
            "is_dbt": self.is_dbt_project(),
            "models": self.list_models(),
        }


class DAGConfigParser:
    """
    Parses orchestration/config artifacts (Airflow DAGs, dbt schema.yml) to derive lineage hints.

    This is best-effort: it should never raise and should return an empty list if nothing is found.
    """

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.logger = logging.getLogger(__name__)
        self.sql = SQLLineageAnalyzer()

    def extract_lineage_events(self) -> List[Dict]:
        events: List[Dict] = []
        events.extend(self._extract_dbt_schema_events())
        events.extend(self._extract_airflow_events())
        return events

    def _extract_dbt_schema_events(self) -> List[Dict]:
        schema_files = list(self.repo_path.rglob("schema.yml")) + list(self.repo_path.rglob("schema.yaml"))
        out: List[Dict] = []
        for path in schema_files:
            try:
                text = path.read_text(encoding="utf-8")
                doc = yaml.safe_load(text) or {}
            except Exception as exc:
                self.logger.debug("Failed parsing dbt schema %s: %s", path, exc)
                continue

            line_count = text.count("\n") + 1 if text else 1
            rel_path = str(path.relative_to(self.repo_path))

            # Extract tests that reference other models via ref()
            refs = re.findall(r'ref\(["\']([\w\.\-]+)["\']\)', text)
            models = []
            if isinstance(doc, dict) and isinstance(doc.get("models"), list):
                for m in doc.get("models"):
                    if isinstance(m, dict) and "name" in m:
                        models.append(str(m["name"]))

            for model in models:
                if refs:
                    out.append(
                        {
                            "source_datasets": sorted(set(refs)),
                            "target_datasets": [model],
                            "transformation_type": "config",
                            "source_file": rel_path,
                            "line_range": [1, line_count],
                            "dynamic_reference": False,
                        }
                    )

            # Sources inventory (not direct dependencies, but useful nodes)
            if isinstance(doc, dict) and isinstance(doc.get("sources"), list):
                for src in doc.get("sources"):
                    if not isinstance(src, dict):
                        continue
                    src_name = src.get("name")
                    for table in src.get("tables") or []:
                        if isinstance(table, dict) and src_name and table.get("name"):
                            dataset = f"{src_name}.{table['name']}"
                            out.append(
                                {
                                    "source_datasets": [dataset],
                                    "target_datasets": [],
                                    "transformation_type": "config",
                                    "source_file": rel_path,
                                    "line_range": [1, line_count],
                                    "dynamic_reference": False,
                                }
                            )
        return out

    def _extract_airflow_events(self) -> List[Dict]:
        out: List[Dict] = []
        dag_files = list(self.repo_path.rglob("dags/**/*.py")) + list(self.repo_path.rglob("**/*dag*.py"))
        seen: set[str] = set()
        for path in dag_files:
            if str(path) in seen:
                continue
            seen.add(str(path))
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "DAG(" not in text and "airflow" not in text:
                continue

            rel_path = str(path.relative_to(self.repo_path))
            line_count = text.count("\n") + 1 if text else 1

            # Extremely simple heuristic: capture sql=... strings passed to operators.
            sql_literals = []
            for m in re.finditer(r"sql\s*=\s*([\"']{3})(.*?)(\\1)", text, flags=re.DOTALL):
                sql_literals.append(m.group(2))
            for m in re.finditer(r"sql\s*=\s*([\"'])(.*?)(\\1)", text):
                sql_literals.append(m.group(2))

            for sql in sql_literals[:50]:  # guardrail
                try:
                    sql2 = self.sql.preprocess_dbt(sql)
                    sources, targets = self.sql.parse_dependencies(sql2)
                except Exception as exc:
                    self.logger.debug("Airflow SQL parse fail in %s: %s", path, exc)
                    continue
                if not targets:
                    targets = {path.stem}
                out.append(
                    {
                        "source_datasets": sorted(sources),
                        "target_datasets": sorted(targets),
                        "transformation_type": "airflow",
                        "source_file": rel_path,
                        "line_range": [1, line_count],
                        "dynamic_reference": False,
                    }
                )
        return out
