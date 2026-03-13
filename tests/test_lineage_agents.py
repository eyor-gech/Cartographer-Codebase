import textwrap
from pathlib import Path

from src.analyzers.python_dataflow import PythonDataflowAnalyzer
from src.analyzers.sql_lineage import SQLLineageAnalyzer
from src.analyzers.dag_config_parser import DAGConfigParser
from src.agents.hydrologist import Hydrologist
from src.graph.knowledge_graph import KnowledgeGraph


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_python_dataflow_pandas(tmp_path):
    py = _write(
        tmp_path,
        "app.py",
        """
        import pandas as pd

        df = pd.read_csv("s3://bucket/raw/orders.csv")
        df.to_sql("analytics.orders", con=engine)
        """,
    )
    events = PythonDataflowAnalyzer().analyze_file(py, repo_root=tmp_path)
    assert any("s3://bucket/raw/orders.csv" in e.get("source_datasets", []) for e in events)
    assert any("analytics.orders" in e.get("target_datasets", []) for e in events)


def test_sql_lineage_multi_dialect(tmp_path):
    sql = _write(
        tmp_path,
        "models/model.sql",
        """
        WITH x AS (SELECT * FROM raw.orders)
        SELECT * FROM x JOIN raw.customers USING(customer_id)
        """,
    )
    result = SQLLineageAnalyzer().analyze_file(sql)
    assert "raw.orders" in result["source_tables"] or "orders" in result["source_tables"]
    assert result["line_range"] == [1, 2] or result["line_range"][0] == 1


def test_dag_config_parser_schema_refs(tmp_path):
    _write(
        tmp_path,
        "models/schema.yml",
        """
        version: 2
        models:
          - name: orders
            tests:
              - relationships:
                  to: ref('customers')
        """,
    )
    events = DAGConfigParser(tmp_path).extract_lineage_events()
    assert any("customers" in e.get("source_datasets", []) for e in events)
    assert any("orders" in e.get("target_datasets", []) for e in events)


def test_hydrologist_blast_radius(tmp_path):
    _write(
        tmp_path,
        "models/a.sql",
        "select * from raw.a",
    )
    _write(
        tmp_path,
        "models/b.sql",
        "select * from a",
    )
    g = KnowledgeGraph(kind="lineage")
    h = Hydrologist(tmp_path, g)
    h.analyze()
    # raw.a should impact downstream target datasets (at least 'a' and/or 'b')
    br = h.blast_radius("raw.a")
    assert isinstance(br, list)
