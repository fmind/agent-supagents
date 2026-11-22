"""Tests for cli.py — streams, exit codes, flags, JSON, scope, and safety."""

import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

from supagents import cli, core
from tests.conftest import MakeSource, RunCLI


def test_bare_command_exits_2_with_stderr_usage(run_cli: RunCLI) -> None:
    result = run_cli()
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "usage:" in result.stderr.lower()


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_root_and_subcommand_help_side_effect_free(
    run_cli: RunCLI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, flag: str
) -> None:
    # Broken user config must never interfere with -h/--help or --version.
    bad_cfg = tmp_path / "supagents" / "config.yaml"
    bad_cfg.parent.mkdir(parents=True)
    bad_cfg.write_text("targets: {broken: [\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    root = run_cli(flag)
    assert root.exit_code == 0
    assert root.stderr == ""
    for cmd in ("build", "check", "clean", "init", "list"):
        assert cmd in root.stdout
        sub = run_cli(cmd, flag)
        assert sub.exit_code == 0
        assert sub.stderr == ""
        assert cmd in sub.stdout


def test_version_flag_side_effect_free(
    run_cli: RunCLI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad_cfg = tmp_path / "supagents" / "config.yaml"
    bad_cfg.parent.mkdir(parents=True)
    bad_cfg.write_text("not: [valid\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    result = run_cli("--version")
    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.stdout.startswith("supagents ")


def test_module_invocation_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "supagents", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
        stdin=subprocess.DEVNULL,
    )
    assert result.stdout.startswith("supagents ")
    assert result.stderr == ""


def test_sigint_exits_130_and_broken_pipe_exits_0(
    run_cli: RunCLI, monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    monkeypatch.setattr(
        core,
        "build",
        lambda **_kw: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    interrupted = run_cli("build", "--project", cwd=ci_workspace)
    assert interrupted.exit_code == 130

    monkeypatch.setattr(
        core,
        "build",
        lambda **_kw: (_ for _ in ()).throw(BrokenPipeError()),
    )
    broken = run_cli("build", "--project", cwd=ci_workspace)
    assert broken.exit_code == 0
    assert "Traceback" not in broken.stderr


def test_broken_pipe_preserves_failure_exit_code_on_check(
    run_cli: RunCLI, monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    # Unbuilt workspace causes check to fail (drift). A BrokenPipeError while
    # writing stdout must still exit 1 rather than masking drift with exit 0.
    monkeypatch.setattr(cli, "_out", lambda *_a, **_k: (_ for _ in ()).throw(BrokenPipeError()))
    result = run_cli("check", "--project", "--diff", cwd=ci_workspace)
    assert result.exit_code == 1
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("flag", ["--source-dir", "--config"])
@pytest.mark.parametrize("bad_value", ["", "   ", "bad\x00path"])
def test_empty_or_nul_path_flags_exit_2(
    run_cli: RunCLI, tmp_path: Path, flag: str, bad_value: str
) -> None:
    result = run_cli("clean", "--project", flag, bad_value, cwd=tmp_path)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "non-empty" in result.stderr


def test_check_json_reports_orphan_scan_skipped(
    run_cli: RunCLI, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("agent.md", "---\nCLAUDE: {}\nTYPO: {}\n---\nBody.\n")
    assert run_cli("build", "--project", cwd=tmp_path).exit_code == 0
    checked = run_cli("check", "--project", "--json", cwd=tmp_path)
    assert checked.exit_code == 0, checked.output
    data = json.loads(checked.stdout)
    assert data["orphan_scan_skipped"] is True
    assert "Orphan scan skipped" in checked.stderr


def test_check_json_reports_orphan_scan_skipped_on_source_errors(
    run_cli: RunCLI, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("agent.md", "---\nCODEX: {}\n---\nBody.\n")
    checked = run_cli("check", "--project", "--json", cwd=tmp_path)
    assert checked.exit_code == 1
    data = json.loads(checked.stdout)
    assert data["ok"] is False
    assert data["orphan_scan_skipped"] is True
    assert data["errors"]
    assert "Orphan scan skipped" in checked.stderr


def test_clean_completes_all_unlinks_even_when_stdout_pipe_breaks(
    run_cli: RunCLI, monkeypatch: pytest.MonkeyPatch, ci_workspace: Path, ci_outputs: list[Path]
) -> None:
    assert run_cli("build", "--project", cwd=ci_workspace).exit_code == 0
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    monkeypatch.setattr(cli, "_out", lambda *_a, **_k: (_ for _ in ()).throw(BrokenPipeError()))

    result = run_cli("clean", "--project", cwd=ci_workspace)
    assert result.exit_code == 0
    assert "Traceback" not in result.stderr
    for path in ci_outputs:
        assert not path.exists(), path


def test_tty_color_honors_no_color_term_dumb_and_json(
    run_cli: RunCLI, ci_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeTTY(StringIO):
        def isatty(self) -> bool:
            return True

    def invoke_tty(*args: str) -> tuple[int, str, str]:
        out_tty, err_tty = FakeTTY(), FakeTTY()
        monkeypatch.setattr(sys, "stdout", out_tty)
        monkeypatch.setattr(sys, "stderr", err_tty)
        monkeypatch.chdir(ci_workspace)
        code = 0
        try:
            cli.main(list(args))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        return code, out_tty.getvalue(), err_tty.getvalue()

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    code, out, _ = invoke_tty("build", "--project", "--dry-run")
    assert code == 0
    assert "\033[" in out

    code, out, _ = invoke_tty("build", "--project", "--dry-run", "--json")
    assert code == 0
    assert "\033[" not in out
    assert json.loads(out)["ok"] is True

    monkeypatch.setenv("NO_COLOR", "1")
    code, out, _ = invoke_tty("build", "--project", "--dry-run")
    assert code == 0
    assert "\033[" not in out

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    code, out, _ = invoke_tty("build", "--project", "--dry-run")
    assert code == 0
    assert "\033[" not in out


def test_broken_cwd_and_broken_stderr_pipe_handled_cleanly(
    run_cli: RunCLI, ci_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        Path, "cwd", classmethod(lambda _cls: (_ for _ in ()).throw(OSError("cwd gone")))
    )
    bad_cwd = run_cli("list", "--project")
    assert bad_cwd.exit_code == 1
    assert "cannot determine working directory" in bad_cwd.stderr
    monkeypatch.undo()

    class BrokenStderr(StringIO):
        def write(self, _s: str) -> int:
            raise BrokenPipeError("closed stderr")

    monkeypatch.setattr(sys, "stderr", BrokenStderr())
    monkeypatch.chdir(ci_workspace)
    cli.main(["build", "--project", "--dry-run"])


def test_init_rejects_existing_directory_even_with_force_and_dry_run(
    run_cli: RunCLI, tmp_path: Path, project_source_dir: Path
) -> None:
    (project_source_dir / "reviewer.md").mkdir()
    result = run_cli("init", "reviewer", "--project", "--force", "--dry-run", cwd=tmp_path)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "not a regular file" in result.stderr


def test_build_mutually_exclusive_checked_before_config_load(
    run_cli: RunCLI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_cfg = tmp_path / "supagents" / "config.yaml"
    bad_cfg.parent.mkdir(parents=True)
    bad_cfg.write_text("targets: {broken: [\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    result = run_cli("build", "--project", "--dry-run", "--check", cwd=tmp_path)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "supagents build" in result.stderr


def test_build_acceptance_canonical(
    run_cli: RunCLI, ci_workspace: Path, ci_outputs: list[Path]
) -> None:
    result = run_cli("build", "--project", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    for path in ci_outputs:
        assert path.exists(), path


@pytest.mark.parametrize("flag", ["--dry-run", "-n"])
def test_build_dry_run_no_write(run_cli: RunCLI, ci_workspace: Path, flag: str) -> None:
    result = run_cli("build", "--project", flag, cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert not (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_build_global_and_project_mutually_exclusive(run_cli: RunCLI, tmp_path: Path) -> None:
    result = run_cli("build", "--global", "--project", cwd=tmp_path)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "mutually exclusive" in result.stderr


def test_clean_removes_orphans(run_cli: RunCLI, ci_workspace: Path, ci_outputs: list[Path]) -> None:
    run_cli("build", "--project", cwd=ci_workspace)
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    result = run_cli("clean", "--project", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    for path in ci_outputs:
        assert not path.exists(), path


@pytest.mark.parametrize("flag", ["--dry-run", "-n"])
def test_clean_dry_run_keeps_files(run_cli: RunCLI, ci_workspace: Path, flag: str) -> None:
    run_cli("build", "--project", cwd=ci_workspace)
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    result = run_cli("clean", "--project", flag, cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_clean_auto_global_requires_consent_unless_yes_or_explicit(
    run_cli: RunCLI, isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_src = isolated_home / ".agents" / "supagents"
    global_src.mkdir(parents=True)
    src = global_src / "agent.md"
    src.write_text("---\nname: agent\nCLAUDE: {}\n---\nBody.\n", encoding="utf-8")
    assert run_cli("build", "--global", cwd=tmp_path).exit_code == 0
    orphan = isolated_home / ".claude" / "agents" / "agent.md"
    assert orphan.is_file()
    src.unlink()

    # Non-TTY auto-detected global clean refuses deletion.
    refused = run_cli("clean", "--no-input", cwd=tmp_path)
    assert refused.exit_code == 1
    assert refused.stdout == ""
    assert "refusing to remove" in refused.stderr
    assert orphan.is_file()

    # Interactive TTY 'n' aborts safely.
    class FakeTTY(StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", FakeTTY("n\n"))
    aborted = run_cli("clean", cwd=tmp_path)
    assert aborted.exit_code == 1
    assert str(orphan) in aborted.stderr
    assert "Aborted." in aborted.stderr
    assert orphan.is_file()

    # --yes deletes cleanly under auto-detected global scope.
    confirmed = run_cli("clean", "--yes", cwd=tmp_path)
    assert confirmed.exit_code == 0, confirmed.output
    assert not orphan.exists()


def test_clean_surfaces_causal_source_diagnostics(
    run_cli: RunCLI, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("bad_agent.md", "---\nCLAUDE: {}\nTYPO: {}\n---\nBody.\n")
    result = run_cli("clean", "--project", cwd=tmp_path)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "bad_agent.md" in result.stderr
    assert "TYPO" in result.stderr
    assert "supagents check --strict" in result.stderr


def test_scope_auto_detect_project(run_cli: RunCLI, ci_workspace: Path) -> None:
    result = run_cli("build", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_scope_auto_detect_global_when_no_project_dir(run_cli: RunCLI, tmp_path: Path) -> None:
    result = run_cli("build", cwd=tmp_path)
    assert result.exit_code == 0, result.output


def test_build_global_flag_explicit(run_cli: RunCLI, tmp_path: Path) -> None:
    result = run_cli("build", "--global", cwd=tmp_path)
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    ("flags", "expected_unchanged_count"),
    [
        pytest.param((), 1, id="quiet"),
        pytest.param(("--verbose",), 4, id="verbose"),
    ],
)
def test_build_twice_reports_unchanged(
    run_cli: RunCLI,
    ci_workspace: Path,
    flags: tuple[str, ...],
    expected_unchanged_count: int,
) -> None:
    run_cli("build", "--project", cwd=ci_workspace)
    result = run_cli("build", "--project", *flags, cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert result.stdout.count("unchanged") == expected_unchanged_count
    assert "wrote" not in result.stdout


def test_build_malformed_source_exits_1_with_clean_stdout(
    run_cli: RunCLI, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("bad.md", "---\nname: bad: invalid: [\n---\nbody\n")
    result = run_cli("build", "--project", cwd=tmp_path)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "ERROR" in result.stderr


def test_build_target_error_exits_1(
    run_cli: RunCLI, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("agent.md", "---\nname: agent\nCLAUDE:\n  OUTPUT: [not, a, string]\n---\nbody\n")
    result = run_cli("build", "--project", cwd=tmp_path)
    assert result.exit_code == 1


def test_build_prints_source_warnings(
    run_cli: RunCLI, tmp_path: Path, make_source: MakeSource
) -> None:
    make_source(
        "agent.md",
        "---\nname: agent\nCLAUDE:\n  model: sonnet\nFOO:\n  bar: baz\n---\nbody\n",
    )
    result = run_cli("build", "--project", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert "WARN" in result.stderr
    assert "FOO" in result.stderr


def test_build_preserves_brackets_and_emoji_shortcodes_verbatim(
    run_cli: RunCLI, tmp_path: Path
) -> None:
    workspace = tmp_path / "[draft]"
    (workspace / ".agents" / "supagents").mkdir(parents=True)
    (workspace / ".agents" / "supagents" / "agent.md").write_text(
        '---\nname: agent\n"[/BOLD]": 1\nCLAUDE: {}\n---\nStatus: :warning: :rocket:\n',
        encoding="utf-8",
    )
    diff_res = run_cli("build", "--project", "--diff", cwd=workspace)
    assert diff_res.exit_code == 0, diff_res.output
    assert "+Status: :warning: :rocket:" in diff_res.stdout
    assert "⚠" not in diff_res.stdout
    assert "🚀" not in diff_res.stdout

    build_res = run_cli("build", "--project", cwd=workspace)
    assert build_res.exit_code == 0, build_res.output
    assert "'[/BOLD]'" in build_res.stderr
    assert str(workspace / ".claude" / "agents" / "agent.md") in build_res.stdout


def test_no_color_and_term_dumb_emit_no_ansi(
    run_cli: RunCLI, ci_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    res1 = run_cli("build", "--project", cwd=ci_workspace)
    assert "\033[" not in res1.stdout
    assert "\033[" not in res1.stderr

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    res2 = run_cli("check", "--project", cwd=ci_workspace)
    assert "\033[" not in res2.stdout
    assert "\033[" not in res2.stderr


def test_json_and_quiet_modes_across_commands(
    run_cli: RunCLI, tmp_path: Path, make_source: MakeSource
) -> None:
    init_res = run_cli("init", "reviewer", "--project", "-t", "claude", "--json", cwd=tmp_path)
    assert init_res.exit_code == 0, init_res.output
    init_data = json.loads(init_res.stdout)
    assert init_data["ok"] is True
    assert init_data["command"] == "init"
    assert init_data["targets"] == ["CLAUDE"]
    assert init_res.stderr == ""

    list_res = run_cli("list", "--project", "--json", cwd=tmp_path)
    assert list_res.exit_code == 0
    list_data = json.loads(list_res.stdout)
    assert len(list_data["items"]) == 1
    assert list_data["items"][0]["target"] == "CLAUDE"

    build_res = run_cli("build", "--project", "--json", cwd=tmp_path)
    assert build_res.exit_code == 0
    build_data = json.loads(build_res.stdout)
    assert build_data["ok"] is True
    assert len(build_data["written"]) == 1

    check_res = run_cli("check", "--project", "--strict", "--json", cwd=tmp_path)
    assert check_res.exit_code == 0
    assert json.loads(check_res.stdout)["ok"] is True

    quiet_res = run_cli("check", "--project", "--strict", "--quiet", cwd=tmp_path)
    assert quiet_res.exit_code == 0
    assert quiet_res.stdout == ""
    assert quiet_res.stderr == ""

    (tmp_path / ".agents" / "supagents" / "reviewer.md").unlink()
    clean_res = run_cli("clean", "--project", "--json", cwd=tmp_path)
    assert clean_res.exit_code == 0
    assert len(json.loads(clean_res.stdout)["removed"]) == 1

    # Fatal error under --json leaves stdout empty.
    make_source("bad.md", "---\nname: [\n---\nbody\n")
    bad_res = run_cli("build", "--project", "--json", cwd=tmp_path)
    assert bad_res.exit_code == 1
    assert bad_res.stdout == ""
    assert "ERROR" in bad_res.stderr


def test_cli_expands_tilde_in_config_and_source_dir(
    run_cli: RunCLI, tmp_path: Path, isolated_home: Path
) -> None:
    src_dir = isolated_home / "supagents-src"
    src_dir.mkdir()
    (src_dir / "agent.md").write_text("---\nname: agent\nCLAUDE: {}\n---\nbody\n", encoding="utf-8")
    cfg = isolated_home / "supagents-cfg.yaml"
    cfg.write_text("targets:\n  claude:\n    project_path: .custom-claude\n", encoding="utf-8")

    result = run_cli(
        "build",
        "--project",
        "--config",
        "~/supagents-cfg.yaml",
        "--source-dir",
        "~/supagents-src",
        cwd=tmp_path,
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".custom-claude" / "agent.md").is_file()


def test_clean_nothing_to_clean(run_cli: RunCLI, tmp_path: Path, project_source_dir: Path) -> None:
    result = run_cli("clean", "--project", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert "Nothing to clean" in result.stdout


def test_clean_unlink_failure_exits_1(
    run_cli: RunCLI, monkeypatch: pytest.MonkeyPatch, ci_workspace: Path
) -> None:
    run_cli("build", "--project", cwd=ci_workspace)
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()

    real_unlink = Path.unlink

    def failing_unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name.endswith(".md") and "claude" in str(self):
            raise OSError("simulated permission denied")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    result = run_cli("clean", "--project", cwd=ci_workspace)
    assert result.exit_code == 1


def test_build_check_exits_1_on_drift(run_cli: RunCLI, ci_workspace: Path) -> None:
    result = run_cli("build", "--project", "--check", cwd=ci_workspace)
    assert result.exit_code == 1, result.output
    assert not (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_build_check_exits_0_when_in_sync(run_cli: RunCLI, ci_workspace: Path) -> None:
    run_cli("build", "--project", cwd=ci_workspace)
    result = run_cli("build", "--project", "--check", cwd=ci_workspace)
    assert result.exit_code == 0, result.output


def test_build_check_and_dry_run_mutually_exclusive(run_cli: RunCLI, ci_workspace: Path) -> None:
    result = run_cli("build", "--project", "--check", "--dry-run", cwd=ci_workspace)
    assert result.exit_code == 2
    assert result.stdout == ""


def test_build_target_filter_skips_others(run_cli: RunCLI, ci_workspace: Path) -> None:
    result = run_cli("build", "--project", "--target", "claude", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()
    assert not (ci_workspace / ".gemini" / "agents" / "code_investigator.md").exists()


def test_build_target_unknown_rejected(run_cli: RunCLI, ci_workspace: Path) -> None:
    result = run_cli("build", "--project", "--target", "WAT", cwd=ci_workspace)
    assert result.exit_code == 2
    assert result.stdout == ""


def test_clean_target_filter_only_removes_selected(run_cli: RunCLI, ci_workspace: Path) -> None:
    run_cli("build", "--project", cwd=ci_workspace)
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    result = run_cli("clean", "--project", "--target", "CLAUDE", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert not (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()
    assert (ci_workspace / ".github" / "agents" / "code_investigator.agent.md").exists()


def test_build_config_flag_redirects_output(run_cli: RunCLI, ci_workspace: Path) -> None:
    cfg = ci_workspace / "custom.yaml"
    cfg.write_text(
        "targets:\n  claude:\n    project_path: .alt-claude/agents\n",
        encoding="utf-8",
    )
    result = run_cli(
        "build", "--project", "--config", str(cfg), "--target", "CLAUDE", cwd=ci_workspace
    )
    assert result.exit_code == 0, result.output
    assert (ci_workspace / ".alt-claude" / "agents" / "code_investigator.md").exists()
    assert not (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_build_malformed_config_yaml_exits_cleanly(run_cli: RunCLI, ci_workspace: Path) -> None:
    cfg = ci_workspace / "bad.yaml"
    cfg.write_text("targets: {claude: [\n", encoding="utf-8")
    result = run_cli("build", "--project", "--config", str(cfg), cwd=ci_workspace)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "invalid YAML" in result.stderr


def test_init_scaffolds_source_and_supports_dry_run(run_cli: RunCLI, tmp_path: Path) -> None:
    dry = run_cli("init", "reviewer", "--project", "--dry-run", cwd=tmp_path)
    assert dry.exit_code == 0, dry.output
    src = tmp_path / ".agents" / "supagents" / "reviewer.md"
    assert not src.exists()
    assert "would create" in dry.stdout

    result = run_cli("init", "reviewer", "--project", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert src.exists()
    text = src.read_text(encoding="utf-8")
    assert "name: reviewer" in text
    assert "# Reviewer" in text
    for block in ("CLAUDE:", "GEMINI:", "COPILOT:", "CURSOR:", "OPENCODE:", "KILO:"):
        assert block in text, block


def test_init_output_builds_nine_targets(run_cli: RunCLI, tmp_path: Path) -> None:
    run_cli("init", "reviewer", "--project", cwd=tmp_path)
    result = run_cli("build", "--project", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    expected = [
        tmp_path / ".agents/agents/reviewer.md",
        tmp_path / ".codex/agents/reviewer.toml",
        tmp_path / ".grok/agents/reviewer.md",
        tmp_path / ".claude" / "agents" / "reviewer.md",
        tmp_path / ".gemini" / "agents" / "reviewer.md",
        tmp_path / ".github" / "agents" / "reviewer.agent.md",
        tmp_path / ".cursor" / "agents" / "reviewer.md",
        tmp_path / ".opencode" / "agents" / "reviewer.md",
        tmp_path / ".kilo" / "agents" / "reviewer.md",
    ]
    for path in expected:
        assert path.exists(), path


def test_init_strips_md_suffix(run_cli: RunCLI, tmp_path: Path) -> None:
    result = run_cli("init", "reviewer.md", "--project", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".agents" / "supagents" / "reviewer.md").exists()


def test_init_rejects_invalid_name(run_cli: RunCLI, tmp_path: Path) -> None:
    result = run_cli("init", "Bad-Name", "--project", cwd=tmp_path)
    assert result.exit_code == 2
    assert result.stdout == ""


def test_init_refuses_existing_unless_force(
    run_cli: RunCLI,
    tmp_path: Path,
    make_source: MakeSource,
    project_source_dir: Path,
) -> None:
    make_source("reviewer.md", "existing\n")
    result = run_cli("init", "reviewer", "--project", cwd=tmp_path)
    assert result.exit_code == 1
    result = run_cli("init", "reviewer", "--project", "--force", cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert "name: reviewer" in (project_source_dir / "reviewer.md").read_text(encoding="utf-8")


def test_list_shows_sources_and_targets(run_cli: RunCLI, ci_workspace: Path) -> None:
    result = run_cli("list", "--project", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert "code_investigator" in result.stdout
    assert "CLAUDE" in result.stdout
    assert "GEMINI" in result.stdout
    assert "COPILOT" in result.stdout


def test_list_preserves_long_output_paths_without_truncation(
    run_cli: RunCLI, tmp_path: Path
) -> None:
    workspace = tmp_path / ("deep" * 30)
    (workspace / ".agents" / "supagents").mkdir(parents=True)
    (workspace / ".agents" / "supagents" / "agent.md").write_text(
        "---\nname: agent\nCLAUDE: {}\n---\nbody\n", encoding="utf-8"
    )
    result = run_cli("list", "--project", cwd=workspace)
    assert result.exit_code == 0, result.output
    assert "…" not in result.stdout
    assert str(workspace / ".claude" / "agents" / "agent.md") in result.stdout


def test_list_empty_and_filtered_empty(
    run_cli: RunCLI, tmp_path: Path, project_source_dir: Path, make_source: MakeSource
) -> None:
    empty = run_cli("list", "--project", cwd=tmp_path)
    assert empty.exit_code == 0, empty.output
    assert "No sources" in empty.stdout

    make_source("agent.md", "---\nname: agent\nCLAUDE: {}\n---\nbody\n")
    filtered = run_cli("list", "--project", "--target", "CODEX", cwd=tmp_path)
    assert filtered.exit_code == 0
    assert "Source" not in filtered.stdout
    assert "No sources" in filtered.stdout


def test_list_target_filter(run_cli: RunCLI, ci_workspace: Path) -> None:
    result = run_cli("list", "--project", "--target", "CLAUDE", cwd=ci_workspace)
    assert result.exit_code == 0, result.output
    assert "CLAUDE" in result.stdout
    assert "GEMINI" not in result.stdout
    assert "COPILOT" not in result.stdout


def test_list_prints_fatal_errors(run_cli: RunCLI, tmp_path: Path, make_source: MakeSource) -> None:
    make_source("bad.md", "---\nname: bad: invalid: [\n---\nbody\n")
    result = run_cli("list", "--project", cwd=tmp_path)
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "ERROR" in result.stderr
