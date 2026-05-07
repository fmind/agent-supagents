"""Tests for core.py — parsing, rendering, building."""

import time
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from supagents import core
from supagents.core import ParseError, parse_source, split_frontmatter
from tests.conftest import MakeSource

_yaml = YAML(typ="rt")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _cm(**items: object) -> CommentedMap:
    """Build a ``CommentedMap`` preserving insertion order."""
    cm = CommentedMap()
    for k, v in items.items():
        cm[k] = v
    return cm


def _write_md(path: Path, frontmatter: str, body: str = "body") -> Path:
    """Write a minimal ``--- frontmatter --- body`` markdown source to ``path``."""
    path.write_text(f"---\n{frontmatter}\n---\n{body}\n", encoding="utf-8")
    return path


# ---------- split_frontmatter ----------


@pytest.mark.parametrize(
    ("text", "expected_fm", "expected_body"),
    [
        pytest.param("---\nname: x\n---\nbody\n", "name: x", "body", id="basic"),
        pytest.param(
            "---\nname: x\n---\n\nbody text\n", "name: x", "body text", id="blank_line_after_close"
        ),
        pytest.param("---\n---\nbody\n", "", "body", id="empty_frontmatter"),
        pytest.param("---\r\nname: x\r\n---\r\nbody\r\n", "name: x", "body", id="crlf"),
        pytest.param(
            "---\nname: x\n---\nbody\n---\nmore\n",
            "name: x",
            "body\n---\nmore",
            id="body_with_dashes",
        ),
    ],
)
def test_split_frontmatter_valid(text: str, expected_fm: str, expected_body: str) -> None:
    fm, body = split_frontmatter(text)
    assert fm == expected_fm
    assert body == expected_body


@pytest.mark.parametrize(
    ("text", "match"),
    [
        pytest.param("name: x\n", "must begin", id="missing_open"),
        pytest.param("---\nname: x\nbody\n", "missing closing", id="missing_close"),
    ],
)
def test_split_frontmatter_invalid(text: str, match: str) -> None:
    with pytest.raises(ParseError, match=match):
        split_frontmatter(text)


# ---------- parse_source ----------


def test_parse_source_canonical_code_investigator(fixtures_dir: Path) -> None:
    src = parse_source(fixtures_dir / "code_investigator.md", fixtures_dir)
    assert src.name == "code_investigator"
    assert set(src.targets) == {"CLAUDE", "GEMINI", "COPILOT"}
    assert src.shared_frontmatter["name"] == "code_investigator"
    assert "description" in src.shared_frontmatter
    assert src.targets["CLAUDE"].frontmatter["model"] == "sonnet"
    assert src.targets["COPILOT"].append_body is not None
    assert "Copilot-specific" in src.targets["COPILOT"].append_body
    assert src.body.startswith("# Code Investigator Agent")
    assert not src.errors
    assert not src.warnings


def test_parse_source_claude_only(fixtures_dir: Path) -> None:
    src = parse_source(fixtures_dir / "claude_only.md", fixtures_dir)
    assert set(src.targets) == {"CLAUDE"}
    assert not src.warnings
    assert not src.errors


def test_parse_source_unknown_target_warns(fixtures_dir: Path) -> None:
    src = parse_source(fixtures_dir / "unknown_target.md", fixtures_dir)
    assert "CLAUDE" in src.targets
    assert "FOO" not in src.targets
    assert any("FOO" in w for w in src.warnings)


def test_parse_source_malformed_raises(fixtures_dir: Path) -> None:
    with pytest.raises(ParseError, match="invalid YAML"):
        parse_source(fixtures_dir / "malformed.md", fixtures_dir)


def test_parse_source_empty_body_raises(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "empty.md", "name: x", body="")
    with pytest.raises(ParseError, match="non-whitespace"):
        parse_source(p, tmp_path)


def test_parse_source_bad_filename_raises(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "Bad-Name.md", "name: x")
    with pytest.raises(ParseError, match="filename"):
        parse_source(p, tmp_path)


def test_parse_source_output_directive_must_be_string(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "agent.md", "name: agent\nCLAUDE:\n  OUTPUT: [not, a, string]")
    src = parse_source(p, tmp_path)
    assert "CLAUDE" not in src.targets
    assert any("OUTPUT" in e for e in src.errors)


def test_parse_source_unknown_directive_warns(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "agent.md", "name: agent\nCLAUDE:\n  WAT: hello")
    src = parse_source(p, tmp_path)
    assert "CLAUDE" in src.targets
    assert any("WAT" in w for w in src.warnings)


def test_parse_source_empty_target_block_emits(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "agent.md", "name: agent\nCLAUDE:")
    src = parse_source(p, tmp_path)
    assert "CLAUDE" in src.targets
    assert dict(src.targets["CLAUDE"].frontmatter) == {}


def test_parse_source_strips_utf8_bom(tmp_path: Path) -> None:
    p = tmp_path / "agent.md"
    p.write_text("﻿---\nname: x\nCLAUDE:\n  model: sonnet\n---\nbody\n", encoding="utf-8")
    src = parse_source(p, tmp_path)
    assert src.shared_frontmatter["name"] == "x"
    assert "CLAUDE" in src.targets


@pytest.mark.parametrize(
    "frontmatter",
    [
        pytest.param("", id="blank"),
        pytest.param("# only a comment", id="comments_only"),
    ],
)
def test_parse_source_empty_frontmatter_yields_no_targets(tmp_path: Path, frontmatter: str) -> None:
    src = parse_source(_write_md(tmp_path / "agent.md", frontmatter), tmp_path)
    assert dict(src.shared_frontmatter) == {}
    assert src.targets == {}


def test_parse_source_non_mapping_frontmatter_raises(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "agent.md", "- a\n- b")
    with pytest.raises(ParseError, match="must be a YAML mapping"):
        parse_source(p, tmp_path)


def test_parse_source_target_value_not_mapping_warns(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "agent.md", "name: agent\nCLAUDE: hello")
    src = parse_source(p, tmp_path)
    assert "CLAUDE" not in src.targets
    assert any("must be a YAML mapping" in w for w in src.warnings)


def test_parse_source_append_body_null_treated_as_empty(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "agent.md", "name: agent\nCLAUDE:\n  APPEND_BODY:")
    src = parse_source(p, tmp_path)
    assert src.targets["CLAUDE"].append_body == ""


def test_parse_source_append_body_non_string_warns(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "agent.md", "name: agent\nCLAUDE:\n  APPEND_BODY: [a, b]")
    src = parse_source(p, tmp_path)
    assert src.targets["CLAUDE"].append_body is None
    assert any("APPEND_BODY" in w for w in src.warnings)


def test_parse_source_non_string_top_level_key_warns(tmp_path: Path) -> None:
    # YAML allows integer keys at the top level; supagents must skip and warn.
    p = _write_md(tmp_path / "agent.md", "1: ignored\nname: agent\nCLAUDE:\n  model: sonnet")
    src = parse_source(p, tmp_path)
    assert "CLAUDE" in src.targets
    assert any("non-string top-level key" in w for w in src.warnings)


def test_parse_source_non_string_key_in_target_warns(tmp_path: Path) -> None:
    p = _write_md(tmp_path / "agent.md", "name: agent\nCLAUDE:\n  model: sonnet\n  1: ignored")
    src = parse_source(p, tmp_path)
    assert "CLAUDE" in src.targets
    assert any("non-string key" in w for w in src.warnings)


# ---------- render & helpers ----------


def test_marker_line_format() -> None:
    assert core.marker_line(Path("code_investigator.md")) == (
        "# Generated by supagents from code_investigator.md. Do not edit; edit the source instead."
    )


def test_render_places_marker_inside_frontmatter() -> None:
    rendered = core.render(Path("code_investigator.md"), _cm(name="x"), "body")
    lines = rendered.split("\n")
    assert lines[0] == "---"
    assert lines[1] == core.marker_line(Path("code_investigator.md"))
    fm_text = rendered.split("---\n", 2)[1]
    assert _yaml.load(fm_text)["name"] == "x"


def test_has_marker_detects_supagents_files() -> None:
    rendered = core.render(Path("x.md"), _cm(name="x"), "body")
    assert core.has_marker(rendered)
    assert not core.has_marker("---\nname: x\n---\nbody\n")
    assert not core.has_marker("")


def test_has_marker_finds_marker_after_reformatting() -> None:
    # Another tool may sort YAML keys, moving the marker off line 2.
    text = f"---\nname: x\n{core.marker_line(Path('x.md'))}\nmodel: sonnet\n---\n\nbody\n"
    assert core.has_marker(text)


def test_has_marker_stops_at_frontmatter_close() -> None:
    # A marker-shaped line in the body must not be detected as ours.
    text = f"---\nname: x\n---\n\n{core.marker_line(Path('x.md'))}\n"
    assert not core.has_marker(text)


def test_has_marker_returns_false_when_frontmatter_unclosed() -> None:
    # Walks every line and never finds a closing '---' or our marker.
    assert not core.has_marker("---\nname: x\nmodel: sonnet\n")


@pytest.mark.parametrize(
    ("shared", "target", "expected_keys", "expected_overrides"),
    [
        pytest.param(
            _cm(name="x", description="desc"),
            _cm(model="sonnet", tools="Read, Write"),
            ["name", "description", "model", "tools"],
            {},
            id="shared_first_then_target_only",
        ),
        pytest.param(
            _cm(name="x", tools="shared-tools"),
            _cm(tools="target-tools"),
            ["name", "tools"],
            {"tools": "target-tools"},
            id="target_overrides_shared_keeps_position",
        ),
    ],
)
def test_compute_frontmatter(
    shared: CommentedMap,
    target: CommentedMap,
    expected_keys: list[str],
    expected_overrides: dict[str, object],
) -> None:
    out = core.compute_frontmatter(shared, target)
    assert list(out.keys()) == expected_keys
    for k, v in expected_overrides.items():
        assert out[k] == v


@pytest.mark.parametrize(
    ("body", "append", "expected"),
    [
        pytest.param("body\n", None, "body\n", id="no_append"),
        pytest.param("body", "extra", "body\n\nextra", id="with_append"),
        pytest.param("body\n", "\n\nextra\n\n", "body\n\nextra", id="strips_surrounding_newlines"),
        pytest.param("body\n", "\n\n", "body\n", id="append_strips_to_empty"),
    ],
)
def test_compute_body(body: str, append: str | None, expected: str) -> None:
    assert core.compute_body(body, append) == expected


# ---------- atomic_write ----------


def test_atomic_write_unchanged_returns_false(tmp_path: Path) -> None:
    p = tmp_path / "out.md"
    assert core.atomic_write(p, "hello\n") is True
    mtime_before = p.stat().st_mtime_ns
    time.sleep(0.01)
    assert core.atomic_write(p, "hello\n") is False
    assert p.stat().st_mtime_ns == mtime_before


def test_atomic_write_changed_returns_true(tmp_path: Path) -> None:
    p = tmp_path / "out.md"
    core.atomic_write(p, "hello\n")
    assert core.atomic_write(p, "world\n") is True
    assert _read(p) == "world\n"


# ---------- build ----------


def test_build_canonical_code_investigator_three_targets(
    ci_workspace: Path, ci_outputs: list[Path]
) -> None:
    summary = core.build(scope="project", cwd=ci_workspace)
    assert not summary.fatal_errors
    assert len(summary.plans) == 3
    assert {p.target_name for p in summary.plans} == {"CLAUDE", "GEMINI", "COPILOT"}
    for path in ci_outputs:
        assert path.exists(), path
        assert core.has_marker(_read(path))


def test_build_outputs_have_yaml_frontmatter(ci_workspace: Path) -> None:
    core.build(scope="project", cwd=ci_workspace)
    text = _read(ci_workspace / ".claude" / "agents" / "code_investigator.md")
    assert text.startswith("---\n")
    parts = text.split("---\n", 2)
    assert len(parts) >= 3
    fm = _yaml.load(parts[1])
    keys = list(fm.keys())
    assert keys[0] == "name"
    assert "description" in keys
    assert "model" in keys
    assert fm["model"] == "sonnet"


def test_build_copilot_uses_agent_md_suffix(ci_workspace: Path) -> None:
    core.build(scope="project", cwd=ci_workspace)
    copilot = ci_workspace / ".github" / "agents" / "code_investigator.agent.md"
    assert copilot.exists()
    assert "## Copilot-specific" in _read(copilot)


def test_build_idempotent_zero_writes_second_run(
    ci_workspace: Path, ci_outputs: list[Path]
) -> None:
    core.build(scope="project", cwd=ci_workspace)
    mtimes = {p: p.stat().st_mtime_ns for p in ci_outputs}
    time.sleep(0.01)
    summary2 = core.build(scope="project", cwd=ci_workspace)
    assert summary2.written == []
    assert len(summary2.skipped_unchanged) == 3
    for p, mtime in mtimes.items():
        assert p.stat().st_mtime_ns == mtime, f"mtime changed for {p}"


def test_build_dry_run_no_writes(ci_workspace: Path) -> None:
    summary = core.build(scope="project", cwd=ci_workspace, dry_run=True)
    assert len(summary.plans) == 3
    # written/skipped_unchanged still reflect what *would* change so callers
    # can detect drift in dry-run mode; no file is actually created.
    assert len(summary.written) == 3
    assert summary.skipped_unchanged == []
    assert not (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()


def test_build_dry_run_reports_unchanged_after_real_build(ci_workspace: Path) -> None:
    core.build(scope="project", cwd=ci_workspace)
    summary = core.build(scope="project", cwd=ci_workspace, dry_run=True)
    assert summary.written == []
    assert len(summary.skipped_unchanged) == 3


def test_build_unknown_target_does_not_block_known(
    tmp_path: Path, make_source: MakeSource, fixtures_dir: Path
) -> None:
    make_source("mystery.md", (fixtures_dir / "unknown_target.md").read_text(encoding="utf-8"))
    summary = core.build(scope="project", cwd=tmp_path)
    assert (tmp_path / ".claude" / "agents" / "mystery.md").exists()
    warnings = [w for src in summary.sources for w in src.warnings]
    assert any("FOO" in w for w in warnings)


def test_build_malformed_skipped_others_succeed(mixed_workspace: Path) -> None:
    summary = core.build(scope="project", cwd=mixed_workspace)
    assert any("malformed.md" in str(p) for p, _ in summary.fatal_errors)
    assert (mixed_workspace / ".claude" / "agents" / "code_investigator.md").exists()
    assert (mixed_workspace / ".claude" / "agents" / "claude_only.md").exists()


def test_build_output_directive_overrides_path(tmp_path: Path, make_source: MakeSource) -> None:
    custom = tmp_path / "custom.md"
    make_source(
        "agent.md",
        f"---\nname: agent\ndescription: x\n"
        f"CLAUDE:\n  model: sonnet\n  OUTPUT: {custom}\n---\nbody\n",
    )
    summary = core.build(scope="project", cwd=tmp_path)
    assert summary.plans[0].output_path == custom
    assert custom.exists()
    assert not (tmp_path / ".claude" / "agents" / "agent.md").exists()


def test_build_output_directive_relative_to_source_dir(
    tmp_path: Path, make_source: MakeSource
) -> None:
    make_source(
        "agent.md",
        "---\nname: agent\nCLAUDE:\n  model: sonnet\n  OUTPUT: ../custom.md\n---\nbody\n",
    )
    core.build(scope="project", cwd=tmp_path)
    assert (tmp_path / ".agents" / "custom.md").exists()


@pytest.mark.parametrize(
    ("relative_to_parent", "should_warn"),
    [
        pytest.param(True, True, id="outside_scope_warns"),
        pytest.param(False, False, id="inside_scope_no_warn"),
    ],
)
def test_build_output_directive_scope_check(
    tmp_path: Path,
    make_source: MakeSource,
    relative_to_parent: bool,
    should_warn: bool,
) -> None:
    base = tmp_path.parent if relative_to_parent else tmp_path
    target_path = base / "supagents-scope-test.md"
    make_source(
        "agent.md",
        f"---\nname: agent\nCLAUDE:\n  model: sonnet\n  OUTPUT: {target_path}\n---\nbody\n",
    )
    summary = core.build(scope="project", cwd=tmp_path, dry_run=True)
    warnings = [w for src in summary.sources for w in src.warnings]
    assert any("resolves outside" in w for w in warnings) is should_warn


def test_build_target_filter_emits_only_selected(ci_workspace: Path) -> None:
    summary = core.build(scope="project", cwd=ci_workspace, targets={"CLAUDE"})
    assert {p.target_name for p in summary.plans} == {"CLAUDE"}
    assert (ci_workspace / ".claude" / "agents" / "code_investigator.md").exists()
    assert not (ci_workspace / ".gemini" / "agents" / "code_investigator.md").exists()
    assert not (ci_workspace / ".github" / "agents" / "code_investigator.agent.md").exists()


def test_find_orphans_target_filter(ci_workspace: Path) -> None:
    core.build(scope="project", cwd=ci_workspace)
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    orphans = core.find_orphans(scope="project", cwd=ci_workspace, targets={"CLAUDE"})
    assert {p.name for p in orphans} == {"code_investigator.md"}
    # Other targets' orphans are still on disk but not listed.
    assert (ci_workspace / ".github" / "agents" / "code_investigator.agent.md").exists()


def test_collect_sources_is_public(ci_workspace: Path) -> None:
    from supagents.config import Config

    sources, fatal = core.collect_sources("project", Config.load(), ci_workspace)
    assert [s.name for s in sources] == ["code_investigator"]
    assert fatal == []


def test_find_orphans_after_source_deletion(ci_workspace: Path) -> None:
    core.build(scope="project", cwd=ci_workspace)
    handwritten = ci_workspace / ".claude" / "agents" / "manual.md"
    handwritten.write_text("---\nname: manual\n---\nhand-written\n", encoding="utf-8")
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    orphans = core.find_orphans(scope="project", cwd=ci_workspace)
    assert {p.name for p in orphans} == {"code_investigator.md", "code_investigator.agent.md"}
    assert handwritten not in orphans
    assert handwritten.exists()


def test_find_orphans_skips_non_files(ci_workspace: Path) -> None:
    core.build(scope="project", cwd=ci_workspace)
    # A directory whose name matches the *.md glob must not be returned as an orphan.
    (ci_workspace / ".claude" / "agents" / "stub.md").mkdir()
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    orphans = core.find_orphans(scope="project", cwd=ci_workspace)
    assert all(o.is_file() for o in orphans)
    assert not any(o.name == "stub.md" for o in orphans)


def test_clean_preserves_handwritten_files(ci_workspace: Path) -> None:
    core.build(scope="project", cwd=ci_workspace)
    manual = ci_workspace / ".claude" / "agents" / "manual.md"
    manual.write_text("---\nname: manual\n---\nhand-written\n", encoding="utf-8")
    (ci_workspace / ".agents" / "supagents" / "code_investigator.md").unlink()
    for o in core.find_orphans(scope="project", cwd=ci_workspace):
        o.unlink()
    assert manual.exists()


def test_render_ends_with_single_newline(ci_workspace: Path, ci_outputs: list[Path]) -> None:
    core.build(scope="project", cwd=ci_workspace)
    for path in ci_outputs:
        text = _read(path)
        assert text.endswith("\n")
        assert not text.endswith("\n\n")


def test_directives_stripped_from_output(ci_workspace: Path) -> None:
    core.build(scope="project", cwd=ci_workspace)
    copilot = _read(ci_workspace / ".github" / "agents" / "code_investigator.agent.md")
    assert "APPEND_BODY" not in copilot
    assert "OUTPUT" not in copilot.split("---\n", 2)[1]
