from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import config_dir


CACHE_FILE_NAME = "cache.json"
HISTORY_FILE_NAME = "history"


@dataclass
class SessionCache:
    last_mode: str = ""
    last_provider: str = ""
    last_model: str = ""
    recent_commands: list[str] = field(default_factory=list)
    context_segments: list[str] = field(default_factory=list)
    project_context_key: str = ""
    project_context: str = ""


def cache_path(root: Path | None = None) -> Path:
    return config_dir(root) / CACHE_FILE_NAME


def history_path(root: Path | None = None) -> Path:
    return config_dir(root) / HISTORY_FILE_NAME


def load_cache(root: Path | None = None) -> SessionCache:
    path = cache_path(root)
    if not path.exists():
        return SessionCache()
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return SessionCache(
        last_mode=data.get("last_mode", ""),
        last_provider=data.get("last_provider", ""),
        last_model=data.get("last_model", ""),
        recent_commands=list(data.get("recent_commands", [])),
        context_segments=list(data.get("context_segments", [])),
        project_context_key=data.get("project_context_key", ""),
        project_context=data.get("project_context", ""),
    )


def save_cache(cache: SessionCache, root: Path | None = None) -> Path:
    directory = config_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = cache_path(root)
    path.write_text(json.dumps(asdict(cache), indent=2), encoding="utf-8")
    return path


def record_command(root: Path, line: str, *, mode: str, provider: str, model: str) -> None:
    stripped = line.strip()
    if not stripped:
        return
    cache = load_cache(root)
    cache.last_mode = mode
    cache.last_provider = provider
    cache.last_model = model
    cache.recent_commands = (cache.recent_commands + [stripped])[-50:]
    cache.context_segments = (cache.context_segments + [stripped])[-100:]
    save_cache(cache, root)
