"""Verify package/plugin manifests, release tags, and CHANGELOG notes."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MANIFEST_FILES = (
    ".claude-plugin/plugin.json",
    "gemini-extension.json",
    "plugin.json",
)
HOMEPAGE_MANIFESTS = (
    ".claude-plugin/plugin.json",
    "plugin.json",
)


class ReleaseCheckError(Exception):
    """Raised when release metadata or changelog notes fail verification."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReleaseCheckError(f"missing manifest: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseCheckError(f"invalid JSON in {path}: {error}") from error
    if not isinstance(data, dict):
        raise ReleaseCheckError(f"expected JSON object in {path}")
    return data


def extract_changelog_section(changelog_text: str, version: str) -> str:
    """Return the trimmed body of ``## [<version>]`` from CHANGELOG Markdown."""
    heading = f"## [{version}]"
    collecting = False
    found_count = 0
    lines: list[str] = []
    for line in changelog_text.splitlines():
        if line == heading or line.startswith(f"{heading} "):
            found_count += 1
            if found_count > 1:
                raise ReleaseCheckError(f"duplicate ## [{version}] section in CHANGELOG.md")
            collecting = True
            continue
        if collecting and line.startswith("## "):
            collecting = False
            continue
        if collecting:
            lines.append(line)
    return "\n".join(lines).strip()


def verify_release(root: Path, tag: str | None = None) -> tuple[str, str]:
    """Validate version, description, homepage, and optional release tag/changelog."""
    pyproject_path = root / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ReleaseCheckError(f"cannot read {pyproject_path}: {error}") from error

    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise ReleaseCheckError("missing [project] table in pyproject.toml")

    version = project.get("version")
    description = project.get("description")
    urls = project.get("urls")
    if not isinstance(version, str) or not version:
        raise ReleaseCheckError("missing project.version in pyproject.toml")
    if not isinstance(description, str) or not description:
        raise ReleaseCheckError("missing project.description in pyproject.toml")
    homepage = urls.get("Homepage") if isinstance(urls, dict) else None
    if not isinstance(homepage, str) or not homepage:
        raise ReleaseCheckError("missing project.urls.Homepage in pyproject.toml")

    for rel in MANIFEST_FILES:
        manifest = _read_json(root / rel)
        if manifest.get("version") != version:
            raise ReleaseCheckError(
                f"{rel}: version {manifest.get('version')!r} != pyproject.toml {version!r}"
            )
        if manifest.get("description") != description:
            raise ReleaseCheckError(f"{rel}: description differs from pyproject.toml")
        if rel in HOMEPAGE_MANIFESTS and manifest.get("homepage") != homepage:
            raise ReleaseCheckError(f"{rel}: homepage differs from pyproject.toml")

    marketplace = _read_json(root / ".claude-plugin/marketplace.json")
    if marketplace.get("description") != description:
        raise ReleaseCheckError(
            ".claude-plugin/marketplace.json: description differs from pyproject.toml"
        )
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or not plugins or not isinstance(plugins[0], dict):
        raise ReleaseCheckError(".claude-plugin/marketplace.json: missing plugins[0] object")
    if plugins[0].get("description") != description:
        raise ReleaseCheckError(
            ".claude-plugin/marketplace.json: plugins[0].description differs from pyproject.toml"
        )
    if plugins[0].get("homepage") != homepage:
        raise ReleaseCheckError(
            ".claude-plugin/marketplace.json: plugins[0].homepage differs from pyproject.toml"
        )

    if tag is None:
        return version, ""

    if tag != f"v{version}":
        raise ReleaseCheckError(
            f"release tag {tag!r} does not match pyproject.toml version v{version}"
        )

    changelog_path = root / "CHANGELOG.md"
    try:
        changelog_text = changelog_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ReleaseCheckError(f"cannot read {changelog_path}: {error}") from error

    notes = extract_changelog_section(changelog_text, version)
    if not notes:
        raise ReleaseCheckError(f"CHANGELOG.md must contain a non-empty ## [{version}] section")
    return version, notes


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for release manifest and changelog verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", nargs="?", help="Expected release tag, e.g. v1.6.0")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root directory",
    )
    parser.add_argument(
        "--notes",
        action="store_true",
        help="Print extracted release notes for TAG to stdout",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.notes and not args.tag:
        sys.stderr.write("error: --notes requires a TAG argument\n")
        return 1
    try:
        _, notes = verify_release(args.root, args.tag)
    except ReleaseCheckError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    if args.notes:
        sys.stdout.write(f"{notes}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
