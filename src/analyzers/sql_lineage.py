from pathlib import Path
from typing import Dict, List, Set, Tuple
import logging
import re

import sqlglot
from sqlglot import expressions as exp


class SQLLineageAnalyzer:
    """Uses sqlglot to derive dataset dependencies from SQL files."""

    DIALECTS = ["postgres", "bigquery", "snowflake"]

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

        # Extract dbt ref() dependencies
        for match in re.findall(r'ref\(["\']([\w\.\-]+)["\']\)', sql):
            sources.add(match)

        parsed = None

        for dialect in self.DIALECTS:
            try:
                parsed = sqlglot.parse_one(sql, read=dialect, error_level="ignore")
                if parsed:
                    break
            except Exception as exc:
                self.logger.debug(
                    "sqlglot parse failed for dialect %s: %s", dialect, exc
                )

        if not parsed:
            return sources, targets

        # Extract source tables
        for table in parsed.find_all(exp.Table):
            try:
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

        return {
            "source_tables": sorted(sources),
            "target_tables": sorted(targets),
            "source_file": str(path),
            "line_range": None,
        }