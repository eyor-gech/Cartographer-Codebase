import re


def infer_purpose_from_code(code: str):

    if "sqlglot" in code:
        return "SQL lineage parsing module"

    if "networkx" in code:
        return "graph construction and lineage traversal module"

    if "typer" in code:
        return "CLI command interface"

    if "pandas" in code:
        return "data processing module"

    return "general application module"