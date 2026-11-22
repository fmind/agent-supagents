"""Stdlib argparse command-line interface for supagents."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from supagents.config import Config, Scope
    from supagents.sources import Source

_INIT_TARGET_DEFAULTS: dict[str, dict[str, object]] = {
    "CLAUDE": {"model": "inherit"},
    "GEMINI": {"kind": "local", "tools": ["*"]},
    "AGY": {"subagent": True, "model": "inherit"},
    "CURSOR": {"model": "inherit", "readonly": False},
    "OPENCODE": {"mode": "subagent"},
    "KILO": {"mode": "subagent"},
}

_INIT_TEMPLATE = """\
---
{frontmatter}\
---

# {title}

You are the specialized {name} agent. TODO — describe persona and capabilities.
"""

_ANSI_CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "cyan": "36",
}

_ROOT_EPILOG = """\
Examples:
  supagents init reviewer --project --target claude --target codex
  supagents build --project --diff
  supagents build --project --strict
  supagents check --project --strict --json
  supagents clean --project --dry-run

Exit codes:
  0    Success
  1    Operational error (drift, source/config/I/O error, strict warning, or refused write)
  2    CLI usage error (invalid flags, unknown --target, or missing subcommand)
  130  Interrupted (SIGINT)
"""


def _configure_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    if sys.version_info >= (3, 14):
        parser.suggest_on_error = True
    return parser


class _VersionAction(argparse.Action):
    """Print package version lazily without importing importlib.metadata at startup."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str = argparse.SUPPRESS,
        default: object = argparse.SUPPRESS,
        help: str | None = None,  # noqa: A002 - argparse.Action parameter name
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        del namespace, values, option_string
        from supagents import __version__

        _out(f"supagents {__version__}")
        parser.exit(0)


class UsageError(Exception):
    """Raised on invalid CLI argument combinations (exits 2)."""


class OperationalError(Exception):
    """Raised on operational failures (exits 1)."""


@dataclass(frozen=True, slots=True)
class CommonOptions:
    """Typed shared CLI options unpacked from ``argparse.Namespace``."""

    global_scope: bool
    project_scope: bool
    targets: tuple[str, ...]
    config: Path | None
    source_dir: Path | None
    quiet: bool
    as_json: bool


@dataclass(slots=True)
class RunContext:
    """Validated runtime options for one CLI invocation."""

    config: Config
    scope: Scope
    explicit_scope: bool
    targets: set[str] | None
    source_dir: Path | None
    effective_source_dir: Path
    cwd: Path
    quiet: bool
    as_json: bool


def _common_options(args: argparse.Namespace) -> CommonOptions:
    raw_targets: list[str] | None = args.target
    return CommonOptions(
        global_scope=bool(args.global_scope),
        project_scope=bool(args.project_scope),
        targets=tuple(raw_targets) if raw_targets else (),
        config=args.config,
        source_dir=args.source_dir,
        quiet=bool(args.quiet),
        as_json=bool(args.as_json),
    )


def _non_empty_path(raw: str) -> Path:
    """Reject empty or NUL-containing path arguments before Path('') becomes '.'."""
    if not raw or not raw.strip() or "\0" in raw:
        raise argparse.ArgumentTypeError("path must be non-empty and contain no NUL bytes")
    return Path(raw)


def _use_color(stream: TextIO) -> bool:
    """Enable ANSI color only on interactive TTYs when NO_COLOR/TERM allow it."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def _style(text: str, style_name: str, stream: TextIO) -> str:
    if not _use_color(stream):
        return text
    code = _ANSI_CODES[style_name]
    return f"\033[{code}m{text}\033[0m"


def _out(text: str = "", *, end: str = "\n") -> None:
    sys.stdout.write(f"{text}{end}")


def _err(text: str = "", *, end: str = "\n") -> None:
    with suppress(BrokenPipeError):
        sys.stderr.write(f"{text}{end}")


def _emit_json(payload: dict[str, object]) -> None:
    import json

    sys.stdout.write(f"{json.dumps(payload, indent=2)}\n")


def _silence_broken_pipe() -> None:
    if sys.stdout is not None and sys.stdout is sys.__stdout__:
        with Path(os.devnull).open("wb") as devnull:
            os.dup2(devnull.fileno(), sys.stdout.fileno())


def _prepare(opts: CommonOptions) -> RunContext:
    """Resolve scope, config, target filter, and source directory."""
    if opts.global_scope and opts.project_scope:
        raise UsageError("--global and --project are mutually exclusive.")

    from supagents.config import Config, ConfigError, detect_scope, source_root

    try:
        cwd = Path.cwd()
        scope: Scope = (
            "global"
            if opts.global_scope
            else "project"
            if opts.project_scope
            else detect_scope(cwd)
        )
    except (OSError, RuntimeError) as e:
        raise OperationalError(f"cannot determine working directory or scope: {e}") from e
    explicit_scope = opts.global_scope or opts.project_scope

    resolved_source_dir: Path | None = None
    if opts.source_dir is not None:
        try:
            resolved_source_dir = opts.source_dir.expanduser()
        except RuntimeError as e:
            raise UsageError(f"source directory cannot be expanded: {e}") from e

    try:
        config = Config.load(opts.config)
    except ConfigError as e:
        raise OperationalError(str(e)) from e

    targets: set[str] | None = None
    if opts.targets:
        normalized = {t.upper() for t in opts.targets}
        unknown = normalized - set(config.targets)
        if unknown:
            raise UsageError(
                f"unknown target(s): {', '.join(sorted(unknown))}. "
                f"Known: {', '.join(sorted(config.targets))}."
            )
        targets = normalized

    try:
        effective_source_dir = (resolved_source_dir or source_root(scope, cwd)).absolute()
    except (OSError, RuntimeError) as e:
        raise OperationalError(f"cannot resolve source directory: {e}") from e

    ctx = RunContext(
        config=config,
        scope=scope,
        explicit_scope=explicit_scope,
        targets=targets,
        source_dir=resolved_source_dir,
        effective_source_dir=effective_source_dir,
        cwd=cwd,
        quiet=opts.quiet,
        as_json=opts.as_json,
    )
    if not ctx.quiet and not ctx.as_json:
        origin = "explicit" if explicit_scope else "auto-detected"
        _err(f"Scope: {scope} ({origin}); sources: {effective_source_dir}")
    return ctx


def _print_source_issues(sources: Sequence[Source]) -> None:
    """Print per-source warnings and errors to stderr verbatim."""
    for src in sources:
        for message in src.warnings:
            _err(f"{_style('WARN', 'yellow', sys.stderr)} {src.path}: {message}")
        for message in src.errors:
            _err(f"{_style('ERROR', 'red', sys.stderr)} {src.path}: {message}")


def _run_build_or_check(
    ctx: RunContext,
    *,
    dry_run: bool,
    check: bool,
    diff: bool,
    strict: bool,
    verbose: bool,
) -> int:
    from supagents import core

    no_write = dry_run or check or diff
    if check:
        summary = core.check(
            ctx.scope,
            ctx.config,
            cwd=ctx.cwd,
            targets=ctx.targets,
            source_dir=ctx.source_dir,
        )
    else:
        summary = core.build(
            scope=ctx.scope,
            config=ctx.config,
            cwd=ctx.cwd,
            dry_run=no_write,
            targets=ctx.targets,
            source_dir=ctx.source_dir,
            strict=strict,
        )

    _print_source_issues(summary.sources)
    for path, msg in summary.fatal_errors:
        _err(f"{_style('ERROR', 'red', sys.stderr)} {path}: {msg}")

    if summary.fatal_errors and not summary.written:
        return 1

    diffs: dict[str, str] = {}
    if diff and not summary.fatal_errors and not summary.error_count:
        changed = {
            plan.output_path: plan.rendered
            for plan in summary.plans
            if plan.output_path in summary.written
        }
        changed.update(dict.fromkeys(summary.orphans, ""))
        for path, content in changed.items():
            try:
                diffs[str(path)] = core.output_diff(path, content)
            except (OSError, UnicodeError) as e:
                summary.fatal_errors.append((path, str(e)))
                _err(f"{_style('ERROR', 'red', sys.stderr)} Could not preview {path}: {e}")

    orphan_scan_skipped = summary.orphan_scan_skipped
    if orphan_scan_skipped:
        _err("Orphan scan skipped: resolve source errors or warnings to determine ownership.")

    failed = bool(
        summary.fatal_errors
        or summary.error_count
        or (strict and summary.warning_count)
        or (check and (summary.written or summary.orphans))
    )

    try:
        if ctx.as_json:
            if summary.fatal_errors:
                return 1
            payload: dict[str, object] = {
                "ok": not failed,
                "command": "check" if check else "build",
                "scope": ctx.scope,
                "source_dir": str(ctx.effective_source_dir),
                "dry_run": no_write,
                "orphan_scan_skipped": orphan_scan_skipped,
                "written": [str(p) for p in summary.written],
                "unchanged": [str(p) for p in summary.skipped_unchanged],
                "obsolete": [str(p) for p in summary.orphans],
                "warnings": [
                    {"source": str(src.path), "message": msg}
                    for src in summary.sources
                    for msg in src.warnings
                ],
                "errors": [
                    {"source": str(src.path), "message": msg}
                    for src in summary.sources
                    for msg in src.errors
                ],
                "mappings": [
                    {
                        "source": str(plan.source.path),
                        "target": plan.target_name,
                        "output": str(plan.output_path),
                    }
                    for plan in summary.plans
                ],
            }
            if diff:
                payload["diffs"] = diffs
            _emit_json(payload)
            return 1 if failed else 0

        if not ctx.quiet:
            verb, color = ("would write", "cyan") if no_write else ("wrote", "green")
            for plan in summary.plans:
                if no_write or verbose:
                    _out(f"{plan.source.path} -> {plan.target_name} -> {plan.output_path}")
            for path in summary.written:
                _out(f"{_style(verb, color, sys.stdout)} {path}")
            for path in summary.orphans:
                _out(
                    f"{_style('obsolete', 'yellow', sys.stdout)} {path}; "
                    "preview cleanup with clean --dry-run"
                )
            for rendered_diff in diffs.values():
                _out(rendered_diff, end="")
            if verbose:
                for path in summary.skipped_unchanged:
                    _out(f"{_style('unchanged', 'dim', sys.stdout)} {path}")

            summary_verb = "would change" if no_write else "written"
            _out(
                f"{_style('Summary', 'bold', sys.stdout)}: "
                f"{len(summary.written)} {summary_verb}, "
                f"{len(summary.skipped_unchanged)} unchanged, "
                f"{len(summary.orphans)} obsolete, "
                f"{summary.warning_count} warnings, "
                f"{len(summary.fatal_errors) + summary.error_count} errors"
            )
    except BrokenPipeError:
        _silence_broken_pipe()
    return 1 if failed else 0


def _handle_build(
    opts: CommonOptions,
    *,
    dry_run: bool,
    check: bool,
    diff: bool,
    strict: bool,
    verbose: bool,
) -> int:
    if dry_run and check:
        raise UsageError("--dry-run and --check are mutually exclusive.")
    ctx = _prepare(opts)
    return _run_build_or_check(
        ctx,
        dry_run=dry_run,
        check=check,
        diff=diff,
        strict=strict,
        verbose=verbose,
    )


def _handle_check(
    opts: CommonOptions,
    *,
    diff: bool,
    strict: bool,
    verbose: bool,
) -> int:
    ctx = _prepare(opts)
    return _run_build_or_check(
        ctx,
        dry_run=False,
        check=True,
        diff=diff,
        strict=strict,
        verbose=verbose,
    )


def _confirm_auto_global_clean(orphans: Sequence[Path], *, no_input: bool) -> bool:
    """Confirm destructive cleanup when global scope was inferred rather than requested."""
    count = len(orphans)
    if no_input or not getattr(sys.stdin, "isatty", lambda: False)():
        _err(
            f"{_style('ERROR', 'red', sys.stderr)}: refusing to remove {count} global "
            "orphan(s) under auto-detected global scope without --global or --yes. "
            "Preview with 'supagents clean --global --dry-run'."
        )
        return False
    for path in orphans:
        _err(f"  {path}")
    _err(f"Remove {count} global orphan(s) under auto-detected global scope? [y/N]: ", end="")
    with suppress(BrokenPipeError):
        sys.stderr.flush()
    answer = sys.stdin.readline().strip().lower()
    if answer not in {"y", "yes"}:
        _err("Aborted.")
        return False
    return True


def _handle_clean(
    opts: CommonOptions,
    *,
    dry_run: bool,
    yes: bool,
    no_input: bool,
) -> int:
    from supagents import core

    ctx = _prepare(opts)
    plan = core.plan_clean(
        ctx.scope,
        ctx.config,
        cwd=ctx.cwd,
        targets=ctx.targets,
        source_dir=ctx.source_dir,
    )
    if plan.has_blockers:
        _print_source_issues(plan.sources)
        for path, msg in plan.fatal_errors:
            _err(f"{_style('ERROR', 'red', sys.stderr)} {path}: {msg}")
        _err(
            f"{_style('ERROR', 'red', sys.stderr)}: cannot clean while sources have errors "
            "or warnings. Run 'supagents check --strict' to inspect and resolve issues."
        )
        return 1

    if (
        plan.orphans
        and not dry_run
        and ctx.scope == "global"
        and not ctx.explicit_scope
        and not yes
        and not _confirm_auto_global_clean(plan.orphans, no_input=no_input)
    ):
        return 1

    processed: list[str] = []
    for path in plan.orphans:
        if not dry_run:
            try:
                path.unlink()
            except OSError as e:
                _err(f"{_style('ERROR', 'red', sys.stderr)} {path}: {e}")
                return 1
        processed.append(str(path))

    try:
        if ctx.as_json:
            _emit_json(
                {
                    "ok": True,
                    "command": "clean",
                    "scope": ctx.scope,
                    "source_dir": str(ctx.effective_source_dir),
                    "dry_run": dry_run,
                    "removed": processed,
                }
            )
        elif not ctx.quiet:
            if not processed:
                _out(_style("Nothing to clean.", "dim", sys.stdout))
            else:
                verb, color = ("would remove", "cyan") if dry_run else ("removed", "red")
                for item in processed:
                    _out(f"{_style(verb, color, sys.stdout)} {item}")
    except BrokenPipeError:
        _silence_broken_pipe()
    return 0


def _handle_init(
    opts: CommonOptions,
    *,
    name: str,
    force: bool,
    dry_run: bool,
) -> int:
    from ruamel.yaml.comments import CommentedMap

    from supagents import core, sources
    from supagents.config import DEFAULT_TARGETS, source_root

    stem = name.removesuffix(".md")
    if not sources.SOURCE_FILENAME_RE.match(f"{stem}.md"):
        raise UsageError(
            f"name {name!r} must match ^[a-z0-9][a-z0-9_-]*$ (lowercase letters, digits, '-_')."
        )
    ctx = _prepare(opts)
    selected = sorted(ctx.targets) if ctx.targets is not None else list(DEFAULT_TARGETS)
    frontmatter = CommentedMap(
        name=stem,
        description="TODO — describe when this agent should be invoked.",
    )
    for key in selected:
        frontmatter[key] = _INIT_TARGET_DEFAULTS.get(key, {})
    try:
        root = ctx.source_dir or source_root(ctx.scope, ctx.cwd)
    except (OSError, RuntimeError) as e:
        raise OperationalError(f"cannot resolve source directory: {e}") from e
    target_path = root / f"{stem}.md"
    try:
        is_symlink = target_path.is_symlink()
        exists = target_path.exists() if not is_symlink else False
        is_file = target_path.is_file() if exists else False
    except OSError as e:
        _err(f"{_style('ERROR', 'red', sys.stderr)}: cannot inspect {target_path}: {e}")
        return 1
    if is_symlink:
        _err(f"{_style('ERROR', 'red', sys.stderr)}: refusing to replace a symlink: {target_path}")
        return 1
    if exists and not is_file:
        _err(
            f"{_style('ERROR', 'red', sys.stderr)}: {target_path} exists and is not a regular file."
        )
        return 1
    if exists and not force:
        _err(
            f"{_style('ERROR', 'red', sys.stderr)}: {target_path} already exists. "
            "Use --force to overwrite."
        )
        return 1
    title = stem.replace("-", " ").replace("_", " ").title()
    content = _INIT_TEMPLATE.format(
        name=stem, title=title, frontmatter=sources.dump_yaml(frontmatter)
    )
    if not dry_run:
        try:
            core.atomic_write(target_path, content)
        except OSError as e:
            _err(f"{_style('ERROR', 'red', sys.stderr)}: could not initialize {target_path}: {e}")
            return 1

    try:
        if ctx.as_json:
            _emit_json(
                {
                    "ok": True,
                    "command": "init",
                    "scope": ctx.scope,
                    "source_dir": str(ctx.effective_source_dir),
                    "dry_run": dry_run,
                    "path": str(target_path),
                    "targets": selected,
                }
            )
        elif not ctx.quiet:
            verb, color = ("would create", "cyan") if dry_run else ("created", "green")
            _out(f"{_style(verb, color, sys.stdout)} {target_path}")
    except BrokenPipeError:
        _silence_broken_pipe()
    return 0


def _handle_list(opts: CommonOptions) -> int:
    from supagents import core, sources

    ctx = _prepare(opts)
    collected, _, fatal_errors = sources.collect_sources(
        ctx.scope, ctx.config, ctx.cwd, ctx.source_dir
    )
    for path, msg in fatal_errors:
        _err(f"{_style('ERROR', 'red', sys.stderr)} {path}: {msg}")
    if fatal_errors:
        return 1

    rows: list[tuple[str, str, str]] = []
    for src in collected:
        rows.extend(
            (src.name, plan.target_name, str(plan.output_path))
            for plan in core.plan_source(src, ctx.config, ctx.scope, ctx.cwd, ctx.targets)
        )
    _print_source_issues(collected)
    has_errors = any(src.errors for src in collected)

    try:
        if ctx.as_json:
            if has_errors:
                return 1
            _emit_json(
                {
                    "ok": True,
                    "command": "list",
                    "scope": ctx.scope,
                    "source_dir": str(ctx.effective_source_dir),
                    "items": [
                        {"source": name, "target": target, "output": output}
                        for name, target, output in rows
                    ],
                }
            )
            return 0

        if not ctx.quiet:
            if not rows:
                if not has_errors:
                    _out(_style("No sources found.", "dim", sys.stdout))
            else:
                src_w = max(len("Source"), *(len(r[0]) for r in rows))
                tgt_w = max(len("Target"), *(len(r[1]) for r in rows))
                header = f"{'Source':<{src_w}}  {'Target':<{tgt_w}}  Output"
                _out(_style(header, "bold", sys.stdout))
                for name, target, output in rows:
                    styled_target = _style(f"{target:<{tgt_w}}", "cyan", sys.stdout)
                    _out(f"{name:<{src_w}}  {styled_target}  {output}")
    except BrokenPipeError:
        _silence_broken_pipe()
    return 1 if has_errors else 0


def _add_shared_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-g",
        "--global",
        dest="global_scope",
        action="store_true",
        help="Operate on global scope (~/.agents/supagents/).",
    )
    parser.add_argument(
        "-p",
        "--project",
        dest="project_scope",
        action="store_true",
        help="Operate on project scope (./.agents/supagents/).",
    )
    parser.add_argument(
        "-t",
        "--target",
        action="append",
        metavar="TARGET",
        help="Operate only on the named target(s); repeatable, case-insensitive.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=_non_empty_path,
        metavar="FILE",
        help="Path to a supagents config file (default: $XDG_CONFIG_HOME/supagents/config.yaml).",
    )
    parser.add_argument(
        "--source-dir",
        type=_non_empty_path,
        metavar="DIR",
        help="Override the source directory; scope still selects outputs.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress routine status output.",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit one machine-readable JSON object on stdout.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Define the full CLI parser tree."""
    parser = _configure_parser(
        argparse.ArgumentParser(
            prog="supagents",
            description=(
                "Maintain shared subagent instructions and generate native coding-tool "
                "configurations."
            ),
            epilog=_ROOT_EPILOG,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            allow_abbrev=False,
        )
    )
    parser.add_argument(
        "--version",
        action=_VersionAction,
        help="Show version and exit.",
    )
    subparsers = parser.add_subparsers(title="commands", metavar="COMMAND", required=True)

    p_build = _configure_parser(
        subparsers.add_parser(
            "build",
            help="Compile sources to target outputs.",
            description="Compile sources to target outputs.",
            allow_abbrev=False,
        )
    )
    _add_shared_options(p_build)
    p_build.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Preview actions without writing or removing files.",
    )
    p_build.add_argument(
        "--check",
        action="store_true",
        help="Check missing, modified, and obsolete outputs without writing. Useful in CI.",
    )
    p_build.add_argument(
        "--diff",
        action="store_true",
        help="Show unified content diffs without writing.",
    )
    p_build.add_argument(
        "--strict",
        action="store_true",
        help="Fail on source warnings; build writes nothing on warnings.",
    )
    p_build.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Also print source-to-output mappings and unchanged files.",
    )
    p_build.set_defaults(
        handler=lambda args: _handle_build(
            _common_options(args),
            dry_run=bool(args.dry_run),
            check=bool(args.check),
            diff=bool(args.diff),
            strict=bool(args.strict),
            verbose=bool(args.verbose),
        ),
        parser=p_build,
    )

    p_check = _configure_parser(
        subparsers.add_parser(
            "check",
            help="Check missing, modified, and obsolete outputs without writing.",
            description="Check missing, modified, and obsolete outputs without writing.",
            allow_abbrev=False,
        )
    )
    _add_shared_options(p_check)
    p_check.add_argument(
        "--strict",
        action="store_true",
        help="Fail on source warnings.",
    )
    p_check.add_argument(
        "--diff",
        action="store_true",
        help="Show unified content diffs for missing, modified, and obsolete outputs.",
    )
    p_check.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Also print unchanged files.",
    )
    p_check.set_defaults(
        handler=lambda args: _handle_check(
            _common_options(args),
            diff=bool(args.diff),
            strict=bool(args.strict),
            verbose=bool(args.verbose),
        ),
        parser=p_check,
    )

    p_clean = _configure_parser(
        subparsers.add_parser(
            "clean",
            help="Remove orphaned outputs (marker-bearing files no longer produced).",
            description="Remove orphaned outputs (marker-bearing files no longer produced).",
            allow_abbrev=False,
        )
    )
    _add_shared_options(p_clean)
    p_clean.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Preview actions without writing or removing files.",
    )
    p_clean.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip interactive confirmation when removing auto-detected global orphans.",
    )
    p_clean.add_argument(
        "--no-input",
        action="store_true",
        help="Never prompt for confirmation on stdin.",
    )
    p_clean.set_defaults(
        handler=lambda args: _handle_clean(
            _common_options(args),
            dry_run=bool(args.dry_run),
            yes=bool(args.yes),
            no_input=bool(args.no_input),
        ),
        parser=p_clean,
    )

    p_init = _configure_parser(
        subparsers.add_parser(
            "init",
            help="Scaffold a new source file with target boilerplate.",
            description="Scaffold a new source file with target boilerplate.",
            allow_abbrev=False,
        )
    )
    p_init.add_argument(
        "name",
        metavar="NAME",
        help="Source name (lowercase letters, digits, '-' or '_'). '.md' optional.",
    )
    _add_shared_options(p_init)
    p_init.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite the file if it already exists.",
    )
    p_init.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Preview actions without writing or removing files.",
    )
    p_init.set_defaults(
        handler=lambda args: _handle_init(
            _common_options(args),
            name=str(args.name),
            force=bool(args.force),
            dry_run=bool(args.dry_run),
        ),
        parser=p_init,
    )

    p_list = _configure_parser(
        subparsers.add_parser(
            "list",
            help="List defined sources and the outputs each would produce.",
            description="List defined sources and the outputs each would produce.",
            allow_abbrev=False,
        )
    )
    _add_shared_options(p_list)
    p_list.set_defaults(
        handler=lambda args: _handle_list(_common_options(args)),
        parser=p_list,
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point invoked by the ``supagents`` console script or ``python -m supagents``."""
    parser = build_parser()
    active_parser = parser
    code = 0
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        active_parser = getattr(args, "parser", parser)
        code = args.handler(args)
        sys.stdout.flush()
    except SystemExit:
        try:
            sys.stdout.flush()
        except BrokenPipeError:
            _silence_broken_pipe()
        raise
    except UsageError as e:
        active_parser.error(str(e))
    except OperationalError as e:
        _err(f"{_style('ERROR', 'red', sys.stderr)}: {e}")
        raise SystemExit(1) from None
    except BrokenPipeError:
        _silence_broken_pipe()
        if code:
            raise SystemExit(code) from None
        return
    except KeyboardInterrupt as e:
        raise SystemExit(130) from e
    if code:
        raise SystemExit(code)
