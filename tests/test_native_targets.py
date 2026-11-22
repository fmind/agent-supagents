"""Native serialization, explicit source roots, and safe generation contracts."""

import tomllib
from pathlib import Path

import pytest

from supagents import core
from supagents.config import Config, ConfigError
from tests.conftest import RunCLI


def source(root: Path, text: str, name: str = "reviewer.md") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def test_native_formats_preserve_body_and_nested_config(tmp_path):
    root = tmp_path / "inputs"
    body = 'Review "quotes", \\paths, Unicode café.\n\n```python\nprint("test")\n```'
    source(
        root,
        "---\nname: reviewer\ndescription: Review changes\n"
        "AGY:\n  subagent: true\nGROK:\n  tools: Read, Grep\n"
        "CODEX:\n  sandbox_mode: read-only\n  mcp_servers:\n    example:\n      enabled: false\n"
        "  APPEND_BODY: Report evidence.\n---\n" + body,
    )
    result = core.build("project", cwd=tmp_path, source_dir=root)
    assert not result.fatal_errors
    assert len(result.written) == 3
    data = tomllib.loads((tmp_path / ".codex/agents/reviewer.toml").read_text(encoding="utf-8"))
    assert data["developer_instructions"] == body + "\n\nReport evidence.\n"
    assert data["mcp_servers"]["example"]["enabled"] is False
    assert data["sandbox_mode"] == "read-only"
    again = core.build("project", cwd=tmp_path, source_dir=root)
    assert len(again.skipped_unchanged) == 3
    assert not again.written
    (root / "reviewer.md").unlink()
    assert len(core.find_orphans("project", cwd=tmp_path, source_dir=root)) == 3


@pytest.mark.parametrize(
    "fields",
    [
        "description: test",
        "name: test",
        "name: []\ndescription: test",
        "name: test\ndescription: test\nCODEX:\n  developer_instructions: override",
        "name: test\ndescription: test\nCODEX:\n  model: null",
    ],
)
def test_invalid_codex_does_not_write_any_target(tmp_path, fields):
    root = tmp_path / "inputs"
    if "CODEX:" not in fields:
        fields += "\nCODEX: {}"
    source(root, f"---\n{fields}\nCLAUDE: {{}}\n---\nReview.")
    result = core.build("project", cwd=tmp_path, source_dir=root)
    assert result.error_count
    assert not result.written


def test_invalid_rendered_unicode_fails_before_any_writes(tmp_path, run_cli: RunCLI):
    root = tmp_path / "inputs"
    source(
        root,
        '---\nname: reviewer\ndescription: "\\ud800"\nCLAUDE: {}\nCODEX: {}\n---\nReview.',
    )
    result = run_cli("build", "--project", "--source-dir", str(root), cwd=tmp_path)
    assert result.exit_code == 1, result.output
    assert "UTF-8" in result.stderr
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".codex").exists()


def test_atomic_write_cleans_up_encoding_failure(tmp_path):
    output = tmp_path / "reviewer.md"
    output.write_text("Preserve this file.", encoding="utf-8")
    with pytest.raises(UnicodeEncodeError):
        core.atomic_write(output, "\ud800")
    assert output.read_text(encoding="utf-8") == "Preserve this file."
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("kind", ["handwritten", "binary", "directory", "symlink"])
def test_existing_unowned_outputs_preserved_before_other_writes(tmp_path, kind):
    root = tmp_path / "inputs"
    source(root, "---\nCLAUDE: {}\nGROK: {}\n---\nReview.")
    output = tmp_path / ".grok/agents/reviewer.md"
    output.parent.mkdir(parents=True)
    if kind == "directory":
        output.mkdir()
    elif kind == "symlink":
        output.symlink_to(root / "reviewer.md")
    else:
        output.write_bytes(b"handwritten" if kind == "handwritten" else b"\xff")
    result = core.build("project", cwd=tmp_path, source_dir=root)
    assert result.fatal_errors
    assert not result.written
    assert not (tmp_path / ".claude").exists()
    assert output.exists()


@pytest.mark.parametrize("output", ["reviewer.md", "../../shared.md"])
def test_source_overwrite_and_output_collision_rejected(tmp_path, output):
    root = tmp_path / "inputs"
    source(root, f"---\nCLAUDE:\n  OUTPUT: {output}\nGROK:\n  OUTPUT: {output}\n---\nReview.")
    result = core.build("project", cwd=tmp_path, source_dir=root)
    assert result.fatal_errors
    assert not result.written
    assert (root / "reviewer.md").read_text(encoding="utf-8").startswith("---")


@pytest.mark.parametrize(
    "broken",
    [
        "not frontmatter",
        "---\nCLAUDE: []\n---\nbody",
        "---\nCLAUDE:\n  OUTPUT: []\n---\nbody",
        "---\nTYPO: {}\n---\nbody",
    ],
)
def test_cleanup_refuses_invalid_or_ambiguous_sources(tmp_path, broken):
    root = tmp_path / "inputs"
    path = source(root, "---\nCLAUDE: {}\n---\nReview.")
    core.build("project", cwd=tmp_path, source_dir=root)
    path.write_text(broken, encoding="utf-8")
    with pytest.raises(core.ParseError, match="cannot clean"):
        core.find_orphans("project", cwd=tmp_path, source_dir=root)
    assert (tmp_path / ".claude/agents/reviewer.md").is_file()


def test_source_dir_cli_and_config_overrides(tmp_path, run_cli: RunCLI):
    cfg = tmp_path / "supagents.yaml"
    cfg.write_text("targets:\n  CODEX:\n    project_path: dot_codex/agents\n", encoding="utf-8")
    assert (
        run_cli("init", "reviewer", "--project", "--source-dir", "inputs", cwd=tmp_path).exit_code
        == 0
    )
    flags = ["--project", "--source-dir", "inputs", "--config", str(cfg), "--target", "codex"]
    assert run_cli("build", *flags, "--check", cwd=tmp_path).exit_code == 1
    assert run_cli("build", *flags, cwd=tmp_path).exit_code == 0
    assert (tmp_path / "dot_codex/agents/reviewer.toml").is_file()
    assert run_cli("build", *flags, "--check", cwd=tmp_path).exit_code == 0
    assert run_cli("list", *flags, cwd=tmp_path).exit_code == 0
    (tmp_path / "inputs/reviewer.md").write_text("broken", encoding="utf-8")
    assert run_cli("clean", *flags, cwd=tmp_path).exit_code == 1


@pytest.mark.parametrize(
    "content",
    [
        "targets: []",
        "targets:\n  CLAUDE:\n    format: xml",
        "targets:\n  CLAUDE:\n    filename_suffix: /bad",
        "targets:\n  5: {}",
        'targets:\n  "123":\n    project_path: generated\n    global_path: ~/.custom',
        'targets:\n  "":\n    project_path: generated\n    global_path: ~/.custom',
    ],
)
def test_config_rejects_invalid_shapes(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(path)


def test_missing_explicit_inputs_fail(tmp_path):
    with pytest.raises(ConfigError, match="does not exist"):
        Config.load(tmp_path / "missing.yaml")
    result = core.build("project", cwd=tmp_path, source_dir=tmp_path / "missing")
    assert result.fatal_errors
    assert not result.written


@pytest.mark.parametrize("failure", ["missing", "unreadable", "broken-source-link"])
def test_cleanup_preserves_outputs_when_sources_cannot_be_enumerated(
    tmp_path, monkeypatch, failure, run_cli: RunCLI
):
    root = tmp_path / ".agents/supagents"
    path = source(root, "---\nCLAUDE: {}\n---\nReview.")
    result = core.build("project", cwd=tmp_path)
    output = result.written[0]
    before = output.read_bytes()
    if failure == "missing":
        path.unlink()
        root.rmdir()
    elif failure == "broken-source-link":
        path.unlink()
        path.symlink_to(root / "unavailable")
    else:
        original = Path.iterdir

        def inaccessible(directory):
            if directory == root:
                raise PermissionError("source directory is unreadable")
            return original(directory)

        monkeypatch.setattr(Path, "iterdir", inaccessible)

    cli_res = run_cli("clean", "--project", cwd=tmp_path)

    assert cli_res.exit_code == 1
    assert "cannot clean" in cli_res.stderr
    assert output.read_bytes() == before


def test_build_reports_source_enumeration_errors_before_writing(tmp_path, monkeypatch):
    root = tmp_path / "inputs"
    source(root, "---\nCLAUDE: {}\n---\nReview.")

    def inaccessible(_directory):
        raise PermissionError("source directory is unreadable")

    monkeypatch.setattr(Path, "iterdir", inaccessible)
    result = core.build("project", cwd=tmp_path, source_dir=root)
    assert result.fatal_errors
    assert not result.written


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_init_never_follows_source_symlinks(tmp_path, force, existing, run_cli: RunCLI):
    root = tmp_path / "inputs"
    root.mkdir()
    outside = tmp_path / "outside.md"
    if existing:
        outside.write_text("Preserve this file.", encoding="utf-8")
    path = root / "reviewer.md"
    path.symlink_to(outside)
    args = ["init", "reviewer", "--project", "--source-dir", str(root)]
    if force:
        args.append("--force")

    result = run_cli(*args, cwd=tmp_path)

    assert result.exit_code == 1
    assert "symlink" in result.stderr
    assert path.is_symlink()
    assert outside.exists() is existing
    if existing:
        assert outside.read_text(encoding="utf-8") == "Preserve this file."


@pytest.mark.parametrize("command", ["build", "list", "clean"])
@pytest.mark.parametrize("path", ['"bad\\0.md"', "~supagents-user-that-does-not-exist/agent.md"])
def test_invalid_output_paths_report_controlled_errors(tmp_path, command, path, run_cli: RunCLI):
    source(tmp_path / ".agents/supagents", f"---\nCLAUDE:\n  OUTPUT: {path}\n---\nReview.")
    result = run_cli(command, "--project", cwd=tmp_path)
    assert result.exit_code == 1
    assert "ERROR" in result.stderr
    assert not (tmp_path / ".claude").exists()


@pytest.mark.parametrize("field", ["global_path", "project_path", "filename_suffix"])
def test_config_rejects_invalid_filesystem_paths(tmp_path, field):
    path = tmp_path / "config.yaml"
    path.write_text(f'targets:\n  CLAUDE:\n    {field}: ".bad\\0path"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(path)


def test_init_reports_write_failure(tmp_path, run_cli: RunCLI):
    root = tmp_path / "inputs"
    root.write_text("This is a file, not a directory.", encoding="utf-8")
    result = run_cli("init", "reviewer", "--project", "--source-dir", str(root), cwd=tmp_path)
    assert result.exit_code == 1
    assert "ERROR" in result.stderr
    assert root.read_text(encoding="utf-8") == "This is a file, not a directory."
