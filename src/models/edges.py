from enum import Enum


class EdgeType(str, Enum):
    IMPORTS = "imports"
    CALLS = "calls"
    DEFINED_IN = "defined_in"
    CONSUMES = "consumes"
    PRODUCES = "produces"
