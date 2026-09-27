"""User journeys for scoped scaffolding, previews, and CI verification."""

import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from supagents import core
from supagents.cli import app
from supagents.config import DEFAULT_TARGETS

runner = CliRunner()


def test_selected_targets_round_trip(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "reviewer", "--project", "-t", "claude", "-t", "codex"])
    assert result.exit_code == 0, result.output
    source = tmp_path / ".agents/supagents/reviewer.md"
    assert set(core.parse_source(source, source.parent).targets) == {"CLAUDE", "CODEX"}
    assert "Scope: project (explicit)" in result.stderr
    assert runner.invoke(app, ["build", "--project"]).exit_code == 0
    result = runner.invoke(app, ["check", "--project", "--strict"])
    assert result.exit_code == 0, result.output
    assert "2 unchanged" in result.stdout
    assert not (tmp_path / ".gemini").exists()


def test_init_custom_target_and_unknown_target(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text(
        "targets:\n  CUSTOM:\n    project_path: .custom\n    global_path: ~/.custom\n"
    )
    result = runner.invoke(
        app, ["init", "reviewer", "--project", "-c", str(config), "-t", "custom"]
    )
    assert result.exit_code == 0, result.output
    source = tmp_path / ".agents/supagents/reviewer.md"
    assert "CUSTOM: {}" in source.read_text()
    assert "CLAUDE:" not in source.read_text()
    result = runner.invoke(app, ["init", "other", "--project", "-t", "TYPO"])
    assert result.exit_code == 2
    assert not source.with_name("other.md").exists()


@pytest.mark.parametrize("command", [["check"], ["build", "--check"]])
def test_check_reports_missing_modified_and_obsolete_without_writes(
    monkeypatch, ci_workspace, ci_outputs, command
):
    monkeypatch.chdir(ci_workspace)
    assert runner.invoke(app, ["build", "--project"]).exit_code == 0
    missing, modified, original = ci_outputs
    missing.unlink()
    modified.write_text(modified.read_text() + "Changed locally.\n")
    orphan = original.with_name("retired.agent.md")
    orphan.write_bytes(original.read_bytes())
    before = {path: path.read_bytes() for path in (modified, original, orphan)}
    result = runner.invoke(app, [*command, "--project", "--strict", "--diff"])
    assert result.exit_code == 1, result.output
    assert "2 would change" in result.stdout
    assert "1 obsolete" in result.stdout
    assert "-Changed locally." in result.stdout
    assert "+++ /dev/null" in result.stdout
    assert not missing.exists()
    assert all(path.read_bytes() == content for path, content in before.items())


def test_diff_previews_additions_and_edits_without_writes(monkeypatch, ci_workspace, ci_outputs):
    monkeypatch.chdir(ci_workspace)
    result = runner.invoke(app, ["build", "--project", "--diff"])
    assert result.exit_code == 0, result.output
    assert "--- /dev/null" in result.stdout
    assert "+name: code_investigator" in result.stdout
    assert "-> CLAUDE ->" in result.stdout
    assert not any(path.exists() for path in ci_outputs)
    assert runner.invoke(app, ["build", "--project"]).exit_code == 0
    source = ci_workspace / ".agents/supagents/code_investigator.md"
    source.write_text(source.read_text() + "\nKeep [bold]literal[/bold] text.\n")
    before = {path: path.read_bytes() for path in ci_outputs}
    result = runner.invoke(app, ["build", "--project", "--diff"])
    assert result.exit_code == 0, result.output
    assert "+Keep [bold]literal[/bold] text." in result.stdout
    assert all(path.read_bytes() == content for path, content in before.items())


def test_strict_build_rejects_warnings_before_writing(monkeypatch, tmp_path, make_source):
    monkeypatch.chdir(tmp_path)
    make_source("reviewer.md", "---\nCLAUDE: {}\nTYPO: {}\n---\nReview.\n")
    result = runner.invoke(app, ["build", "--project", "--strict"])
    assert result.exit_code == 1, result.output
    assert "1 warnings" in result.stdout
    assert not (tmp_path / ".claude").exists()
    assert runner.invoke(app, ["build", "--project"]).exit_code == 0
    result = runner.invoke(app, ["check", "--project"])
    assert result.exit_code == 0, result.output
    assert "Orphan scan skipped" in result.stderr
    assert runner.invoke(app, ["check", "--project", "--strict"]).exit_code == 1


def test_check_requires_existing_sources(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["check", "--project"])
    assert result.exit_code == 2, result.output
    assert "source directory does not exist" in result.stderr
    (tmp_path / ".agents/supagents").mkdir(parents=True)
    assert runner.invoke(app, ["check", "--project", "--strict"]).exit_code == 0


def test_check_filters_orphans_by_target(monkeypatch, ci_workspace, ci_outputs):
    monkeypatch.chdir(ci_workspace)
    runner.invoke(app, ["build", "--project"])
    orphan = ci_outputs[2].with_name("retired.agent.md")
    orphan.write_bytes(ci_outputs[2].read_bytes())
    result = runner.invoke(app, ["check", "--project", "--strict", "-t", "claude"])
    assert result.exit_code == 0, result.output
    assert orphan.exists()


def test_filtered_cleanup_preserves_other_targets_in_shared_directory(
    monkeypatch, tmp_path, make_source
):
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text(
        "targets:\n  CLAUDE:\n    project_path: generated\n  GROK:\n    project_path: generated\n"
    )
    make_source("first.md", "---\nCLAUDE: {}\n---\nFirst.\n")
    make_source("second.md", "---\nGROK: {}\n---\nSecond.\n")
    flags = ["--project", "-c", str(config)]
    assert runner.invoke(app, ["build", *flags]).exit_code == 0
    second = tmp_path / "generated/second.md"
    before = second.read_bytes()
    for command in ("check", "clean"):
        result = runner.invoke(app, [command, *flags, "-t", "claude"])
        assert result.exit_code == 0, result.output
        assert second.read_bytes() == before


@pytest.mark.parametrize("command", ["check", "clean"])
def test_unreadable_output_directory_fails_closed(monkeypatch, ci_workspace, command):
    monkeypatch.chdir(ci_workspace)
    runner.invoke(app, ["build", "--project"])
    original = Path.iterdir

    def denied(path):
        if path == ci_workspace / ".claude/agents":
            raise PermissionError("directory denied")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", denied)
    result = runner.invoke(app, [command, "--project"])
    assert result.exit_code == 2, result.output
    assert "directory denied" in result.stderr


def test_output_diff_preserves_missing_final_newline(tmp_path):
    path = tmp_path / "agent.md"
    path.write_text("old")
    diff = core.output_diff(path, "new\n")
    assert "-old\n\\ No newline at end of file\n+new\n" in diff


def test_documented_reviewer_compiles_for_every_bundled_target(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/reviewer.md"
    result = core.build("project", cwd=tmp_path, source_dir=source.parent, strict=True)
    assert not result.fatal_errors
    assert not result.error_count
    assert not result.warning_count
    assert {plan.target_name for plan in result.plans} == set(DEFAULT_TARGETS)
    for plan in result.plans:
        if plan.target_name == "CODEX":
            metadata = tomllib.loads(plan.rendered)
            assert metadata["sandbox_mode"] == "read-only"
            body = metadata["developer_instructions"]
        else:
            _, body = core.split_frontmatter(plan.rendered)
        assert body.strip() == plan.source.body.strip()
    checked = core.check("project", cwd=tmp_path, source_dir=source.parent)
    assert not checked.written
    assert not checked.orphans
