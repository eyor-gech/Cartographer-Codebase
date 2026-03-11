from pathlib import Path
from typing import Dict, List, Optional
import logging
import sqlglot
import yaml
from tree_sitter import Parser
from tree_sitter_languages import get_language

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".sql": "sql",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".js": "javascript",
    ".ts": "typescript",
}


class LanguageRouter:
    """Lightweight router that prepares a Tree-sitter parser per extension."""

    def __init__(self):
        self.parsers = {}
        for ext, lang_name in SUPPORTED_EXTENSIONS.items():
            try:
                lang = get_language(lang_name)
                parser = Parser()
                parser.set_language(lang)
                self.parsers[ext] = parser
            except Exception:
                # gracefully skip languages that fail to load
                continue

    def get_parser(self, path: Path) -> Optional[Parser]:
        return self.parsers.get(path.suffix)


class TreeSitterAnalyzer:
    """Extracts structural facts using Tree-sitter and language-aware helpers."""

    def __init__(self):
        self.router = LanguageRouter()
        self.logger = logging.getLogger(__name__)

    def analyze_python(self, path: Path, content: bytes) -> Dict:
        parser = self.router.get_parser(path)
        if not parser:
            return {}
        tree = parser.parse(content)
        root = tree.root_node
        imports: List[str] = []
        functions: List[str] = []
        classes: List[str] = []

        def node_text(node):
            return content[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")

        for child in root.children:
            try:
                if child.type in ("import_statement", "import_from_statement"):
                    imports.append(node_text(child))
                if child.type == "function_definition":
                    signature = self._extract_signature(child, content)
                    functions.append(signature)
                if child.type == "decorated_definition":
                    func = child.child_by_field_name("definition")
                    if func and func.type == "function_definition":
                        decorator_text = [
                            node_text(dec) for dec in child.children if dec.type == "decorator"
                        ]
                        signature = self._extract_signature(func, content, decorator_text)
                        functions.append(signature)
                if child.type == "class_definition":
                    name = child.child_by_field_name("name")
                    if name:
                        classes.append(node_text(name))
            except Exception as exc:
                self.logger.debug("Tree-sitter extraction skip for %s child %s: %s", path, child.type, exc)
                continue
        return {"imports": imports, "functions": functions, "classes": classes}

    def analyze(self, path: Path) -> Dict:
        suffix = path.suffix.lower()
        try:
            content = path.read_bytes()
        except Exception as exc:
            self.logger.error("Failed reading %s: %s", path, exc)
            return {"type": "unknown", "error": str(exc)}

        if suffix == ".py":
            try:
                data = self.analyze_python(path, content)
                data["type"] = "python"
                return data
            except Exception as exc:
                self.logger.error("Tree-sitter parse failure for %s: %s", path, exc)
                return {"type": "python", "error": str(exc)}
        if suffix == ".sql":
            return self.analyze_sql(path, content)
        if suffix in (".yml", ".yaml"):
            return self.analyze_yaml(path, content)
        if suffix in (".js", ".ts"):
            return self.analyze_js_ts(path, content)
        return {"type": "unknown"}

    # SQL
    def analyze_sql(self, path: Path, content: bytes) -> Dict:
        sql_text = content.decode("utf-8", errors="ignore")
        tables_read = set()
        tables_written = set()
        ctes = set()
        parsed = None
        try:
            parsed = sqlglot.parse_one(sql_text, error_level="ignore")
            if parsed:
                for table in parsed.find_all(sqlglot.exp.Table):
                    if table.this:
                        tables_read.add(table.this.sql())
                for cte in parsed.find_all(sqlglot.exp.CTE):
                    if cte.this and hasattr(cte.this, "this"):
                        ctes.add(cte.this.this.sql())
                insert = parsed.find(sqlglot.exp.Insert)
                if insert and insert.this:
                    tables_written.add(insert.this.sql())
                create = parsed.find(sqlglot.exp.Create)
                if create and create.this:
                    tables_written.add(create.this.sql())
        except Exception as exc:
            self.logger.error("SQL parse failure for %s: %s", path, exc)

        # dbt ref() detection
        if parsed:
            for ref in parsed.find_all(sqlglot.exp.Func):
                if getattr(ref, "name", "").lower() == "ref":
                    args = ref.expressions
                    if args:
                        arg = args[0]
                        tables_read.add(arg.name if hasattr(arg, "name") else arg.sql())

        return {
            "type": "sql",
            "tables_read": sorted(tables_read),
            "tables_written": sorted(tables_written),
            "ctes": sorted(ctes),
        }

    # YAML
    def analyze_yaml(self, path: Path, content: bytes) -> Dict:
        try:
            doc = yaml.safe_load(content) or {}
        except Exception as exc:
            self.logger.error("YAML parse failure for %s: %s", path, exc)
            return {"type": "yaml", "error": str(exc)}

        top_keys = list(doc.keys()) if isinstance(doc, dict) else []
        metadata = {"models": [], "sources": [], "tests": []}
        if isinstance(doc, dict):
            metadata["models"] = list(doc.get("models", {}).keys()) if isinstance(doc.get("models"), dict) else doc.get("models", []) or []
            metadata["sources"] = list(doc.get("sources", {}).keys()) if isinstance(doc.get("sources"), dict) else doc.get("sources", []) or []
            metadata["tests"] = list(doc.get("tests", {}).keys()) if isinstance(doc.get("tests"), dict) else doc.get("tests", []) or []
        return {
            "type": "yaml",
            "top_keys": top_keys,
            **metadata,
        }

    # JS/TS
    def analyze_js_ts(self, path: Path, content: bytes) -> Dict:
        parser = self.router.get_parser(path)
        if not parser:
            return {"type": "javascript", "imports": [], "exports": []}
        try:
            tree = parser.parse(content)
        except Exception as exc:
            self.logger.error("JS/TS parse failure for %s: %s", path, exc)
            return {"type": "javascript", "error": str(exc)}
        root = tree.root_node
        imports: List[str] = []
        exports: List[str] = []

        def text(node):
            return content[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")

        for child in root.children:
            try:
                if child.type == "import_statement":
                    imports.append(text(child))
                if child.type in ("export_statement", "export_clause"):
                    exports.append(text(child))
            except Exception:
                continue
        return {"type": "javascript", "imports": imports, "exports": exports}

    def _extract_signature(self, func_node, content: bytes, decorators: Optional[List[str]] = None) -> str:
        params = func_node.child_by_field_name("parameters")
        name = func_node.child_by_field_name("name")
        name_text = content[name.start_byte : name.end_byte].decode("utf-8", errors="ignore") if name else ""
        params_text = content[params.start_byte : params.end_byte].decode("utf-8", errors="ignore") if params else "()"
        decorator_prefix = "".join(decorators) if decorators else ""
        return f"{decorator_prefix}def {name_text}{params_text}"
