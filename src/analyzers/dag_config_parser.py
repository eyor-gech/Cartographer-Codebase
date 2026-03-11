from pathlib import Path
from typing import Dict, List


class DbtProjectDetector:
    """Heuristic detector for dbt projects and lightweight metadata extraction."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def is_dbt_project(self) -> bool:
        return (self.repo_path / "dbt_project.yml").exists() and (self.repo_path / "models").exists()

    def list_models(self) -> List[str]:
        if not self.is_dbt_project():
            return []
        return [str(p.relative_to(self.repo_path)) for p in self.repo_path.rglob("models/**/*.sql")]

    def metadata(self) -> Dict:
        return {
            "is_dbt": self.is_dbt_project(),
            "models": self.list_models(),
        }
