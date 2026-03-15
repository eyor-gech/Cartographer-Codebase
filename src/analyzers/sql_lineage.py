from pathlib import Path
from typing import Dict, List, Set, Tuple
import logging
import re

try:
    import sqlglot  # type: ignore
    from sqlglot import expressions as exp  # type: ignore
except Exception:  # pragma: no cover
    sqlglot = None  # type: ignore[assignment]
    exp = None  # type: ignore[assignment]


class SQLLineageAnalyzer:
    """Uses sqlglot to derive dataset dependencies from SQL files."""

    DIALECTS = ["postgres", "bigquery", "snowflake", "duckdb"]

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    # ---------------------------------------------------------
    # DBT PREPROCESSING
    # ---------------------------------------------------------

    def preprocess_dbt(self, sql: str) -> str:
        """Convert dbt macros into plain SQL so parsers can understand them."""
        sql = re.sub(r"\{\{\s*ref\(['\"](.*?)['\"]\)\s*\}\}", r"\1", sql)
        sql = re.sub(
            r"\{\{\s*source\(['\"](.*?)['\"],\s*['\"](.*?)['\"]\)\s*\}\}",
            r"\1.\2",
            sql,
        )
        return sql

    # ---------------------------------------------------------
    # DEPENDENCY PARSING
    # ---------------------------------------------------------

    def parse_dependencies(self, sql: str) -> Tuple[Set[str], Set[str]]:
        sources: Set[str] = set()
        targets: Set[str] = set()
        ctes: Set[str] = set()

        # Extract dbt ref() dependencies
        for match in re.findall(r'ref\(["\']([\w\.\-]+)["\']\)', sql):
            sources.add(match)

        parsed = None

        if sqlglot is not None and exp is not None:
            for dialect in self.DIALECTS:
                try:
                    parsed = sqlglot.parse_one(sql, read=dialect, error_level="ignore")
                    if parsed:
                        break
                except Exception as exc:
                    self.logger.debug("sqlglot parse failed for dialect %s: %s", dialect, exc)

        if parsed is not None and exp is not None:
            # CTE names (avoid counting as physical reads)
            for cte in parsed.find_all(exp.CTE):
                name = cte.alias_or_name
                if name:
                    ctes.add(name)

            # Extract source tables
            for table in parsed.find_all(exp.Table):
                try:
                    if table.name and table.name not in ctes:
                        sources.add(table.name)
                except Exception:
                    continue

            # Detect INSERT targets
            insert = parsed.find(exp.Insert)
            if insert and insert.this:
                try:
                    targets.add(insert.this.name)
                except Exception:
                    pass

            # Detect CREATE TABLE targets
            create = parsed.find(exp.Create)
            if create and create.this:
                try:
                    targets.add(create.this.name)
                except Exception:
                    pass
        else:
            # Deterministic regex fallback when sqlglot is unavailable.
            for m in re.finditer(r"\\bwith\\s+([\\w\\.\\-`\\\"]+)\\s+as\\s*\\(", sql, flags=re.IGNORECASE):
                ctes.add(m.group(1).strip("`\""))
            for m in re.finditer(r"\\bfrom\\s+([\\w\\.\\-`\\\"]+)", sql, flags=re.IGNORECASE):
                t = m.group(1).strip("`\"")
                if t and t not in ctes:
                    sources.add(t)
            for m in re.finditer(r"\\bjoin\\s+([\\w\\.\\-`\\\"]+)", sql, flags=re.IGNORECASE):
                t = m.group(1).strip("`\"")
                if t and t not in ctes:
                    sources.add(t)
            for m in re.finditer(r"\\binsert\\s+into\\s+([\\w\\.\\-`\\\"]+)", sql, flags=re.IGNORECASE):
                targets.add(m.group(1).strip("`\""))
            for m in re.finditer(r"\\bcreate\\s+table\\s+([\\w\\.\\-`\\\"]+)", sql, flags=re.IGNORECASE):
                targets.add(m.group(1).strip("`\""))

        return sources, targets

    # ---------------------------------------------------------
    # FILE ANALYSIS
    # ---------------------------------------------------------

    def analyze_file(self, path: Path) -> Dict[str, List[str]]:
        try:
            sql = path.read_text(encoding="utf-8")
        except Exception as exc:
            self.logger.error("Failed reading SQL file %s: %s", path, exc)
            return {}

        try:
            sql = self.preprocess_dbt(sql)
            sources, targets = self.parse_dependencies(sql)
        except Exception as exc:
            self.logger.error("SQL lineage parse failure for %s: %s", path, exc)
            return {}

        # dbt models often have implicit targets
        if not targets:
            targets = {path.stem}

        line_count = sql.count("\n") + 1 if sql else 1
        return {
            "source_tables": sorted(sources),
            "target_tables": sorted(targets),
            "source_file": str(path),
            "line_range": [1, line_count],
            # Backward compatibility keys (older callers)
            "sources": sorted(sources),
            "targets": sorted(targets),
        }
