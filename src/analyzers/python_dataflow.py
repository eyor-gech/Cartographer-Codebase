from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import logging
import ast

from tree_sitter import Parser, Node
from tree_sitter_languages import get_language


@dataclass(frozen=True)
class LineageEvent:
    source_datasets: List[str]
    target_datasets: List[str]
    transformation_type: str
    source_file: str
    line_range: List[int]
    dynamic_reference: bool

    def to_dict(self) -> Dict:
        return {
            "source_datasets": self.source_datasets,
            "target_datasets": self.target_datasets,
            "transformation_type": self.transformation_type,
            "source_file": self.source_file,
            "line_range": self.line_range,
            "dynamic_reference": self.dynamic_reference,
        }


class PythonDataflowAnalyzer:
    """
    Detects common data IO patterns in Python (pandas, PySpark, SQLAlchemy).

    It is intentionally heuristic: it must never crash and should surface best-effort lineage events.
    """

    PANDAS_READ_SUFFIXES = {".read_csv", ".read_parquet", ".read_sql"}
    PANDAS_WRITE_SUFFIXES = {".to_sql", ".to_parquet"}

    # spark.read.csv / spark.read.parquet / spark.read... and df.write...
    SPARK_READ_PREFIX = "spark.read"
    SPARK_WRITE_ATTR = "write"

    SQLA_EXECUTE = {"engine.execute", "session.execute"}

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._parser: Optional[Parser] = None
        try:
            lang = get_language("python")
            parser = Parser()
            parser.set_language(lang)
            self._parser = parser
        except Exception as exc:
            # Keep analyzer usable even if tree-sitter bindings are incompatible in the runtime.
            self.logger.warning("PythonDataflow falling back to ast module: %s", exc)

    def analyze_file(self, path: Path, repo_root: Optional[Path] = None) -> List[Dict]:
        try:
            content = path.read_bytes()
        except Exception as exc:
            self.logger.error("PythonDataflow failed reading %s: %s", path, exc)
            return []

        rel = str(path.relative_to(repo_root)) if repo_root else str(path)
        events: List[LineageEvent] = []
        if self._parser is not None:
            try:
                tree = self._parser.parse(content)
                for call in self._find_nodes(tree.root_node, "call"):
                    try:
                        event = self._analyze_call(call, content, rel)
                        if event:
                            events.append(event)
                    except Exception as exc:
                        self.logger.debug("PythonDataflow skip call in %s: %s", path, exc)
                        continue
            except Exception as exc:
                self.logger.error("PythonDataflow tree-sitter parse failure for %s: %s", path, exc)
        else:
            events.extend(self._analyze_with_ast(content, rel))

        return [e.to_dict() for e in events]

    def _analyze_with_ast(self, content: bytes, rel_path: str) -> List[LineageEvent]:
        try:
            tree = ast.parse(content.decode("utf-8", errors="ignore"))
        except Exception:
            return []
        out: List[LineageEvent] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = self._ast_dotted_name(node.func)
            if not call_name:
                continue
            start_line = getattr(node, "lineno", 1) or 1
            end_line = getattr(node, "end_lineno", start_line) or start_line

            # Mirror the tree-sitter heuristics with best-effort extraction.
            arg0, dynamic = self._ast_first_arg(node)
            if any(call_name.endswith(s) for s in self.PANDAS_READ_SUFFIXES):
                out.append(
                    LineageEvent(
                        source_datasets=[arg0] if arg0 else [],
                        target_datasets=[],
                        transformation_type="python",
                        source_file=rel_path,
                        line_range=[start_line, end_line],
                        dynamic_reference=dynamic,
                    )
                )
            elif call_name.endswith(".to_sql") or call_name.endswith(".to_parquet"):
                out.append(
                    LineageEvent(
                        source_datasets=[],
                        target_datasets=[arg0] if arg0 else [],
                        transformation_type="python",
                        source_file=rel_path,
                        line_range=[start_line, end_line],
                        dynamic_reference=dynamic,
                    )
                )
            elif call_name.startswith(f"{self.SPARK_READ_PREFIX}."):
                out.append(
                    LineageEvent(
                        source_datasets=[arg0] if arg0 else [],
                        target_datasets=[],
                        transformation_type="python",
                        source_file=rel_path,
                        line_range=[start_line, end_line],
                        dynamic_reference=dynamic,
                    )
                )
            elif f".{self.SPARK_WRITE_ATTR}." in call_name:
                out.append(
                    LineageEvent(
                        source_datasets=[],
                        target_datasets=[arg0] if arg0 else [],
                        transformation_type="python",
                        source_file=rel_path,
                        line_range=[start_line, end_line],
                        dynamic_reference=dynamic,
                    )
                )
            elif call_name.endswith(".execute"):
                # If SQL is a literal, record it for reconciliation.
                if arg0 and not dynamic:
                    out.append(
                        LineageEvent(
                            source_datasets=[arg0],
                            target_datasets=[],
                            transformation_type="python",
                            source_file=rel_path,
                            line_range=[start_line, end_line],
                            dynamic_reference=dynamic,
                        )
                    )
        return out

    def _ast_dotted_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            left = self._ast_dotted_name(node.value)
            return f"{left}.{node.attr}" if left else node.attr
        return ""

    def _ast_first_arg(self, call: ast.Call) -> Tuple[Optional[str], bool]:
        if not call.args:
            return None, False
        a0 = call.args[0]
        if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
            return a0.value, False
        if isinstance(a0, ast.JoinedStr):
            return ast.get_source_segment("", a0) or "<fstring>", True
        if isinstance(a0, ast.Name):
            return a0.id, True
        return None, True

    def _analyze_call(self, call: Node, content: bytes, rel_path: str) -> Optional[LineageEvent]:
        func = call.child_by_field_name("function")
        args = call.child_by_field_name("arguments")
        if not func:
            return None

        call_name = self._dotted_name(func, content)
        if not call_name:
            return None

        start_line = (call.start_point[0] + 1) if call.start_point else 1
        end_line = (call.end_point[0] + 1) if call.end_point else start_line

        # pandas reads (handles aliases like pd.read_csv)
        if any(call_name.endswith(s) for s in self.PANDAS_READ_SUFFIXES):
            dataset, dynamic = self._first_arg_dataset(args, content)
            srcs = [dataset] if dataset else []
            self._log_dynamic(rel_path, call_name, dataset, dynamic)
            return LineageEvent(
                source_datasets=srcs,
                target_datasets=[],
                transformation_type="python",
                source_file=rel_path,
                line_range=[start_line, end_line],
                dynamic_reference=dynamic,
            )

        # pandas writes (to_sql/to_parquet) called on a df instance; tree-sitter won't tell us it's a DataFrame.
        if call_name.endswith(".to_sql"):
            dataset, dynamic = self._first_arg_dataset(args, content)
            tgts = [dataset] if dataset else []
            self._log_dynamic(rel_path, call_name, dataset, dynamic)
            return LineageEvent(
                source_datasets=[],
                target_datasets=tgts,
                transformation_type="python",
                source_file=rel_path,
                line_range=[start_line, end_line],
                dynamic_reference=dynamic,
            )

        if call_name.endswith(".to_parquet"):
            dataset, dynamic = self._first_arg_dataset(args, content)
            tgts = [dataset] if dataset else []
            self._log_dynamic(rel_path, call_name, dataset, dynamic)
            return LineageEvent(
                source_datasets=[],
                target_datasets=tgts,
                transformation_type="python",
                source_file=rel_path,
                line_range=[start_line, end_line],
                dynamic_reference=dynamic,
            )

        # spark.read.csv / spark.read.parquet
        if call_name.startswith(f"{self.SPARK_READ_PREFIX}."):
            dataset, dynamic = self._first_arg_dataset(args, content)
            srcs = [dataset] if dataset else []
            self._log_dynamic(rel_path, call_name, dataset, dynamic)
            return LineageEvent(
                source_datasets=srcs,
                target_datasets=[],
                transformation_type="python",
                source_file=rel_path,
                line_range=[start_line, end_line],
                dynamic_reference=dynamic,
            )

        # spark write patterns: df.write.parquet(...) / df.write.csv(...)
        if f".{self.SPARK_WRITE_ATTR}." in call_name:
            dataset, dynamic = self._first_arg_dataset(args, content)
            tgts = [dataset] if dataset else []
            self._log_dynamic(rel_path, call_name, dataset, dynamic)
            return LineageEvent(
                source_datasets=[],
                target_datasets=tgts,
                transformation_type="python",
                source_file=rel_path,
                line_range=[start_line, end_line],
                dynamic_reference=dynamic,
            )

        # SQLAlchemy execute (SQL literal -> later reconciled by Hydrologist with sqlglot)
        if call_name in self.SQLA_EXECUTE or call_name.endswith(".execute"):
            sql_text, dynamic = self._first_arg_string(args, content)
            if sql_text:
                self._log_dynamic(rel_path, call_name, "<sql>", dynamic)
                return LineageEvent(
                    source_datasets=[sql_text] if not dynamic else [],
                    target_datasets=[],
                    transformation_type="python",
                    source_file=rel_path,
                    line_range=[start_line, end_line],
                    dynamic_reference=dynamic,
                )

        return None

    def _log_dynamic(self, source_file: str, call_name: str, dataset: Optional[str], dynamic: bool) -> None:
        if dynamic:
            self.logger.info("Dynamic dataset reference in %s (%s): %s", source_file, call_name, dataset)

    def _first_arg_dataset(self, args: Optional[Node], content: bytes) -> Tuple[Optional[str], bool]:
        value, dynamic = self._first_arg_string(args, content)
        return value, dynamic

    def _first_arg_string(self, args: Optional[Node], content: bytes) -> Tuple[Optional[str], bool]:
        if not args:
            return None, False

        # Arguments node children include punctuation; filter named children.
        named = [c for c in args.named_children]
        if not named:
            return None, False

        first = named[0]
        if first.type == "string":
            return self._string_value(first, content), False
        if first.type in ("identifier", "attribute", "subscript"):
            return self._node_text(first, content), True
        if first.type == "f_string":
            return self._node_text(first, content), True
        return self._node_text(first, content), True

    def _string_value(self, node: Node, content: bytes) -> str:
        raw = self._node_text(node, content)
        # Strip simple quotes; keep as-is if complex.
        if len(raw) >= 2 and raw[0] in ("'", '"') and raw[-1] == raw[0]:
            return raw[1:-1]
        return raw

    def _dotted_name(self, node: Node, content: bytes) -> str:
        if node.type == "identifier":
            return self._node_text(node, content)
        if node.type == "attribute":
            obj = node.child_by_field_name("object")
            attr = node.child_by_field_name("attribute")
            if not attr:
                return ""
            left = self._dotted_name(obj, content) if obj else ""
            right = self._node_text(attr, content)
            return f"{left}.{right}" if left else right
        if node.type == "call":
            inner = node.child_by_field_name("function")
            return self._dotted_name(inner, content) if inner else ""
        return ""

    def _node_text(self, node: Node, content: bytes) -> str:
        return content[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")

    def _find_nodes(self, root: Node, node_type: str) -> List[Node]:
        found: List[Node] = []
        stack = [root]
        while stack:
            n = stack.pop()
            if n.type == node_type:
                found.append(n)
            stack.extend(reversed(n.children))
        return found
