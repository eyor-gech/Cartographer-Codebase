from typing import List, Optional
from pydantic import BaseModel, Field


class ModuleNode(BaseModel):
    path: str
    language: str = "python"
    complexity_score: float = 0.0
    change_velocity_30d: int = 0
    pagerank: float = 0.0
    betweenness: float = 0.0
    is_dead_code_candidate: bool = False
    last_modified: Optional[str] = None
    purpose_statement: Optional[str] = None
    domain_cluster: Optional[str] = None


class DatasetNode(BaseModel):
    name: str
    storage_type: str = "table"
    schema_snapshot: Optional[dict] = None
    owner: Optional[str] = None
    purpose_statement: Optional[str] = None
    domain_cluster: Optional[str] = None


class FunctionNode(BaseModel):
    qualified_name: str
    parent_module: str
    signature: str
    is_public_api: bool = False
    purpose_statement: Optional[str] = None
    domain_cluster: Optional[str] = None


class TransformationNode(BaseModel):
    source_datasets: List[str] = Field(default_factory=list)
    target_datasets: List[str] = Field(default_factory=list)
    transformation_type: str = "sql"
    source_file: str
    line_range: Optional[List[int]] = None
    purpose_statement: Optional[str] = None
    domain_cluster: Optional[str] = None
