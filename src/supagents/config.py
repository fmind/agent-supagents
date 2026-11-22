"""Supagents configuration: targets, source roots, and scope helpers.

Sane defaults are bundled, so the config file is optional. Users can
override per-target by writing YAML at ``$XDG_CONFIG_HOME/supagents/config.yaml``
(default ``~/.config/supagents/config.yaml``). Per-field merge is shallow:
a field present in user config replaces the default for that target.
Lowercase target keys in YAML are normalised to UPPERCASE to match the
source frontmatter convention.
"""

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Self

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

Scope = Literal["global", "project"]
OutputFormat = Literal["markdown", "toml"]

GLOBAL_SOURCE_PATH = Path("~/.agents/supagents")
PROJECT_SOURCE_PATH = Path(".agents/supagents")

_TARGET_FIELDS = frozenset({"global_path", "project_path", "filename_suffix", "format", "body_key"})
_CONFIG_FIELDS = frozenset({"targets"})
_VALID_FORMATS = frozenset({"markdown", "toml"})


class ConfigError(Exception):
    """Raised when the user config file cannot be loaded or parsed."""


def user_config_path() -> Path:
    """XDG-compliant location of the user config file."""
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base, "supagents", "config.yaml").expanduser()


def _validate_path(value: object, field_name: str) -> Path:
    if isinstance(value, str):
        if not value or not value.strip() or "\0" in value:
            raise ValueError(f"{field_name} must be a non-empty path without NUL characters")
        path = Path(value)
    elif isinstance(value, Path):
        if "\0" in str(value):
            raise ValueError(f"{field_name} must not contain NUL characters")
        path = value
    else:
        raise TypeError(f"{field_name} must be a path string")
    try:
        path.expanduser()
    except RuntimeError as e:
        raise ValueError(f"{field_name} home directory cannot be expanded") from e
    return path


@dataclass(frozen=True, slots=True)
class TargetConfig:
    """One target's output paths and filename convention.

    Paths are stored as-written (tildes preserved) and expanded by callers
    that resolve actual filesystem locations (see ``output_dir``). This keeps
    ``$HOME`` overrides effective at use time, not at construction time.
    """

    global_path: Path
    project_path: Path
    filename_suffix: str = ".md"
    format: OutputFormat = "markdown"
    body_key: str = "developer_instructions"

    def __post_init__(self) -> None:
        object.__setattr__(self, "global_path", _validate_path(self.global_path, "global_path"))
        object.__setattr__(self, "project_path", _validate_path(self.project_path, "project_path"))
        if (
            not isinstance(self.filename_suffix, str)
            or not self.filename_suffix.startswith(".")
            or any(c in self.filename_suffix for c in "/\\*?[]\0")
        ):
            raise ValueError("filename_suffix must be an extension without separators or globs")
        if not isinstance(self.format, str) or self.format not in _VALID_FORMATS:
            raise ValueError(f"format must be one of {sorted(_VALID_FORMATS)}")
        if not isinstance(self.body_key, str) or not self.body_key:
            raise ValueError("body_key must be a non-empty string")

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> Self:
        """Build a validated ``TargetConfig`` from a raw YAML mapping."""
        unknown = set(raw) - _TARGET_FIELDS
        if unknown:
            raise ValueError(f"unknown target field(s): {', '.join(sorted(map(str, unknown)))}")
        if "global_path" not in raw or "project_path" not in raw:
            raise ValueError("target requires both global_path and project_path")
        raw_format = raw.get("format", "markdown")
        if not isinstance(raw_format, str) or raw_format not in _VALID_FORMATS:
            raise ValueError(f"format must be one of {sorted(_VALID_FORMATS)}")
        fmt: OutputFormat = "toml" if raw_format == "toml" else "markdown"
        suffix = raw.get("filename_suffix", ".md")
        body_key = raw.get("body_key", "developer_instructions")
        if not isinstance(suffix, str):
            raise TypeError("filename_suffix must be a string")
        if not isinstance(body_key, str):
            raise TypeError("body_key must be a string")
        return cls(
            global_path=_validate_path(raw["global_path"], "global_path"),
            project_path=_validate_path(raw["project_path"], "project_path"),
            filename_suffix=suffix,
            format=fmt,
            body_key=body_key,
        )


DEFAULT_TARGETS: dict[str, TargetConfig] = {
    "AGY": TargetConfig(
        global_path=Path("~/.gemini/config/agents"),
        project_path=Path(".agents/agents"),
    ),
    "CODEX": TargetConfig(
        global_path=Path("~/.codex/agents"),
        project_path=Path(".codex/agents"),
        filename_suffix=".toml",
        format="toml",
    ),
    "GROK": TargetConfig(
        global_path=Path("~/.grok/agents"),
        project_path=Path(".grok/agents"),
    ),
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


@dataclass(frozen=True, slots=True)
class Config:
    """Top-level supagents configuration."""

    targets: dict[str, TargetConfig]

    def __post_init__(self) -> None:
        if not isinstance(self.targets, dict):
            raise TypeError("targets must be a mapping")
        normalized: dict[str, TargetConfig] = {}
        for k, val in self.targets.items():
            if not isinstance(k, str) or not k.upper().isupper():
                raise ValueError("target names must contain a letter with an uppercase form")
            key = k.upper()
            if key in normalized:
                raise ValueError(f"duplicate target name after normalization: {key!r}")
            if not isinstance(val, TargetConfig):
                raise TypeError(f"target {key!r} must be a TargetConfig")
            normalized[key] = val
        object.__setattr__(self, "targets", normalized)

    @classmethod
    def load(cls, path: Path | None = None) -> Self:
        """Defaults overlaid with user config (if the YAML file exists).

        Raises ``ConfigError`` if the file exists (or is a broken symlink/directory)
        and cannot be loaded or validated.
        """
        explicit = path is not None
        try:
            resolved = path.expanduser() if path is not None else user_config_path()
        except RuntimeError as e:
            raise ConfigError(f"config path cannot be expanded: {e}") from e
        try:
            is_file = resolved.is_file()
            exists_or_link = resolved.exists() or resolved.is_symlink()
        except OSError as e:
            raise ConfigError(f"cannot access config path {resolved}: {e}") from e
        if explicit and not is_file:
            raise ConfigError(f"config file does not exist: {resolved}")
        if not explicit and exists_or_link and not is_file:
            raise ConfigError(f"config path is not a regular file: {resolved}")

        user: dict[str, object] = {}
        if is_file:
            try:
                loaded = YAML(typ="safe").load(resolved.read_text(encoding="utf-8"))
            except (YAMLError, OSError, UnicodeError, RecursionError) as e:
                raise ConfigError(f"invalid YAML in {resolved}: {e}") from e
            if loaded is not None and not isinstance(loaded, dict):
                raise ConfigError(f"config must be a YAML mapping: {resolved}")
            user = loaded or {}
        if not user:
            return cls(targets=dict(DEFAULT_TARGETS))

        unknown_top = set(user) - _CONFIG_FIELDS
        if unknown_top:
            keys = ", ".join(sorted(map(str, unknown_top)))
            raise ConfigError(f"invalid config: unknown top-level key(s): {keys}")

        merged: dict[str, dict[str, object]] = {
            name: asdict(target) for name, target in DEFAULT_TARGETS.items()
        }
        user_targets = user.get("targets")
        if "targets" in user and not isinstance(user_targets, dict):
            raise ConfigError("targets must be a mapping")
        if isinstance(user_targets, dict):
            seen_keys: set[str] = set()
            for name, value in user_targets.items():
                if not isinstance(name, str) or not isinstance(value, dict):
                    raise ConfigError("targets require string names and mapping values")
                if not name.upper().isupper():
                    raise ConfigError(
                        "invalid config: target names must contain a letter with an uppercase form"
                    )
                key = name.upper()
                if key in seen_keys:
                    raise ConfigError(f"invalid config: duplicate target name {key!r}")
                seen_keys.add(key)
                merged[key] = {**merged.get(key, {}), **value}
        try:
            validated = {name: TargetConfig.from_mapping(raw) for name, raw in merged.items()}
            return cls(targets=validated)
        except (ValueError, TypeError) as e:
            raise ConfigError(f"invalid config: {e}") from e


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
        return (cwd or Path.cwd()) / target.project_path.expanduser()
    return target.global_path.expanduser()
