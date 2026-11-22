"""Parse Markdown sources, ``_*.md`` partials, and DAG inheritance."""

import re
import stat
from copy import deepcopy
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

from supagents.config import DEFAULT_TARGETS, Config, Scope, source_root

SOURCE_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*\.md$")
PARTIAL_FILENAME_RE = re.compile(r"^_[a-z0-9][a-z0-9_-]*\.md$")
BODY_SLOT = "{{BODY}}"
DIRECTIVES: tuple[str, ...] = ("OUTPUT", "APPEND_BODY")


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


def _make_yaml() -> YAML:
    """Return a fresh round-trip YAML parser/dumper with project formatting."""
    yaml = YAML(typ="rt")
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def dump_yaml(data: CommentedMap) -> str:
    """Dump a frontmatter mapping using project conventions."""
    sio = StringIO()
    try:
        _make_yaml().dump(data, sio)
    except (YAMLError, RecursionError) as e:
        raise ParseError(f"frontmatter cannot be represented as YAML: {e}") from e
    return sio.getvalue()


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split source text into ``(frontmatter, body)``.

    Raises ``ParseError`` if the delimiters are missing or malformed.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[0].rstrip() != "---":
        raise ParseError("source must begin with '---' frontmatter delimiter")
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :]).strip("\n")
    raise ParseError("missing closing '---' frontmatter delimiter")


def _parse_frontmatter(text: str) -> CommentedMap:
    """Load YAML frontmatter as a ``CommentedMap`` (empty if blank)."""
    if not text.strip():
        return CommentedMap()
    try:
        result = _make_yaml().load(text)
    except (YAMLError, RecursionError) as e:
        raise ParseError(f"invalid YAML frontmatter: {e}") from e
    if result is None:
        return CommentedMap()
    if not isinstance(result, CommentedMap):
        raise ParseError("frontmatter must be a YAML mapping at the top level")
    return result


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


def _parse_target_block(name: str, value: object, src: Source) -> TargetBlock | None:
    """Parse one target block, appending warnings/errors to ``src``."""
    if value is None:
        return TargetBlock(frontmatter=CommentedMap())
    if not isinstance(value, CommentedMap):
        src.warnings.append(
            f"target {name!r} must be a YAML mapping (got {type(value).__name__}); skipping"
        )
        return None

    fm = CommentedMap()
    output: str | None = None
    append_body: str | None = None
    for k, v in value.items():
        if not isinstance(k, str):
            src.warnings.append(f"non-string key {k!r} in target {name!r} ignored")
            continue
        if not k.isupper():
            fm[k] = v
            continue
        match k:
            case "OUTPUT":
                if not isinstance(v, str):
                    src.errors.append(
                        f"directive 'OUTPUT' in target {name!r} must be a string; "
                        f"skipping this target's emit"
                    )
                    return None
                output = v
            case "APPEND_BODY":
                if v is None:
                    append_body = ""
                elif isinstance(v, str):
                    append_body = v
                else:
                    src.warnings.append(
                        f"directive 'APPEND_BODY' in target {name!r} must be a string; ignored"
                    )
            case _:
                src.warnings.append(
                    f"unknown directive {k!r} in target {name!r} (known: {', '.join(DIRECTIVES)})"
                )
    return TargetBlock(frontmatter=fm, output=output, append_body=append_body)


def _parse_single(
    path: Path, root: Path, known_targets: set[str], *, partial: bool = False
) -> tuple[Source, list[str]]:
    """Parse one concrete source or ``_*.md`` partial without resolving ``extends``."""
    pattern = PARTIAL_FILENAME_RE if partial else SOURCE_FILENAME_RE
    if not pattern.match(path.name):
        kind = "partial" if partial else "source"
        raise ParseError(f"{kind} filename must match {pattern.pattern} (got {path.name!r})")

    text = path.read_text(encoding="utf-8").removeprefix("\ufeff")
    fm_text, body = split_frontmatter(text)
    fm = _parse_frontmatter(fm_text)
    extends_list = parse_extends(fm["extends"]) if "extends" in fm else []

    if not partial and not extends_list and not body.strip():
        raise ParseError("body must contain non-whitespace content")
    if partial and body.count(BODY_SLOT) > 1:
        raise ParseError("partial body may contain at most one {{BODY}} placeholder")

    try:
        rel_path = path.resolve().relative_to(root.resolve())
    except ValueError:
        rel_path = Path(path.name)

    src = Source(
        path=path,
        name=path.stem,
        rel_path=rel_path,
        shared_frontmatter=CommentedMap(),
        body=body,
    )
    for key, value in fm.items():
        if not isinstance(key, str):
            src.warnings.append(f"non-string top-level key {key!r} ignored")
            continue
        if key == "extends":
            continue
        if not key.isupper():
            src.shared_frontmatter[key] = value
            continue
        if key not in known_targets:
            src.warnings.append(
                f"unknown top-level key {key!r} (known targets: {', '.join(sorted(known_targets))})"
            )
            continue
        if value is False:
            src.disabled_targets.add(key)
            continue
        block = _parse_target_block(key, value, src)
        if block is not None:
            src.targets[key] = block
        else:
            src.disabled_targets.add(key)

    if partial and (src.errors or src.warnings):
        first = (src.errors or src.warnings)[0]
        raise ParseError(f"invalid partial {path.name}: {first}")
    return src, extends_list


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
    known_targets: set[str],
    *,
    partial: bool,
    raw_cache: dict[Path, tuple[Source, list[str]]] | None = None,
    failed_partials: set[Path] | None = None,
) -> Source:
    """Parse ``path`` and apply deduplicated post-order ``extends`` ancestors."""
    cache = raw_cache if raw_cache is not None else {}

    def _get_raw(target_path: Path, is_part: bool) -> tuple[Source, list[str]]:
        if not is_part:
            return _parse_single(target_path, root, known_targets, partial=False)
        if target_path.is_symlink():
            raise ParseError(f"refusing symlinked partial: {target_path.name}")
        resolved = target_path.resolve()
        if resolved not in cache:
            cache[resolved] = _parse_single(target_path, root, known_targets, partial=True)
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


def parse_source(path: Path, root: Path, known_targets: set[str] | None = None) -> Source:
    """Read and parse a concrete source file into a ``Source`` value."""
    targets = set(DEFAULT_TARGETS) if known_targets is None else known_targets
    return resolve_inheritance(path, root, targets, partial=False)


def iter_markdown_files(root: Path, *, partial: bool = False) -> list[Path]:
    """Enumerate concrete sources (``partial=False``) or ``_*.md`` partials (``partial=True``)."""
    return sorted(
        path
        for path in root.iterdir()
        if path.suffix == ".md"
        and path.name.startswith("_") is partial
        and (path.is_symlink() or stat.S_ISREG(path.stat().st_mode))
    )


def collect_sources(
    scope: Scope, config: Config, cwd: Path, source_dir: Path | None = None
) -> tuple[list[Source], list[Path], list[tuple[Path, str]]]:
    """Parse every source and partial in ``scope``.

    Returns ``(sources, partial_paths, fatal_errors)``.
    """
    if source_dir is not None:
        try:
            root = source_dir.expanduser()
            is_dir = root.is_dir()
        except (OSError, RuntimeError) as e:
            return [], [], [(source_dir, str(e))]
        if not is_dir:
            return [], [], [(root, "source directory does not exist")]
    else:
        root = source_root(scope, cwd)

    sources: list[Source] = []
    fatal_errors: list[tuple[Path, str]] = []
    known_targets = set(config.targets)
    try:
        paths = iter_markdown_files(root, partial=False)
        partial_paths = iter_markdown_files(root, partial=True)
    except FileNotFoundError as e:
        if source_dir is None and not root.exists() and not root.is_symlink():
            return [], [], []
        return [], [], [(root, str(e))]
    except OSError as e:
        return [], [], [(root, str(e))]

    raw_cache: dict[Path, tuple[Source, list[str]]] = {}
    failed_partials: set[Path] = set()

    for ppath in partial_paths:
        if ppath.is_symlink():
            fatal_errors.append((ppath, f"refusing symlinked partial: {ppath.name}"))
            failed_partials.add(ppath)
            continue
        try:
            raw_cache[ppath.resolve()] = _parse_single(ppath, root, known_targets, partial=True)
        except (ParseError, OSError, UnicodeError) as e:
            fatal_errors.append((ppath, str(e)))
            failed_partials.add(ppath)

    for ppath in partial_paths:
        if ppath in failed_partials:
            continue
        try:
            resolve_inheritance(
                ppath,
                root,
                known_targets,
                partial=True,
                raw_cache=raw_cache,
                failed_partials=failed_partials,
            )
        except InheritedPartialError:
            failed_partials.add(ppath)
        except (ParseError, OSError, UnicodeError) as e:
            fatal_errors.append((ppath, str(e)))
            failed_partials.add(ppath)

    for path in paths:
        try:
            src = resolve_inheritance(
                path,
                root,
                known_targets,
                partial=False,
                raw_cache=raw_cache,
                failed_partials=failed_partials,
            )
        except InheritedPartialError:
            continue
        except (ParseError, OSError, UnicodeError) as e:
            fatal_errors.append((path, str(e)))
            continue
        sources.append(src)
    return sources, partial_paths, fatal_errors
