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

    def parse_dependencies(self, sql: str) -> Tuple[Set[str], Set[str]]:
        sources: Set[str] = set()
        targets: Set[str] = set()

        # dbt ref() macro extraction
        for match in re.findall(r'ref\(["\']([\w\.\-]+)["\']\)', sql):
            sources.add(match)

        parsed = None
        for dialect in self.DIALECTS:
            try:
                parsed = sqlglot.parse_one(sql, read=dialect, error_level="ignore")
                if parsed:
                    break
            except Exception as exc:
                self.logger.debug("sqlglot parse failed for dialect %s: %s", dialect, exc)
        if not parsed:
            return sources, targets

        for table in parsed.find_all(exp.Table):
            if table.this:
                sources.add(table.this.sql())

        for cte in parsed.find_all(exp.CTE):
            if isinstance(cte.this, exp.Table):
                targets.add(cte.this.this.sql())

        insert = parsed.find(exp.Insert)
        if insert and insert.this:
            targets.add(insert.this.sql())
        create = parsed.find(exp.Create)
        if create and create.this:
            targets.add(create.this.sql())
        return sources, targets

    def analyze_file(self, path: Path) -> Dict[str, List[str]]:
        try:
            sql = path.read_text(encoding="utf-8")
        except Exception as exc:
            self.logger.error("Failed reading SQL file %s: %s", path, exc)
            return {}
        try:
            sources, targets = self.parse_dependencies(sql)
        except Exception as exc:
            self.logger.error("SQL lineage parse failure for %s: %s", path, exc)
            return {}
        return {
            "source_tables": sorted(sources),
            "target_tables": sorted(targets) if targets else [path.name],
            "source_file": str(path),
            "line_range": None,
        }
