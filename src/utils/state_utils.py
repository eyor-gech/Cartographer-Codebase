from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from git import Repo, InvalidGitRepositoryError, NoSuchPathError


@dataclass
class AnalysisState:
    last_run_utc: str
    git_head: Optional[str] = None

    @classmethod
    def load(cls, path: Path) -> Optional["AnalysisState"]:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except Exception:
            return None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"last_run_utc": self.last_run_utc, "git_head": self.git_head}, indent=2), encoding="utf-8")


def current_state_for_repo(repo_path: Path) -> AnalysisState:
    head = None
    try:
        repo = Repo(repo_path, search_parent_directories=True)
        head = repo.head.commit.hexsha
    except (InvalidGitRepositoryError, NoSuchPathError, Exception):
        head = None
    return AnalysisState(last_run_utc=datetime.now(timezone.utc).isoformat(), git_head=head)

