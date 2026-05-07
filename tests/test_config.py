"""Tests for config.py — defaults, loading, XDG resolution, overrides."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from supagents.config import (
    DEFAULT_TARGETS,
    Config,
    ConfigError,
    TargetConfig,
    detect_scope,
    output_dir,
    source_root,
    user_config_path,
)


def test_load_with_no_file_uses_defaults(tmp_path: Path) -> None:
    config = Config.load(tmp_path / "nonexistent.yaml")
    assert set(config.targets) == set(DEFAULT_TARGETS)
    assert config.targets["CLAUDE"].filename_suffix == ".md"
    assert config.targets["COPILOT"].filename_suffix == ".agent.md"


def test_default_targets_cover_all_six_bundled_clis() -> None:
    assert set(DEFAULT_TARGETS) == {"CLAUDE", "GEMINI", "COPILOT", "CURSOR", "OPENCODE", "KILO"}


@pytest.mark.parametrize(
    ("target", "global_path", "project_path"),
    [
        ("CURSOR", Path("~/.cursor/agents"), Path(".cursor/agents")),
        ("OPENCODE", Path("~/.config/opencode/agents"), Path(".opencode/agents")),
        ("KILO", Path("~/.config/kilo/agents"), Path(".kilo/agents")),
    ],
)
def test_new_default_targets_have_expected_paths(
    target: str, global_path: Path, project_path: Path
) -> None:
    cfg = DEFAULT_TARGETS[target]
    assert cfg.global_path == global_path
    assert cfg.project_path == project_path
    assert cfg.filename_suffix == ".md"


def test_load_user_overrides_per_field(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "targets:\n  claude:\n    global_path: /custom/claude\n",
        encoding="utf-8",
    )
    config = Config.load(cfg_file)
    assert config.targets["CLAUDE"].global_path == Path("/custom/claude")
    # project_path falls back to default
    assert config.targets["CLAUDE"].project_path == Path(".claude/agents")


def test_load_user_can_add_new_target(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "targets:\n"
        "  mytool:\n"
        "    global_path: ~/.mytool/agents\n"
        "    project_path: .mytool/agents\n",
        encoding="utf-8",
    )
    config = Config.load(cfg_file)
    assert "MYTOOL" in config.targets
    assert config.targets["MYTOOL"].filename_suffix == ".md"


def test_load_ignores_non_dict_top_level(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("- a\n- b\n", encoding="utf-8")
    config = Config.load(cfg_file)
    assert set(config.targets) == set(DEFAULT_TARGETS)


def test_load_ignores_target_value_that_is_not_dict(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("targets:\n  claude: not-a-dict\n", encoding="utf-8")
    config = Config.load(cfg_file)
    # CLAUDE keeps its default values since "not-a-dict" was skipped.
    assert config.targets["CLAUDE"].project_path == Path(".claude/agents")


def test_load_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("unknown: oops\ntargets: {}\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        Config.load(cfg_file)


def test_load_raises_config_error_on_malformed_yaml(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("targets: {claude: [\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        Config.load(cfg_file)


def test_target_config_preserves_tilde_for_lazy_expansion() -> None:
    # Paths are stored as-written; expansion happens at use time so test fixtures
    # can monkeypatch $HOME and have it take effect for global-scope writes.
    target = TargetConfig(
        global_path=Path("~/.foo"),
        project_path=Path(".foo"),
    )
    assert target.global_path == Path("~/.foo")
    assert target.project_path == Path(".foo")


def test_output_dir_global_expands_home_at_call_time(isolated_home: Path) -> None:
    target = TargetConfig(
        global_path=Path("~/.foo"),
        project_path=Path(".foo"),
    )
    assert output_dir(target, "global") == isolated_home / ".foo"


def test_target_config_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        TargetConfig.model_validate(
            {
                "global_path": "~/.foo",
                "project_path": ".foo",
                "unknown": "bad",
            }
        )


def test_user_config_path_respects_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert user_config_path() == tmp_path / "xdg" / "supagents" / "config.yaml"


def test_user_config_path_default_when_xdg_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = user_config_path()
    assert path.parts[-3:] == (".config", "supagents", "config.yaml")


def test_detect_scope_project(tmp_path: Path) -> None:
    (tmp_path / ".agents" / "supagents").mkdir(parents=True)
    assert detect_scope(tmp_path) == "project"


def test_detect_scope_global(tmp_path: Path) -> None:
    assert detect_scope(tmp_path) == "global"


def test_source_root_project_relative_to_cwd(tmp_path: Path) -> None:
    assert source_root("project", tmp_path) == tmp_path / ".agents" / "supagents"


def test_output_dir_project_uses_project_path(tmp_path: Path) -> None:
    target = DEFAULT_TARGETS["CLAUDE"]
    assert output_dir(target, "project", tmp_path) == tmp_path / ".claude" / "agents"


def test_output_dir_global_uses_global_path() -> None:
    target = DEFAULT_TARGETS["CLAUDE"]
    assert output_dir(target, "global") == target.global_path.expanduser()
