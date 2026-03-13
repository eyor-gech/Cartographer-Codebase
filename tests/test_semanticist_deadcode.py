from pathlib import Path

from src.agents.semanticist import Semanticist
from src.analyzers.dead_code_detector import detect_dead_code_candidates
from src.graph.knowledge_graph import KnowledgeGraph
from src.models.nodes import ModuleNode
from src.utils.token_budget import TokenBudget


def test_token_budget_enforces_limit():
    b = TokenBudget(model="x", hard_limit_tokens=10)
    b.add_usage(5, 0.01)
    assert b.tokens_used == 5
    try:
        b.add_usage(6, 0.01)
        assert False, "expected budget exceed"
    except RuntimeError:
        pass


def test_semanticist_offline_purpose(tmp_path: Path):
    p = tmp_path / "m.py"
    p.write_text("import sqlglot\n\ndef f():\n  pass\n", encoding="utf-8")
    s = Semanticist()
    out = s.infer_module_purpose(p)
    assert "purpose_statement" in out
    assert "drift" in out


def test_dead_code_detector_excludes_cli(tmp_path: Path):
    g = KnowledgeGraph(kind="module")
    g.add_module_node("cli.py", **ModuleNode(path="cli.py").model_dump())
    g.add_module_node("a.py", **ModuleNode(path="a.py").model_dump())
    # nobody imports a.py => candidate, but cli.py excluded
    dead = detect_dead_code_candidates(g)
    assert "cli.py" not in dead
    assert "a.py" in dead

