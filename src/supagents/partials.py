"""Partial source inheritance (``_*.md``), DAG linearization, and merging."""

import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml.comments import CommentedMap

PARTIAL_FILENAME_RE = re.compile(r"^_[a-z0-9][a-z0-9_-]*\.md$")
BODY_SLOT = "{{BODY}}"


class ParseError(Exception):
    """Raised when a source or partial cannot be parsed and must be skipped."""


class InheritedPartialError(ParseError):
    """Raised when a source or partial depends on an already-reported partial failure."""


@dataclass(slots=True)
class TargetBlock:
    """One target's parsed frontmatter and directives."""

    frontmatter: CommentedMap
    output: str | None = None
    append_body: str | None = None


@dataclass(slots=True)
class Source:
    """A parsed source file ready to be rendered for each target."""

    path: Path
    name: str
    rel_path: Path
    shared_frontmatter: CommentedMap
    body: str
    targets: dict[str, TargetBlock] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    disabled_targets: set[str] = field(default_factory=set)


def compute_frontmatter(shared: CommentedMap, target_fm: CommentedMap) -> CommentedMap:
    """Merge shared + target frontmatter; target overrides; shared keys keep their position."""
    out = CommentedMap()
    for mapping in (shared, target_fm):
        for k, v in mapping.items():
            out[k] = deepcopy(v)
    return out


def compute_body(shared_body: str, append_body: str | None) -> str:
    """Concatenate shared body + optional ``APPEND_BODY``, separated by one blank line."""
    if not append_body:
        return shared_body
    tail = append_body.strip("\n")
    if not tail:
        return shared_body
    return f"{shared_body.rstrip('\n')}\n\n{tail}"


def parse_extends(value: object) -> list[str]:
    """Normalize and validate an ``extends`` partial reference or list."""
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        items = list(value)
    else:
        raise ParseError("'extends' must be a partial name or non-empty list of partial names")
    out: list[str] = []
    for raw in items:
        if not raw or raw != raw.strip() or "/" in raw or "\\" in raw:
            raise ParseError(f"invalid partial reference in 'extends': {raw!r}")
        filename = raw if raw.endswith(".md") else f"{raw}.md"
        if not PARTIAL_FILENAME_RE.match(filename):
            raise ParseError(
                f"invalid partial reference in 'extends': {raw!r}; expected '_name' or '_name.md'"
            )
        out.append(filename)
    return out


def _merge_body(base_body: str, child_body: str, *, is_partial: bool) -> str:
    c_stripped = child_body.strip()
    if not base_body.strip():
        return child_body if c_stripped else ""
    if BODY_SLOT not in base_body:
        return compute_body(base_body, child_body) if c_stripped else base_body
    if not c_stripped:
        if not is_partial:
            raise ParseError("body must contain non-whitespace content when partial uses {{BODY}}")
        return base_body
    c_trimmed = child_body.strip("\n")
    if is_partial and BODY_SLOT not in child_body:
        return base_body.replace(BODY_SLOT, f"{c_trimmed}\n\n{BODY_SLOT}").strip("\n")
    return base_body.replace(BODY_SLOT, c_trimmed).strip("\n")


def merge_sources(base: Source, child: Source, *, is_partial: bool) -> Source:
    """Merge ``base`` and ``child`` sources with ``child`` taking precedence."""
    shared = compute_frontmatter(base.shared_frontmatter, child.shared_frontmatter)
    merged_targets: dict[str, TargetBlock] = {
        k: deepcopy(v) for k, v in base.targets.items() if k not in child.disabled_targets
    }
    for tname, cblock in child.targets.items():
        if tname in merged_targets:
            bblock = merged_targets[tname]
            merged_append = (
                compute_body(bblock.append_body, cblock.append_body)
                if bblock.append_body
                else cblock.append_body
            )
            merged_targets[tname] = TargetBlock(
                frontmatter=compute_frontmatter(bblock.frontmatter, cblock.frontmatter),
                output=cblock.output if cblock.output is not None else bblock.output,
                append_body=merged_append,
            )
        else:
            merged_targets[tname] = deepcopy(cblock)

    return Source(
        path=child.path,
        name=child.name,
        rel_path=child.rel_path,
        shared_frontmatter=shared,
        body=_merge_body(base.body, child.body, is_partial=is_partial),
        targets=merged_targets,
        warnings=list(dict.fromkeys([*base.warnings, *child.warnings])),
        errors=list(dict.fromkeys([*base.errors, *child.errors])),
        disabled_targets=(base.disabled_targets - set(child.targets)) | child.disabled_targets,
    )


def resolve_inheritance(
    path: Path,
    root: Path,
    *,
    partial: bool,
    parse_raw: Callable[[Path, bool], tuple[Source, list[str]]],
    raw_cache: dict[Path, tuple[Source, list[str]]] | None = None,
    failed_partials: set[Path] | None = None,
) -> Source:
    """Parse ``path`` and apply deduplicated post-order ``extends`` ancestors."""
    cache = raw_cache if raw_cache is not None else {}

    def _get_raw(target_path: Path, is_part: bool) -> tuple[Source, list[str]]:
        if not is_part:
            return parse_raw(target_path, False)
        if target_path.is_symlink():
            raise ParseError(f"refusing symlinked partial: {target_path.name}")
        resolved = target_path.resolve()
        if resolved not in cache:
            cache[resolved] = parse_raw(target_path, True)
        return cache[resolved]

    def _visit_partial(
        partial_path: Path,
        visiting: tuple[Path, ...],
        seen: set[Path],
        ordered: list[Source],
    ) -> None:
        if failed_partials is not None and partial_path in failed_partials:
            raise InheritedPartialError(f"inherited partial failed: {partial_path.name}")
        if not partial_path.is_symlink() and not partial_path.is_file():
            raise ParseError(f"extended partial does not exist: {partial_path.name}")
        raw_src, parent_refs = _get_raw(partial_path, True)
        resolved = partial_path.resolve()
        if resolved in visiting:
            cycle = " -> ".join(p.name for p in (*visiting, resolved))
            raise ParseError(f"cyclic partial inheritance: {cycle}")
        if resolved in seen:
            return
        next_visiting = (*visiting, resolved)
        for ref in parent_refs:
            _visit_partial(root / ref, next_visiting, seen, ordered)
        seen.add(resolved)
        ordered.append(raw_src)

    raw_leaf, leaf_extends = _get_raw(path, partial)
    if not leaf_extends:
        return raw_leaf

    visiting = (path.resolve(),)
    seen: set[Path] = set()
    ancestors: list[Source] = []
    for ref in leaf_extends:
        _visit_partial(root / ref, visiting, seen, ancestors)

    acc = ancestors[0]
    for ancestor in ancestors[1:]:
        acc = merge_sources(acc, ancestor, is_partial=True)
    merged = merge_sources(acc, raw_leaf, is_partial=partial)
    if not partial and not merged.body.strip():
        raise ParseError("body must contain non-whitespace content")
    return merged
