from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .modes import DEFAULT_MODE


CONFIG_DIR_NAME = ".turtles"
CONFIG_FILE_NAME = "config.json"


@dataclass
class ProviderConfig:
    provider: str = ""
    username: str = ""
    api_key: str = ""
    model: str = ""
    base_url: str = ""


@dataclass
class DisplayConfig:
    prompt_style: str = "claude"
    color_theme: str = "turtle-green"
    verbosity: str = "normal"
    show_animation: bool = True


@dataclass
class TurtlesConfig:
    trusted: bool = False
    mode: str = DEFAULT_MODE.key
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    skills: list[str] = field(default_factory=list)
    subagents: list[str] = field(default_factory=list)
    plugins: dict[str, bool] = field(default_factory=dict)
    hooks: dict[str, str] = field(default_factory=dict)
    mcp_servers: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "github": {
                "enabled": True,
                "transport": "stdio",
                "command": "github-mcp-server",
                "scope": "project",
            }
        }
    )


def project_root(path: Path | None = None) -> Path:
    return (path or Path.cwd()).resolve()


def config_dir(root: Path | None = None) -> Path:
    return project_root(root) / CONFIG_DIR_NAME


def config_path(root: Path | None = None) -> Path:
    return config_dir(root) / CONFIG_FILE_NAME


def load_config(root: Path | None = None) -> TurtlesConfig:
    path = config_path(root)
    if not path.exists():
        return TurtlesConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    provider = ProviderConfig(**data.get("provider", {}))
    display = DisplayConfig(**data.get("display", {}))
    return TurtlesConfig(
        trusted=data.get("trusted", False),
        mode=data.get("mode", DEFAULT_MODE.key),
        provider=provider,
        display=display,
        skills=list(data.get("skills", [])),
        subagents=list(data.get("subagents", [])),
        plugins=dict(data.get("plugins", {})),
        hooks=dict(data.get("hooks", {})),
        mcp_servers=dict(data.get("mcp_servers", TurtlesConfig().mcp_servers)),
    )


def save_config(config: TurtlesConfig, root: Path | None = None) -> Path:
    directory = config_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = config_path(root)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def init_project(root: Path | None = None) -> Path:
    config = load_config(root)
    return save_config(config, root)


def is_logged_in(config: TurtlesConfig) -> bool:
    return bool(config.provider.provider and config.provider.api_key)


def redacted_config(config: TurtlesConfig) -> dict[str, Any]:
    data = asdict(config)
    key = data["provider"].get("api_key", "")
    if key:
        data["provider"]["api_key"] = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"
    return data
