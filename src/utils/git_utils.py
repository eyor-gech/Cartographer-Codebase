from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from git import Repo, InvalidGitRepositoryError, NoSuchPathError
from typing import Set, Optional


def change_velocity(repo_path: Path, days: int = 30) -> Dict[str, int]:
    """Return a mapping of file path to number of commits touching it in the given window."""
    try:
        repo = Repo(repo_path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return {}

    since = datetime.utcnow() - timedelta(days=days)
    velocities: Dict[str, int] = {}
    try:
        for commit in repo.iter_commits("HEAD", since=since):
            for file_path in commit.stats.files:
                velocities[file_path] = velocities.get(file_path, 0) + 1
    except Exception:
        # Be resilient to traversal issues
        return velocities
    return velocities


def changed_files_since(repo_path: Path, since: datetime) -> Set[str]:
    """Return repo-relative paths touched by commits since the given timestamp (UTC)."""
    try:
        repo = Repo(repo_path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return set()

    changed: Set[str] = set()
    try:
        for commit in repo.iter_commits("HEAD", since=since):
            for file_path in commit.stats.files:
                changed.add(file_path)
    except Exception:
        return changed
    return changed


# Backward compatibility alias
def change_velocity_last_30d(repo_path: Path) -> Dict[str, int]:
    return change_velocity(repo_path, days=30)
