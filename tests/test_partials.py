"""Tests for _*.md partial inheritance, DAG linearization, and recursion guards."""

from dataclasses import replace
from pathlib import Path

import pytest
from ruamel.yaml.comments import CommentedMap

from supagents import core, sources
from supagents.config import DEFAULT_TARGETS, Config
from supagents.sources import ParseError, parse_source
from tests.conftest import MakeSource


@pytest.mark.parametrize("ref", ["_reviewer", "_reviewer.md"], ids=["stem", "with_ext"])
def test_partial_inheritance_single_and_body_slot(
    tmp_path: Path, make_source: MakeSource, ref: str
) -> None:
    make_source(
        "_reviewer.md",
        "---\n"
        "AGY:\n"
        "  subagent: true\n"
        "  model: inherit\n"
        "  tools: [view_file]\n"
        "CLAUDE:\n"
        "  model: inherit\n"
        "  APPEND_BODY: Follow output contract.\n"
        "CODEX:\n"
        "  sandbox_mode: read-only\n"
        "---\n"
        "{{BODY}}\n\n"
        "## Output Contract\n"
        "Return VERDICT.\n",
    )
    make_source(
        "security.md",
        f"---\n"
        f"extends: {ref}\n"
        f"name: security\n"
        f"description: Audit security\n"
        f"AGY:\n"
        f"  tools: [view_file, grep_search]\n"
        f"CLAUDE:\n"
        f"  APPEND_BODY: Check secrets.\n"
        f"---\n"
        f"# Security\n\nAudit boundaries.\n",
    )

    assert [
        p.name for p in sources.iter_markdown_files(tmp_path / ".agents/supagents", partial=False)
    ] == ["security.md"]
    summary = core.build("project", cwd=tmp_path, strict=True)
    assert not summary.fatal_errors
    assert not summary.error_count
    assert not summary.warning_count
    assert not (tmp_path / ".claude/agents/_reviewer.md").exists()

    agy = (tmp_path / ".agents/agents/security.md").read_text(encoding="utf-8")
    assert "extends" not in agy
    assert "subagent: true" in agy
    assert "model: inherit" in agy
    assert "tools: [view_file, grep_search]" in agy
    assert "# Security\n\nAudit boundaries.\n\n## Output Contract\nReturn VERDICT." in agy

    claude = (tmp_path / ".claude/agents/security.md").read_text(encoding="utf-8")
    assert "Follow output contract.\n\nCheck secrets." in claude

    codex = (tmp_path / ".codex/agents/security.toml").read_text(encoding="utf-8")
    assert "extends" not in codex
    assert 'sandbox_mode = "read-only"' in codex
    assert "## Output Contract" in codex


def test_partial_inheritance_multiple_chained_and_diamond(
    tmp_path: Path, make_source: MakeSource
) -> None:
    make_source(
        "_common.md",
        "---\n"
        "AGY:\n  model: inherit\n  tools: [view_file]\n"
        "CLAUDE:\n  APPEND_BODY: Shared contract.\n"
        "CODEX: {}\n"
        "---\n"
        "{{BODY}}\n\n## Common Footer\nEnd.\n",
    )
    make_source(
        "_a.md",
        "---\nextends: _common\nAGY:\n  subagent: true\n  tools: [view_file, grep_search]\n"
        "CLAUDE:\n  maxTurns: 10\nCODEX: false\n---\n## Branch A\n{{BODY}}\n",
    )
    make_source(
        "_b.md",
        "---\nextends: _common\nCLAUDE:\n  maxTurns: 25\n---\n## Branch B\n",
    )
    make_source(
        "leaf.md",
        "---\nextends: [_a, _b]\nname: leaf\ndescription: Leaf agent\n---\nMain instructions.\n",
    )
    make_source(
        "dup.md",
        "---\nextends: [_a, _a]\nname: dup\ndescription: Duplicate parent\n---\nMain dup.\n",
    )

    summary = core.build("project", cwd=tmp_path, strict=True)
    assert not summary.fatal_errors
    assert not summary.warning_count

    claude = (tmp_path / ".claude/agents/leaf.md").read_text(encoding="utf-8")
    assert "maxTurns: 25" in claude
    assert claude.count("Shared contract.") == 1
    assert claude.count("## Common Footer") == 1
    assert "## Branch A\n## Branch B\n\nMain instructions.\n\n## Common Footer\nEnd." in claude

    agy = (tmp_path / ".agents/agents/leaf.md").read_text(encoding="utf-8")
    assert "subagent: true" in agy
    assert "tools: [view_file, grep_search]" in agy
    assert not (tmp_path / ".codex/agents/leaf.toml").exists()

    dup_claude = (tmp_path / ".claude/agents/dup.md").read_text(encoding="utf-8")
    assert dup_claude.count("## Branch A") == 1
    assert dup_claude.count("## Common Footer") == 1


@pytest.mark.parametrize(
    "order",
    [
        pytest.param("[_slot, _preamble]", id="slot_then_preamble"),
        pytest.param("[_preamble, _slot]", id="preamble_then_slot"),
    ],
)
def test_partial_sibling_slot_preservation(
    tmp_path: Path, make_source: MakeSource, order: str
) -> None:
    make_source("_slot.md", "---\nCLAUDE: {}\n---\n{{BODY}}\n\n## Output Contract\n")
    make_source("_preamble.md", "---\nCLAUDE: {}\n---\nAlways check security.\n")
    make_source("leaf.md", f"---\nextends: {order}\nname: leaf\n---\nInspect code.\n")

    summary = core.build("project", cwd=tmp_path, strict=True)
    assert not summary.fatal_errors
    content = (tmp_path / ".claude/agents/leaf.md").read_text(encoding="utf-8")
    assert "Always check security.\n\nInspect code.\n\n## Output Contract" in content


def test_partial_prepend_and_inherited_body(tmp_path: Path, make_source: MakeSource) -> None:
    make_source("_fm_only.md", "---\nCLAUDE:\n  model: sonnet\n---\n")
    make_source("_preamble.md", "---\nextends: _fm_only\n---\nBase guidance.\n")
    make_source("with_child.md", "---\nextends: _preamble\nname: with_child\n---\nChild step.\n")
    make_source("inherit_only.md", "---\nextends: _preamble\nname: inherit_only\n---\n")
    make_source("whitespace_only.md", "---\nextends: _preamble\nname: whitespace_only\n---\n  \n")

    summary = core.build("project", cwd=tmp_path, strict=True)
    assert not summary.fatal_errors
    assert "Base guidance.\n\nChild step." in (tmp_path / ".claude/agents/with_child.md").read_text(
        encoding="utf-8"
    )
    assert (
        (tmp_path / ".claude/agents/inherit_only.md")
        .read_text(encoding="utf-8")
        .endswith("Base guidance.\n")
    )
    assert (
        (tmp_path / ".claude/agents/whitespace_only.md")
        .read_text(encoding="utf-8")
        .endswith("Base guidance.\n")
    )


def test_partial_target_opt_out_and_reenable(tmp_path: Path, make_source: MakeSource) -> None:
    make_source(
        "_base.md",
        "---\nAGY: {}\nCODEX:\n  model: o3\n  APPEND_BODY: Base codex note.\n---\n{{BODY}}\n",
    )
    make_source("_no_codex.md", "---\nextends: _base\nCODEX: false\n---\n")
    make_source(
        "no_codex.md",
        "---\nextends: _no_codex\nname: no_codex\ndescription: No codex\n---\nBody.\n",
    )
    make_source(
        "with_codex.md",
        "---\nextends: _no_codex\nname: with_codex\ndescription: Re-enabled\n"
        "CODEX: {}\n---\nBody.\n",
    )
    make_source("standalone.md", "---\nCLAUDE: {}\nCODEX: false\n---\nSolo.\n")

    summary = core.build("project", cwd=tmp_path, strict=True)
    assert not summary.fatal_errors
    assert not summary.warning_count
    assert (tmp_path / ".agents/agents/no_codex.md").exists()
    assert not (tmp_path / ".codex/agents/no_codex.toml").exists()
    codex_toml = (tmp_path / ".codex/agents/with_codex.toml").read_text(encoding="utf-8")
    assert "o3" not in codex_toml
    assert "Base codex note." not in codex_toml
    assert (tmp_path / ".claude/agents/standalone.md").exists()
    assert not (tmp_path / ".codex/agents/standalone.toml").exists()


def test_malformed_child_target_suppresses_inherited_base(
    tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("_base.md", "---\nCLAUDE:\n  model: sonnet\nAGY: {}\n---\n{{BODY}}\n")
    make_source("child.md", '---\nextends: _base\nCLAUDE: "false"\n---\nBody.\n')

    summary = core.build("project", cwd=tmp_path)
    assert not summary.fatal_errors
    assert summary.warning_count == 1
    assert (tmp_path / ".agents/agents/child.md").exists()
    assert not (tmp_path / ".claude/agents/child.md").exists()


def test_parse_source_empty_body_and_yaml_recursion_errors(
    tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("_fm.md", "---\nCLAUDE: {}\n---\n")
    make_source("_slot.md", "---\nCLAUDE: {}\n---\n{{BODY}}\n")
    empty_leaf = make_source("empty_leaf.md", "---\nextends: _fm\nname: x\n---\n")
    empty_slot_leaf = make_source("empty_slot.md", "---\nextends: _slot\nname: x\n---\n")
    deep_yaml = make_source(
        "deep.md",
        "---\nname: deep\nCLAUDE:\n  a: " + ("[" * 600) + "1" + ("]" * 600) + "\n---\nBody.\n",
    )

    root = tmp_path / ".agents/supagents"
    with pytest.raises(ParseError, match="non-whitespace"):
        parse_source(empty_leaf, root)
    with pytest.raises(ParseError, match="non-whitespace"):
        parse_source(empty_slot_leaf, root)
    with pytest.raises(ParseError, match="invalid YAML"):
        parse_source(deep_yaml, root)


@pytest.mark.parametrize(
    ("setup_case", "match"),
    [
        pytest.param(
            lambda m, _t: m("a.md", "---\nextends: _missing\n---\nbody\n"),
            "does not exist",
            id="missing_partial",
        ),
        pytest.param(
            lambda m, _t: m("a.md", "---\nextends: other\n---\nbody\n"),
            "invalid partial reference",
            id="non_underscore_ref",
        ),
        pytest.param(
            lambda m, _t: m("a.md", "---\nextends: ../_secret\n---\nbody\n"),
            "invalid partial reference",
            id="path_traversal",
        ),
        pytest.param(
            lambda m, _t: m("a.md", "---\nextends: 123\n---\nbody\n"),
            "'extends' must be",
            id="invalid_extends_type",
        ),
        pytest.param(
            lambda m, _t: m("a.md", "---\nextends: []\n---\nbody\n"),
            "'extends' must be",
            id="empty_extends_list",
        ),
        pytest.param(
            lambda m, _t: (
                m("_a.md", "---\nextends: _b\n---\n"),
                m("_b.md", "---\nextends: _a\n---\n"),
                m("x.md", "---\nextends: _a\n---\nbody\n"),
            ),
            "cyclic partial inheritance",
            id="cycle",
        ),
        pytest.param(
            lambda m, _t: (
                m("_dup.md", "---\nCLAUDE: {}\n---\n{{BODY}}\n{{BODY}}\n"),
                m("x.md", "---\nextends: _dup\n---\nbody\n"),
            ),
            "at most one",
            id="duplicate_body_slot",
        ),
        pytest.param(
            lambda m, _t: m("_Bad.md", "---\nCLAUDE: {}\n---\n"),
            "partial filename",
            id="bad_partial_name",
        ),
        pytest.param(
            lambda m, _t: (
                m("_warn.md", "---\nTYPO: {}\n---\n"),
                m("x.md", "---\nextends: _warn\n---\nbody\n"),
            ),
            "invalid partial",
            id="referenced_partial_warning",
        ),
    ],
)
def test_partial_validation_failures_block_all_writes(
    tmp_path: Path, make_source: MakeSource, setup_case, match: str
) -> None:
    make_source("good.md", "---\nCLAUDE: {}\n---\nBody.\n")
    setup_case(make_source, tmp_path)
    summary = core.build("project", cwd=tmp_path)
    assert any(match in err for _, err in summary.fatal_errors), summary.fatal_errors
    assert not summary.written
    assert not (tmp_path / ".claude/agents/good.md").exists()


def test_partial_symlink_and_unreferenced_warning_fail_closed(
    tmp_path: Path, make_source: MakeSource
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("---\nCLAUDE: {}\n---\n", encoding="utf-8")
    link = tmp_path / ".agents/supagents/_link.md"
    link.symlink_to(outside)
    make_source("_unused_warn.md", "---\nTYPO: {}\n---\n")
    make_source("good.md", "---\nCLAUDE: {}\n---\nBody.\n")

    summary = core.build("project", cwd=tmp_path)
    messages = [msg for _, msg in summary.fatal_errors]
    assert any("symlinked partial" in m for m in messages)
    assert any("invalid partial" in m for m in messages)
    assert not summary.written
    assert not (tmp_path / ".claude/agents/good.md").exists()


def test_output_cannot_overwrite_partial_and_clean_preserves_partial(
    tmp_path: Path, make_source: MakeSource
) -> None:
    partial = make_source(
        "_reviewer.md",
        f"---\n{core.marker_line(Path('old.md'))}\nCLAUDE: {{}}\n---\n{{{{BODY}}}}\n",
    )
    make_source(
        "child.md",
        "---\nextends: _reviewer\nCLAUDE:\n  OUTPUT: _reviewer.md\n---\nBody.\n",
    )
    summary = core.build("project", cwd=tmp_path)
    assert any("overwrite a source" in msg for _, msg in summary.fatal_errors)
    assert not summary.written

    root = tmp_path / "overlap"
    root.mkdir()
    kept_partial = root / "_shared.md"
    kept_partial.write_text(
        f"---\n{core.marker_line(Path('legacy.md'))}\nCODEX: {{}}\n---\n", encoding="utf-8"
    )
    (root / "agent.md").write_text(
        "---\nextends: _shared\nname: agent\ndescription: Overlap\n---\nBody.\n", encoding="utf-8"
    )
    cfg = Config(
        targets={
            **DEFAULT_TARGETS,
            "CLAUDE": replace(DEFAULT_TARGETS["CLAUDE"], project_path=Path("overlap")),
        }
    )
    assert core.build("project", config=cfg, cwd=tmp_path, source_dir=root, strict=True).written
    clean_plan = core.plan_clean("project", config=cfg, cwd=tmp_path, source_dir=root)
    assert not clean_plan.has_blockers
    assert kept_partial not in clean_plan.orphans
    assert not core.check("project", config=cfg, cwd=tmp_path, source_dir=root).orphans
    assert partial.exists()


def test_concrete_symlinks_do_not_collide_in_raw_cache(
    tmp_path: Path, make_source: MakeSource
) -> None:
    empty_partial = make_source("_empty.md", "---\nCLAUDE: {}\n---\n")
    concrete_to_partial = tmp_path / ".agents/supagents/alias.md"
    concrete_to_partial.symlink_to(empty_partial)
    summary = core.build("project", cwd=tmp_path)
    assert any("non-whitespace" in msg for _, msg in summary.fatal_errors)
    assert not (tmp_path / ".claude/agents/_empty.md").exists()

    concrete_to_partial.unlink()
    shared = tmp_path / "shared.md"
    shared.write_text("---\nCLAUDE: {}\n---\nShared body.\n", encoding="utf-8")
    (tmp_path / ".agents/supagents/first.md").symlink_to(shared)
    (tmp_path / ".agents/supagents/second.md").symlink_to(shared)

    ok_summary = core.build("project", cwd=tmp_path, strict=True)
    assert not ok_summary.fatal_errors
    assert (tmp_path / ".claude/agents/first.md").exists()
    assert (tmp_path / ".claude/agents/second.md").exists()


def test_partial_failure_reported_once_without_child_duplication(
    tmp_path: Path, make_source: MakeSource
) -> None:
    make_source("_a.md", "---\nextends: _z\n---\n")
    broken = make_source("_z.md", "---\nTYPO: {}\n---\n")
    make_source("child.md", "---\nextends: _a\n---\nBody.\n")
    make_source("sibling.md", "---\nextends: _z\n---\nBody.\n")

    summary = core.build("project", cwd=tmp_path)
    assert len(summary.fatal_errors) == 1
    assert summary.fatal_errors[0][0] == broken

    outside = tmp_path / "outside.md"
    outside.write_text("---\nCLAUDE: {}\n---\n", encoding="utf-8")
    (tmp_path / ".agents/supagents/_link.md").symlink_to(outside)
    via_link = make_source("via_link.md", "---\nextends: _link\n---\nBody.\n")
    with pytest.raises(ParseError, match="symlinked partial"):
        parse_source(via_link, tmp_path / ".agents/supagents")


def test_cyclic_and_deep_commented_map_raise_parse_error() -> None:
    deep = CommentedMap(name="x")
    cur = deep
    for _ in range(500):
        nxt = CommentedMap()
        cur["n"] = nxt
        cur = nxt
    with pytest.raises(ParseError, match="cannot be represented as YAML"):
        sources.dump_yaml(deep)

    cyclic = CommentedMap(name="x")
    cyclic["self"] = cyclic
    with pytest.raises(ParseError, match="cannot be represented as TOML"):
        core.render(Path("x.md"), cyclic, "body", DEFAULT_TARGETS["CODEX"])
