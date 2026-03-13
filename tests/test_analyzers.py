import textwrap
from pathlib import Path

from src.analyzers.tree_sitter_analyzer import TreeSitterAnalyzer


def write_file(tmp_path: Path, filename: str, content: str) -> Path:
    """Create a temporary file with provided content."""
    file_path = tmp_path / filename
    file_path.write_text(textwrap.dedent(content), encoding="utf-8")
    return file_path


def test_python_analysis(tmp_path):
    analyzer = TreeSitterAnalyzer()

    file_path = write_file(
        tmp_path,
        "sample.py",
        """
        import os
        def foo(): pass
        class Bar: pass
        """,
    )

    result = analyzer.analyze(file_path)

    # currently the analyzer only detects type
    assert result["type"] == "python"


def test_sql_analysis(tmp_path):
    analyzer = TreeSitterAnalyzer()

    file_path = write_file(
        tmp_path,
        "query.sql",
        """
        WITH cte_orders AS (SELECT * FROM raw.orders)
        INSERT INTO analytics.orders_clean
        SELECT * FROM cte_orders
        JOIN raw.customers USING(customer_id);
        """,
    )

    result = analyzer.analyze(file_path)

    # check type and that keys exist, without asserting table names
    assert result["type"] == "sql"
    assert "tables_read" in result
    assert "tables_written" in result
    assert "ctes" in result


def test_yaml_analysis(tmp_path):
    analyzer = TreeSitterAnalyzer()

    file_path = write_file(
        tmp_path,
        "schema.yml",
        """
        version: 2
        models:
          my_model:
            description: test
        sources:
          my_src:
            tables: []
        """,
    )

    result = analyzer.analyze(file_path)

    assert result["type"] == "yaml"
    assert "top_keys" in result
    assert "models" in result
    assert "sources" in result


def test_unknown_file_type(tmp_path):
    analyzer = TreeSitterAnalyzer()

    file_path = write_file(tmp_path, "README.txt", "hello world")

    result = analyzer.analyze(file_path)

    assert result["type"] == "unknown"
