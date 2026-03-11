import textwrap
from pathlib import Path

from src.analyzers.tree_sitter_analyzer import TreeSitterAnalyzer


def write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(content))
    return path


def test_python_analysis(tmp_path):
    analyzer = TreeSitterAnalyzer()
    path = write(
        tmp_path,
        "sample.py",
        """
        import os

        @decorator
        def foo(x, y):
            return x + y

        class Bar:
            pass
        """,
    )
    result = analyzer.analyze(path)
    assert result["type"] == "python"
    assert any("import os" in imp for imp in result.get("imports", []))
    assert any("def foo" in fn for fn in result.get("functions", []))
    assert "Bar" in "".join(result.get("classes", []))


def test_sql_analysis(tmp_path):
    analyzer = TreeSitterAnalyzer()
    path = write(
        tmp_path,
        "query.sql",
        """
        WITH cte_orders AS (SELECT * FROM raw.orders)
        INSERT INTO analytics.orders_clean
        SELECT * FROM cte_orders JOIN raw.customers USING(customer_id);
        """,
    )
    result = analyzer.analyze(path)
    assert result["type"] == "sql"
    assert "raw.orders" in result["tables_read"]
    assert "analytics.orders_clean" in result["tables_written"]
    assert "cte_orders" in result["ctes"]


def test_yaml_analysis(tmp_path):
    analyzer = TreeSitterAnalyzer()
    path = write(
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
    result = analyzer.analyze(path)
    assert result["type"] == "yaml"
    assert "models" in result["top_keys"]
    assert "my_model" in result["models"]
    assert "my_src" in result["sources"]


def test_dispatcher_unknown(tmp_path):
    analyzer = TreeSitterAnalyzer()
    path = write(tmp_path, "README.txt", "hello")
    result = analyzer.analyze(path)
    assert result["type"] == "unknown"
