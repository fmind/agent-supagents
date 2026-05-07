"""Tests for cli.py — exit codes, scope detection, output."""

import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from supagents import core
from supagents.cli import app
from tests.conftest import MakeSource

runner = CliRunner()


def _run(monkeypatch: pytest.MonkeyPatch, cwd: Path, *args: str) -> Result:
    """Invoke the CLI with cwd set; return the CliRunner result."""
    monkeypatch.chdir(cwd)
    return runner.invoke(app, list(args))


def test_help_no_args() -> None:
    result = runner.invoke(app, [])
    output = (result.stdout or "") + (result.stderr or "")
    for cmd in ("build", "clean"):
        assert cmd in output


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "supagents" in result.stdout


def test_build_acceptance_canonical(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path, ci_outputs: list[Path]
) -> None:
    result = _run(monkeypatch, ci_workspace, "build", "--project")
    assert result.exit_code == 0, result.stdout
    for path in ci_outputs:
        assert path.exists(), path


def test_build_dry_run_no_write(monkeypatch: pytest.MonkeyPatch, ci_workspace: Path) -> None:
    result = _run(monkeypatch, ci_workspace, "build", "--project", "--dry-run")
    assert result.exit_code == 0, result.stdout
    assert not (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_build_global_and_project_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run(monkeypatch, tmp_path, "build", "--global", "--project")
    assert result.exit_code == 2


def test_clean_removes_orphans(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path, ci_outputs: list[Path]
) -> None:
    _run(monkeypatch, ci_workspace, "build", "--project")
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    result = _run(monkeypatch, ci_workspace, "clean", "--project")
    assert result.exit_code == 0, result.stdout
    for path in ci_outputs:
        assert not path.exists(), path


def test_clean_dry_run_keeps_files(monkeypatch: pytest.MonkeyPatch, ci_workspace: Path) -> None:
    _run(monkeypatch, ci_workspace, "build", "--project")
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    result = _run(monkeypatch, ci_workspace, "clean", "--project", "--dry-run")
    assert result.exit_code == 0, result.stdout
    assert (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_scope_auto_detect_project(monkeypatch: pytest.MonkeyPatch, ci_workspace: Path) -> None:
    result = _run(monkeypatch, ci_workspace, "build")
    assert result.exit_code == 0, result.stdout
    assert (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_scope_auto_detect_global_when_no_project_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # No .agents/supagents/ exists → auto-detect "global". No global sources should
    # exist for this isolated test, so build prints a summary with 0 written.
    result = _run(monkeypatch, tmp_path, "build")
    assert result.exit_code == 0, result.stdout


def test_build_global_flag_explicit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``--global`` resolves to global scope explicitly (no auto-detect)."""
    result = _run(monkeypatch, tmp_path, "build", "--global")
    assert result.exit_code == 0, result.stdout


@pytest.mark.parametrize(
    ("flags", "expected_unchanged_count"),
    [
        # Quiet (default): only the summary line should mention "unchanged".
        pytest.param((), 1, id="quiet"),
        # Verbose: three per-file lines + one summary line.
        pytest.param(("--verbose",), 4, id="verbose"),
    ],
)
def test_build_twice_reports_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    ci_workspace: Path,
    flags: tuple[str, ...],
    expected_unchanged_count: int,
) -> None:
    _run(monkeypatch, ci_workspace, "build", "--project")
    result = _run(monkeypatch, ci_workspace, "build", "--project", *flags)
    assert result.exit_code == 0, result.stdout
    out = result.stdout or ""
    assert out.count("unchanged") == expected_unchanged_count
    assert "wrote" not in out


def test_module_invocation_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "supagents", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "supagents" in result.stdout


def test_build_malformed_source_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("bad.md", "---\nname: bad: invalid: [\n---\nbody\n")
    result = _run(monkeypatch, tmp_path, "build", "--project")
    assert result.exit_code == 2


def test_build_target_error_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("agent.md", "---\nname: agent\nCLAUDE:\n  OUTPUT: [not, a, string]\n---\nbody\n")
    result = _run(monkeypatch, tmp_path, "build", "--project")
    assert result.exit_code == 1


def test_build_prints_source_warnings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, make_source: MakeSource
) -> None:
    # Unknown top-level UPPERCASE key produces a warning during parsing.
    make_source(
        "agent.md",
        "---\nname: agent\nCLAUDE:\n  model: sonnet\nFOO:\n  bar: baz\n---\nbody\n",
    )
    result = _run(monkeypatch, tmp_path, "build", "--project")
    assert result.exit_code == 0, result.stdout
    assert "WARN" in (result.stderr or "")
    assert "FOO" in (result.stderr or "")


def test_build_duplicate_source_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("agent.md", "---\nname: agent\nCLAUDE:\n  model: sonnet\n---\nbody\n")

    def fake_build(*args: object, **kwargs: object) -> core.BuildSummary:
        raise core.DuplicateSourceError("simulated duplicate")

    monkeypatch.setattr(core, "build", fake_build)
    result = _run(monkeypatch, tmp_path, "build", "--project")
    assert result.exit_code == 1


def test_clean_nothing_to_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_source_dir: Path
) -> None:
    result = _run(monkeypatch, tmp_path, "clean", "--project")
    assert result.exit_code == 0, result.stdout
    assert "Nothing to clean" in (result.stdout or "")


def test_clean_unlink_failure_exits_2(monkeypatch: pytest.MonkeyPatch, ci_workspace: Path) -> None:
    _run(monkeypatch, ci_workspace, "build", "--project")
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()

    real_unlink = Path.unlink

    def failing_unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name.endswith(".md") and "claude" in str(self):
            raise OSError("simulated permission denied")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    result = _run(monkeypatch, ci_workspace, "clean", "--project")
    assert result.exit_code == 2


# ---------- --check ----------


def test_build_check_exits_1_on_drift(monkeypatch: pytest.MonkeyPatch, ci_workspace: Path) -> None:
    result = _run(monkeypatch, ci_workspace, "build", "--project", "--check")
    assert result.exit_code == 1, result.stdout
    assert not (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_build_check_exits_0_when_in_sync(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    _run(monkeypatch, ci_workspace, "build", "--project")
    result = _run(monkeypatch, ci_workspace, "build", "--project", "--check")
    assert result.exit_code == 0, result.stdout


def test_build_check_and_dry_run_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    result = _run(monkeypatch, ci_workspace, "build", "--project", "--check", "--dry-run")
    assert result.exit_code != 0


# ---------- --target ----------


def test_build_target_filter_skips_others(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    result = _run(monkeypatch, ci_workspace, "build", "--project", "--target", "claude")
    assert result.exit_code == 0, result.stdout
    assert (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()
    assert not (ci_workspace / ".gemini" / "agents" / "code_investigator.md").exists()


def test_build_target_unknown_rejected(monkeypatch: pytest.MonkeyPatch, ci_workspace: Path) -> None:
    result = _run(monkeypatch, ci_workspace, "build", "--project", "--target", "WAT")
    assert result.exit_code != 0


def test_clean_target_filter_only_removes_selected(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    _run(monkeypatch, ci_workspace, "build", "--project")
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    result = _run(monkeypatch, ci_workspace, "clean", "--project", "--target", "CLAUDE")
    assert result.exit_code == 0, result.stdout
    assert not (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()
    # Copilot orphan was untouched because we filtered to CLAUDE only.
    assert (ci_workspace / ".github" / "agents" / "code_investigator.agent.md").exists()


# ---------- --config ----------


def test_build_config_flag_redirects_output(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    cfg = ci_workspace / "custom.yaml"
    cfg.write_text(
        "targets:\n  claude:\n    project_path: .alt-claude/agents\n",
        encoding="utf-8",
    )
    result = _run(
        monkeypatch, ci_workspace, "build", "--project", "--config", str(cfg), "--target", "CLAUDE"
    )
    assert result.exit_code == 0, result.stdout
    assert (ci_workspace / ".alt-claude" / "agents" / "code_investigator.md").exists()
    assert not (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_build_malformed_config_yaml_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    cfg = ci_workspace / "bad.yaml"
    cfg.write_text("targets: {claude: [\n", encoding="utf-8")
    result = _run(monkeypatch, ci_workspace, "build", "--project", "--config", str(cfg))
    assert result.exit_code == 2
    assert "invalid YAML" in (result.stderr or "")


# ---------- init ----------


def test_init_scaffolds_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = _run(monkeypatch, tmp_path, "init", "reviewer", "--project")
    assert result.exit_code == 0, result.stdout
    src = tmp_path / ".agents" / "supagents" / "reviewer.md"
    assert src.exists()
    text = src.read_text(encoding="utf-8")
    assert "name: reviewer" in text
    assert "# Reviewer" in text
    for block in ("CLAUDE:", "GEMINI:", "COPILOT:", "CURSOR:", "OPENCODE:", "KILO:"):
        assert block in text, block


def test_init_output_builds_six_targets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _run(monkeypatch, tmp_path, "init", "reviewer", "--project")
    result = _run(monkeypatch, tmp_path, "build", "--project")
    assert result.exit_code == 0, result.stdout
    expected = [
        tmp_path / ".claude" / "agents" / "reviewer.md",
        tmp_path / ".gemini" / "agents" / "reviewer.md",
        tmp_path / ".github" / "agents" / "reviewer.agent.md",
        tmp_path / ".cursor" / "agents" / "reviewer.md",
        tmp_path / ".opencode" / "agents" / "reviewer.md",
        tmp_path / ".kilo" / "agents" / "reviewer.md",
    ]
    for path in expected:
        assert path.exists(), path


def test_init_strips_md_suffix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = _run(monkeypatch, tmp_path, "init", "reviewer.md", "--project")
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / ".agents" / "supagents" / "reviewer.md").exists()


def test_init_rejects_invalid_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = _run(monkeypatch, tmp_path, "init", "Bad-Name", "--project")
    assert result.exit_code != 0


def test_init_refuses_existing_unless_force(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_source: MakeSource,
    project_source_dir: Path,
) -> None:
    make_source("reviewer.md", "existing\n")
    result = _run(monkeypatch, tmp_path, "init", "reviewer", "--project")
    assert result.exit_code == 1
    # --force overwrites
    result = _run(monkeypatch, tmp_path, "init", "reviewer", "--project", "--force")
    assert result.exit_code == 0, result.stdout
    assert "name: reviewer" in (project_source_dir / "reviewer.md").read_text(encoding="utf-8")


# ---------- list ----------


def test_list_shows_sources_and_targets(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    result = _run(monkeypatch, ci_workspace, "list", "--project")
    assert result.exit_code == 0, result.stdout
    out = result.stdout or ""
    assert "code_investigator" in out
    assert "CLAUDE" in out
    assert "GEMINI" in out
    assert "COPILOT" in out


def test_list_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_source_dir: Path
) -> None:
    result = _run(monkeypatch, tmp_path, "list", "--project")
    assert result.exit_code == 0, result.stdout
    assert "No sources" in (result.stdout or "")


def test_list_target_filter(monkeypatch: pytest.MonkeyPatch, ci_workspace: Path) -> None:
    result = _run(monkeypatch, ci_workspace, "list", "--project", "--target", "CLAUDE")
    assert result.exit_code == 0, result.stdout
    out = result.stdout or ""
    assert "CLAUDE" in out
    assert "GEMINI" not in out
    assert "COPILOT" not in out


def test_list_prints_fatal_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("bad.md", "---\nname: bad: invalid: [\n---\nbody\n")
    result = _run(monkeypatch, tmp_path, "list", "--project")
    assert result.exit_code == 0, result.stdout
    assert "ERROR" in (result.stderr or "")
