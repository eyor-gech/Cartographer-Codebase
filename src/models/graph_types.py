from enum import Enum


class GraphKind(str, Enum):
    MODULE = "module"
    LINEAGE = "lineage"
