"""Supagents configuration: targets, source roots, and scope helpers.

Sane defaults are bundled, so the config file is optional. Users can
override per-target by writing YAML at ``$XDG_CONFIG_HOME/supagents/config.yaml``
(default ``~/.config/supagents/config.yaml``). Per-field merge is shallow:
a field present in user config replaces the default for that target.
Lowercase target keys in YAML are normalised to UPPERCASE to match the
source frontmatter convention.

Example user config::

    targets:
      claude:
        global_path: ~/.claude/agents
        project_path: .claude/agents
"""

import os
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

Scope = Literal["global", "project"]

GLOBAL_SOURCE_PATH = Path("~/.agents/supagents")
PROJECT_SOURCE_PATH = Path(".agents/supagents")


class ConfigError(Exception):
    """Raised when the user config file cannot be loaded or parsed."""


def user_config_path() -> Path:
    """XDG-compliant location of the user config file."""
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base, "supagents", "config.yaml").expanduser()


class TargetConfig(BaseModel):
    """One target's output paths and filename convention.

    Paths are stored as-written (tildes preserved) and expanded by callers
    that resolve actual filesystem locations (see ``output_dir``). This keeps
    ``$HOME`` overrides effective at use time, not at construction time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    global_path: Path
    project_path: Path
    filename_suffix: str = ".md"


DEFAULT_TARGETS: dict[str, TargetConfig] = {
    "CLAUDE": TargetConfig(
        global_path=Path("~/.claude/agents"),
        project_path=Path(".claude/agents"),
    ),
    "GEMINI": TargetConfig(
        global_path=Path("~/.gemini/agents"),
        project_path=Path(".gemini/agents"),
    ),
    "COPILOT": TargetConfig(
        global_path=Path("~/.copilot/agents"),
        project_path=Path(".github/agents"),
        filename_suffix=".agent.md",
    ),
    "CURSOR": TargetConfig(
        global_path=Path("~/.cursor/agents"),
        project_path=Path(".cursor/agents"),
    ),
    "OPENCODE": TargetConfig(
        global_path=Path("~/.config/opencode/agents"),
        project_path=Path(".opencode/agents"),
    ),
    "KILO": TargetConfig(
        global_path=Path("~/.config/kilo/agents"),
        project_path=Path(".kilo/agents"),
    ),
}


class Config(BaseModel):
    """Top-level supagents configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    targets: dict[str, TargetConfig]

    @field_validator("targets", mode="before")
    @classmethod
    def _uppercase_keys(cls, v: object) -> object:
        if isinstance(v, dict):
            return {str(k).upper(): val for k, val in v.items()}
        return v

    @classmethod
    def load(cls, path: Path | None = None) -> Self:
        """Defaults overlaid with user config (if the YAML file exists).

        Raises ``ConfigError`` if the file exists but cannot be parsed as YAML.
        """
        path = path or user_config_path()
        user: dict[str, object] = {}
        if path.is_file():
            try:
                loaded = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
            except YAMLError as e:
                raise ConfigError(f"invalid YAML in {path}: {e}") from e
            if isinstance(loaded, dict):
                user = loaded

        merged = {name: target.model_dump() for name, target in DEFAULT_TARGETS.items()}
        user_targets = user.get("targets")
        if isinstance(user_targets, dict):
            for name, value in user_targets.items():
                if isinstance(value, dict):
                    key = str(name).upper()
                    merged[key] = {**merged.get(key, {}), **value}
        return cls.model_validate({**user, "targets": merged})


def detect_scope(cwd: Path | None = None) -> Scope:
    """Return ``"project"`` if ``.agents/supagents/`` exists in ``cwd``, else ``"global"``."""
    return "project" if ((cwd or Path.cwd()) / PROJECT_SOURCE_PATH).is_dir() else "global"


def source_root(scope: Scope, cwd: Path | None = None) -> Path:
    """Directory holding source files for ``scope``."""
    if scope == "project":
        return (cwd or Path.cwd()) / PROJECT_SOURCE_PATH
    return GLOBAL_SOURCE_PATH.expanduser()


def output_dir(target: TargetConfig, scope: Scope, cwd: Path | None = None) -> Path:
    """Default output directory for ``target`` x ``scope``."""
    if scope == "project":
        return (cwd or Path.cwd()) / target.project_path
    return target.global_path.expanduser()
