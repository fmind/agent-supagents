"""Verify repository skill contracts, plugin manifests, and release checks."""

import re
import shutil
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from scripts import verify_release

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_METADATA_KEYS = {"kind", "author", "source", "created", "updated"}


def _parse_skill(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 500
    assert text.startswith("---\n")
    parts = text.split("\n---\n", 1)
    assert len(parts) == 2
    frontmatter = YAML(typ="safe").load(parts[0].removeprefix("---\n"))
    assert isinstance(frontmatter, dict)
    return frontmatter, parts[1]


def test_user_skill_contract() -> None:
    skill_dirs = sorted(p for p in (REPO_ROOT / "skills").iterdir() if p.is_dir())
    assert [p.name for p in skill_dirs] == ["supagent"]
    skill_path = skill_dirs[0] / "SKILL.md"
    fm, body = _parse_skill(skill_path)
    assert fm["name"] == "supagent"
    assert fm["license"] == "MIT"
    desc = fm["description"]
    assert isinstance(desc, str)
    assert 1 <= len(desc.strip()) <= 180
    metadata = fm["metadata"]
    assert isinstance(metadata, dict)
    assert set(metadata) >= REQUIRED_METADATA_KEYS
    assert metadata["kind"] in {"task", "connector", "collection"}
    # Packaged /supagent must stay self-contained when installed standalone.
    assert not re.search(r"\]\([^)]*\.\./", body)


def test_repo_maintainer_skills_and_claude_bridge() -> None:
    skills_root = REPO_ROOT / ".agents" / "skills"
    skill_dirs = sorted(p for p in skills_root.iterdir() if p.is_dir())
    assert [p.name for p in skill_dirs] == ["harnesses", "release"]
    for directory in skill_dirs:
        fm, _ = _parse_skill(directory / "SKILL.md")
        assert fm["name"] == directory.name
        assert fm["license"] == "MIT"
        desc = fm["description"]
        assert isinstance(desc, str)
        assert 1 <= len(desc.strip()) <= 180
        metadata = fm["metadata"]
        assert isinstance(metadata, dict)
        assert set(metadata) >= REQUIRED_METADATA_KEYS

    bridge = REPO_ROOT / ".claude" / "skills"
    assert bridge.is_symlink()
    assert bridge.readlink().as_posix() == "../.agents/skills"
    assert bridge.resolve() == skills_root.resolve()


def test_verify_release_passes_on_repository() -> None:
    assert verify_release.main(["--root", str(REPO_ROOT)]) == 0


def _copy_release_fixture(
    tmp_path: Path,
    version: str = "1.5.0",
    changelog: str | None = None,
) -> Path:
    (tmp_path / ".claude-plugin").mkdir(parents=True)
    for rel in (
        "pyproject.toml",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "gemini-extension.json",
        "plugin.json",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if rel == "pyproject.toml":
            text = re.sub(r'(?m)^version = "[^"]+"', f'version = "{version}"', text, count=1)
        else:
            text = re.sub(r'"version": "[^"]+"', f'"version": "{version}"', text)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    shutil.copy2(REPO_ROOT / "CHANGELOG.md", tmp_path / "CHANGELOG.md")
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def test_verify_release_notes_and_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    changelog = (
        "# Changelog\n\n"
        "## [1.5.0] - 2026-11-15\n\n"
        "### 🚀 Features\n\n"
        "- Add /supagent.\n\n"
        "## [1.4.1] - 2026-10-06\n\n"
        "- Old.\n"
    )
    root = _copy_release_fixture(tmp_path, version="1.5.0", changelog=changelog)

    assert verify_release.main(["v1.5.0", "--root", str(root), "--notes"]) == 0
    assert capsys.readouterr().out.strip() == "### 🚀 Features\n\n- Add /supagent."

    assert verify_release.main(["v1.4.9", "--root", str(root)]) == 1
    assert "does not match" in capsys.readouterr().err

    assert verify_release.main(["--root", str(root), "--notes"]) == 1
    assert "--notes requires a TAG" in capsys.readouterr().err

    empty_log = _copy_release_fixture(
        tmp_path / "empty",
        version="1.5.0",
        changelog="# Changelog\n\n## [1.5.0] - 2026-11-15\n\n## [1.4.1]\n- x\n",
    )
    assert verify_release.main(["v1.5.0", "--root", str(empty_log)]) == 1
    assert "non-empty ## [1.5.0]" in capsys.readouterr().err

    bad_plugin = '{"version": "0.0.1", "description": "bad"}'
    (root / "plugin.json").write_text(bad_plugin, encoding="utf-8")
    assert verify_release.main(["--root", str(root)]) == 1
    assert "plugin.json" in capsys.readouterr().err
