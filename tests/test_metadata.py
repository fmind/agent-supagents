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


def _assert_skill_frontmatter(fm: dict[str, object], expected_name: str) -> None:
    assert fm["name"] == expected_name
    assert fm["license"] == "MIT"
    desc = fm["description"]
    assert isinstance(desc, str)
    assert 1 <= len(desc.strip()) <= 180
    metadata = fm["metadata"]
    assert isinstance(metadata, dict)
    assert set(metadata) >= REQUIRED_METADATA_KEYS
    assert metadata["kind"] in {"task", "connector", "collection"}


def test_user_skill_contract() -> None:
    skill_dirs = sorted(p for p in (REPO_ROOT / "skills").iterdir() if p.is_dir())
    assert [p.name for p in skill_dirs] == ["supagent"]
    fm, body = _parse_skill(skill_dirs[0] / "SKILL.md")
    _assert_skill_frontmatter(fm, "supagent")
    # Packaged /supagent must stay self-contained when installed standalone.
    assert not re.search(r"\]\([^)]*\.\./", body)


def test_repo_maintainer_skills() -> None:
    skills_root = REPO_ROOT / ".agents" / "skills"
    skill_dirs = sorted(p for p in skills_root.iterdir() if p.is_dir())
    assert [p.name for p in skill_dirs] == ["harnesses", "release"]
    for directory in skill_dirs:
        fm, _ = _parse_skill(directory / "SKILL.md")
        _assert_skill_frontmatter(fm, directory.name)

    retired_bridge = REPO_ROOT / ".claude" / "skills"
    assert not retired_bridge.exists()
    assert not retired_bridge.is_symlink()


def test_verify_release_passes_on_repository() -> None:
    assert verify_release.main(["--root", str(REPO_ROOT)]) == 0


def _copy_release_fixture(
    tmp_path: Path,
    version: str = "1.6.0",
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
        "## [1.6.0] - 2026-11-16\n\n"
        "### Features\n\n"
        "- Add partials.\n\n"
        "## Older notes\n\n"
        "- Not part of 1.6.0.\n"
    )
    root = _copy_release_fixture(tmp_path, version="1.6.0", changelog=changelog)

    assert verify_release.main(["v1.6.0", "--root", str(root), "--notes"]) == 0
    assert capsys.readouterr().out.strip() == "### Features\n\n- Add partials."

    assert verify_release.main(["v1.4.9", "--root", str(root)]) == 1
    assert "does not match" in capsys.readouterr().err

    assert verify_release.main(["--root", str(root), "--notes"]) == 1
    assert "--notes requires a TAG" in capsys.readouterr().err

    dup_log = _copy_release_fixture(
        tmp_path / "dup",
        version="1.6.0",
        changelog="# Changelog\n\n## [1.6.0]\n- a\n\n## [1.6.0]\n- b\n",
    )
    assert verify_release.main(["v1.6.0", "--root", str(dup_log)]) == 1
    assert "duplicate" in capsys.readouterr().err

    empty_log = _copy_release_fixture(
        tmp_path / "empty",
        version="1.6.0",
        changelog="# Changelog\n\n## [1.6.0] - 2026-11-16\n\n## [1.5.0]\n- x\n",
    )
    assert verify_release.main(["v1.6.0", "--root", str(empty_log)]) == 1
    assert "non-empty ## [1.6.0]" in capsys.readouterr().err

    (root / "plugin.json").write_bytes(b"\xff\xfe")
    assert verify_release.main(["--root", str(root)]) == 1
    assert "invalid JSON" in capsys.readouterr().err
