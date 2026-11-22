"""User journeys for scoped scaffolding, previews, and CI verification."""

import tomllib
from pathlib import Path

import pytest

from supagents import core, sources
from supagents.config import DEFAULT_TARGETS
from tests.conftest import MakeSource, RunCLI


def test_selected_targets_round_trip(tmp_path: Path, run_cli: RunCLI) -> None:
    result = run_cli("init", "reviewer", "--project", "-t", "claude", "-t", "codex", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    source = tmp_path / ".agents/supagents/reviewer.md"
    assert set(sources.parse_source(source, source.parent).targets) == {"CLAUDE", "CODEX"}
    assert "Scope: project (explicit)" in result.stderr
    assert run_cli("build", "--project", cwd=tmp_path).exit_code == 0
    result = run_cli("check", "--project", "--strict", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert "2 unchanged" in result.stdout
    assert not (tmp_path / ".gemini").exists()


def test_init_custom_target_and_unknown_target(tmp_path: Path, run_cli: RunCLI) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "targets:\n  CUSTOM:\n    project_path: .custom\n    global_path: ~/.custom\n",
        encoding="utf-8",
    )
    result = run_cli(
        "init", "reviewer", "--project", "-c", str(config), "-t", "custom", cwd=tmp_path
    )
    assert result.exit_code == 0, result.output
    source = tmp_path / ".agents/supagents/reviewer.md"
    text = source.read_text(encoding="utf-8")
    assert "CUSTOM: {}" in text
    assert "CLAUDE:" not in text
    result = run_cli("init", "other", "--project", "-t", "TYPO", cwd=tmp_path)
    assert result.exit_code == 2
    assert not source.with_name("other.md").exists()


@pytest.mark.parametrize("name", ["true", "123", "null", "2026-10-13"])
def test_scalar_like_scaffold_names_round_trip(tmp_path: Path, name: str, run_cli: RunCLI) -> None:
    assert run_cli("init", name, "--project", cwd=tmp_path).exit_code == 0
    result = run_cli("build", "--project", "--strict", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    data = tomllib.loads((tmp_path / f".codex/agents/{name}.toml").read_text(encoding="utf-8"))
    assert data["name"] == name
    result = run_cli("check", "--project", "--strict", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert "9 unchanged" in result.stdout


@pytest.mark.parametrize("target", ["true", "my: tool"])
def test_scaffold_quotes_custom_target_keys(tmp_path: Path, target: str, run_cli: RunCLI) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        f'targets:\n  "{target}":\n    project_path: .custom\n    global_path: ~/.custom\n',
        encoding="utf-8",
    )
    flags = ["--project", "--config", str(config), "--target", target]
    result = run_cli("init", "reviewer", *flags, cwd=tmp_path)
    assert result.exit_code == 0, result.output
    result = run_cli("build", "--strict", *flags, cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".custom/reviewer.md").is_file()
    assert run_cli("check", "--strict", *flags, cwd=tmp_path).exit_code == 0


@pytest.mark.parametrize("command", ["check", "clean"])
def test_overlapping_output_directory_preserves_marked_source(
    tmp_path: Path, command: str, run_cli: RunCLI
) -> None:
    root = tmp_path / "inputs"
    root.mkdir()
    source = root / "reviewer.md"
    source.write_text(
        f"---\n{core.marker_line(Path('old.md'))}\n"
        "name: reviewer\ndescription: Review changes\nCODEX: {}\n---\nReview.\n",
        encoding="utf-8",
    )
    before = source.read_bytes()
    config = tmp_path / "config.yaml"
    config.write_text("targets:\n  CLAUDE:\n    project_path: inputs\n", encoding="utf-8")
    flags = ["--project", "--source-dir", str(root), "--config", str(config)]
    assert run_cli("build", *flags, cwd=tmp_path).exit_code == 0
    result = run_cli(command, *flags, cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert source.read_bytes() == before


@pytest.mark.parametrize("command", [["check"], ["build", "--check"]])
def test_check_reports_missing_modified_and_obsolete_without_writes(
    ci_workspace: Path, ci_outputs: list[Path], command: list[str], run_cli: RunCLI
) -> None:
    assert run_cli("build", "--project", cwd=ci_workspace).exit_code == 0
    missing, modified, original = ci_outputs
    missing.unlink()
    modified.write_text(
        modified.read_text(encoding="utf-8") + "Changed locally.\n", encoding="utf-8"
    )
    orphan = original.with_name("retired.agent.md")
    orphan.write_bytes(original.read_bytes())
    before = {path: path.read_bytes() for path in (modified, original, orphan)}
    result = run_cli(*command, "--project", "--strict", "--diff", cwd=ci_workspace)
    assert result.exit_code == 1, result.output
    assert "2 would change" in result.stdout
    assert "1 obsolete" in result.stdout
    assert "-Changed locally." in result.stdout
    assert "+++ /dev/null" in result.stdout
    assert not missing.exists()
    assert all(path.read_bytes() == content for path, content in before.items())


def test_diff_previews_additions_and_edits_without_writes(
    ci_workspace: Path, ci_outputs: list[Path], run_cli: RunCLI
) -> None:
    result = run_cli("build", "--project", "--diff", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert "--- /dev/null" in result.stdout
    assert "+name: code_investigator" in result.stdout
    assert "-> CLAUDE ->" in result.stdout
    assert not any(path.exists() for path in ci_outputs)
    assert run_cli("build", "--project", cwd=ci_workspace).exit_code == 0
    source = ci_workspace / ".agents/supagents/code_investigator.md"
    source.write_text(
        source.read_text(encoding="utf-8") + "\nKeep [bold]literal[/bold] text.\n",
        encoding="utf-8",
    )
    before = {path: path.read_bytes() for path in ci_outputs}
    result = run_cli("build", "--project", "--diff", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert "+Keep [bold]literal[/bold] text." in result.stdout
    assert all(path.read_bytes() == content for path, content in before.items())


def test_strict_build_rejects_warnings_before_writing(
    tmp_path: Path, make_source: MakeSource, run_cli: RunCLI
) -> None:
    make_source("reviewer.md", "---\nCLAUDE: {}\nTYPO: {}\n---\nReview.\n")
    result = run_cli("build", "--project", "--strict", cwd=tmp_path)
    assert result.exit_code == 1, result.output
    assert "1 warnings" in result.stdout
    assert not (tmp_path / ".claude").exists()
    assert run_cli("build", "--project", cwd=tmp_path).exit_code == 0
    result = run_cli("check", "--project", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert "Orphan scan skipped" in result.stderr
    assert run_cli("check", "--project", "--strict", cwd=tmp_path).exit_code == 1


def test_check_requires_existing_sources(tmp_path: Path, run_cli: RunCLI) -> None:
    tmp_path = tmp_path / ("long-directory-" * 8)
    tmp_path.mkdir()
    result = run_cli("check", "--project", cwd=tmp_path)
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "source directory does not exist" in result.stderr
    assert str(tmp_path / ".agents/supagents") in result.stderr
    (tmp_path / ".agents/supagents").mkdir(parents=True)
    assert run_cli("check", "--project", "--strict", cwd=tmp_path).exit_code == 0


def test_check_filters_orphans_by_target(
    ci_workspace: Path, ci_outputs: list[Path], run_cli: RunCLI
) -> None:
    run_cli("build", "--project", cwd=ci_workspace)
    orphan = ci_outputs[2].with_name("retired.agent.md")
    orphan.write_bytes(ci_outputs[2].read_bytes())
    result = run_cli("check", "--project", "--strict", "-t", "claude", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert orphan.exists()


def test_filtered_cleanup_preserves_other_targets_in_shared_directory(
    tmp_path: Path, make_source: MakeSource, run_cli: RunCLI
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "targets:\n  CLAUDE:\n    project_path: generated\n  GROK:\n    project_path: generated\n",
        encoding="utf-8",
    )
    make_source("first.md", "---\nCLAUDE: {}\n---\nFirst.\n")
    make_source("second.md", "---\nGROK: {}\n---\nSecond.\n")
    flags = ["--project", "-c", str(config)]
    assert run_cli("build", *flags, cwd=tmp_path).exit_code == 0
    second = tmp_path / "generated/second.md"
    before = second.read_bytes()
    for command in ("check", "clean"):
        result = run_cli(command, *flags, "-t", "claude", cwd=tmp_path)
        assert result.exit_code == 0, result.output
        assert second.read_bytes() == before


@pytest.mark.parametrize("command", ["check", "clean"])
def test_unreadable_output_directory_fails_closed(
    monkeypatch: pytest.MonkeyPatch, ci_workspace: Path, command: str, run_cli: RunCLI
) -> None:
    run_cli("build", "--project", cwd=ci_workspace)
    original = Path.iterdir

    def denied(path: Path):
        if path == ci_workspace / ".claude/agents":
            raise PermissionError("directory denied")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", denied)
    result = run_cli(command, "--project", cwd=ci_workspace)
    assert result.exit_code == 1, result.output
    assert "directory denied" in result.stderr


def test_output_diff_preserves_missing_final_newline(tmp_path: Path) -> None:
    path = tmp_path / "agent.md"
    path.write_text("old", encoding="utf-8")
    diff = core.output_diff(path, "new\n")
    assert "-old\n\\ No newline at end of file\n+new\n" in diff


def test_documented_reviewer_compiles_for_every_bundled_target(tmp_path: Path) -> None:
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
            _, body = sources.split_frontmatter(plan.rendered)
        assert body.strip() == plan.source.body.strip()
    checked = core.check("project", cwd=tmp_path, source_dir=source.parent)
    assert not checked.written
    assert not checked.orphans


def test_partial_cli_list_build_check_clean_journey(tmp_path: Path, run_cli: RunCLI) -> None:
    root = tmp_path / ".agents/supagents"
    root.mkdir(parents=True)
    partial = root / "_reviewer.md"
    partial.write_text(
        "---\n"
        "CLAUDE:\n"
        "  model: inherit\n"
        "  tools: [Read, Glob, Grep]\n"
        "OPENCODE:\n"
        "  mode: subagent\n"
        "---\n"
        "{{BODY}}\n\n"
        "## Output Contract\n"
        "Report VERDICT.\n",
        encoding="utf-8",
    )
    child = root / "security.md"
    child.write_text(
        "---\n"
        "extends: _reviewer\n"
        "name: security\n"
        "description: Audit security boundaries\n"
        "---\n"
        "Inspect threat paths.\n",
        encoding="utf-8",
    )

    listed = run_cli("list", "--project", cwd=tmp_path)
    assert listed.exit_code == 0, listed.output
    assert "security" in listed.stdout
    assert "_reviewer" not in listed.stdout

    assert run_cli("build", "--project", "--strict", cwd=tmp_path).exit_code == 0
    checked = run_cli("check", "--project", "--strict", cwd=tmp_path)
    assert checked.exit_code == 0, checked.output
    assert "2 unchanged, 0 obsolete" in checked.stdout

    child.unlink()
    dry_clean = run_cli("clean", "--project", "--dry-run", cwd=tmp_path)
    assert dry_clean.exit_code == 0, dry_clean.output
    assert "would remove" in dry_clean.stdout
    assert run_cli("clean", "--project", cwd=tmp_path).exit_code == 0
    assert partial.exists()
    assert not (tmp_path / ".claude/agents/security.md").exists()
    assert not (tmp_path / ".opencode/agents/security.md").exists()
