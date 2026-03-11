import json
from pathlib import Path
from typing import Iterable, List


def ensure_cartography_dir(repo_path: Path) -> Path:
    target = repo_path / ".cartography"
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def list_files(repo_path: Path, extensions: List[str]) -> Iterable[Path]:
    for ext in extensions:
        yield from repo_path.rglob(f"*{ext}")
