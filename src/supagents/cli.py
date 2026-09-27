"""Typer-based command line interface."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from supagents import __version__, core
from supagents.config import Config, ConfigError, Scope, detect_scope, source_root

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Maintain shared subagent instructions and generate native coding-tool configurations.",
)

stdout = Console()
stderr = Console(stderr=True)

GlobalOpt = Annotated[
    bool, typer.Option("--global", "-g", help="Operate on global scope (~/.agents/supagents/).")
]
ProjectOpt = Annotated[
    bool, typer.Option("--project", "-p", help="Operate on project scope (./.agents/supagents/).")
]
DryRunOpt = Annotated[bool, typer.Option("--dry-run", help="Print actions without writing.")]
CheckOpt = Annotated[
    bool,
    typer.Option(
        "--check",
        help="Check missing, modified, and obsolete outputs without writing. Useful in CI.",
    ),
]
DiffOpt = Annotated[
    bool, typer.Option("--diff", help="Show unified content diffs without writing.")
]
StrictOpt = Annotated[
    bool,
    typer.Option("--strict", help="Fail on source warnings; build writes nothing on warnings."),
]
VerboseOpt = Annotated[
    bool, typer.Option("--verbose", "-v", help="Also print files left unchanged.")
]
TargetOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--target",
        "-t",
        help="Operate only on the named target(s); repeatable. Case-insensitive.",
    ),
]
ConfigOpt = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="Path to a supagents config file (default: $XDG_CONFIG_HOME/supagents/config.yaml).",
    ),
]
SourceOpt = Annotated[
    Path | None,
    typer.Option(
        "--source-dir", help="Override the source directory; scope still selects outputs."
    ),
]
ForceOpt = Annotated[
    bool, typer.Option("--force", "-f", help="Overwrite the file if it already exists.")
]


_INIT_TARGETS = {
    "CLAUDE": "  model: inherit\n",
    "GEMINI": '  kind: local\n  tools: ["*"]\n',
    "AGY": "  subagent: true\n  model: inherit\n",
    "CODEX": "",
    "GROK": "",
    "COPILOT": "",
    "CURSOR": "  model: inherit\n  readonly: false\n",
    "OPENCODE": "  mode: subagent\n",
    "KILO": "  mode: subagent\n",
}

_INIT_TEMPLATE = """\
---
name: {name}
description: TODO — describe when this agent should be invoked.
{targets}\
---

# {title}

You are the specialized {name} agent. TODO — describe persona and capabilities.
"""


def _load_config(config_path: Path | None) -> Config:
    """Load config, exiting cleanly on parse errors instead of leaking a stack trace."""
    try:
        return Config.load(config_path)
    except ConfigError as e:
        stderr.print(f"[red]ERROR[/]: {e}")
        raise typer.Exit(2) from None


def _resolve_scope(global_: bool, project: bool) -> Scope:
    if global_ and project:
        raise typer.BadParameter("--global and --project are mutually exclusive.")
    if global_:
        return "global"
    if project:
        return "project"
    return detect_scope()


def _show_scope(scope: Scope, explicit: bool, source_dir: Path | None) -> None:
    origin = "explicit" if explicit else "auto-detected"
    root = (source_dir or source_root(scope)).absolute()
    stderr.print(f"Scope: {scope} ({origin}); sources: {root}", markup=False)


def _resolve_targets(target: list[str] | None, config: Config) -> set[str] | None:
    """Normalise --target values to uppercase and validate against ``config``."""
    if not target:
        return None
    normalized = {t.upper() for t in target}
    unknown = normalized - set(config.targets)
    if unknown:
        raise typer.BadParameter(
            f"unknown target(s): {', '.join(sorted(unknown))}. "
            f"Known: {', '.join(sorted(config.targets))}."
        )
    return normalized


def _version_callback(value: bool) -> None:
    if value:
        stdout.print(f"supagents {__version__}")
        raise typer.Exit


@app.callback()
def _main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Supagents — cross-platform subagent build tool."""


@app.command(name="build")
def build_command(
    global_: GlobalOpt = False,
    project: ProjectOpt = False,
    dry_run: DryRunOpt = False,
    check: CheckOpt = False,
    diff: DiffOpt = False,
    strict: StrictOpt = False,
    verbose: VerboseOpt = False,
    target: TargetOpt = None,
    config_path: ConfigOpt = None,
    source_dir: SourceOpt = None,
) -> None:
    """Compile sources to target outputs."""
    if dry_run and check:
        raise typer.BadParameter("--dry-run and --check are mutually exclusive.")
    config = _load_config(config_path)
    scope = _resolve_scope(global_, project)
    targets = _resolve_targets(target, config)
    _show_scope(scope, global_ or project, source_dir)
    no_write = dry_run or check or diff
    try:
        if check:
            summary = core.check(scope, config, targets=targets, source_dir=source_dir)
        else:
            summary = core.build(
                scope=scope,
                config=config,
                dry_run=no_write,
                targets=targets,
                source_dir=source_dir,
                strict=strict,
            )
    except core.DuplicateSourceError as e:
        stderr.print(f"[red]ERROR[/]: {e}")
        raise typer.Exit(1) from None

    for src in summary.sources:
        for w in src.warnings:
            stderr.print(f"[yellow]WARN[/] {src.path}: {w}")
        for e in src.errors:
            stderr.print(f"[red]ERROR[/] {src.path}: {e}")
    for path, msg in summary.fatal_errors:
        stderr.print(f"[red]ERROR[/] {path}: {msg}")

    verb, color = ("would write", "cyan") if no_write else ("wrote", "green")
    for plan in summary.plans:
        if no_write or verbose:
            stdout.print(
                f"{plan.source.path} -> {plan.target_name} -> {plan.output_path}",
                markup=False,
            )
    for path in summary.written:
        stdout.print(f"[{color}]{verb}[/] {path}")
    for path in summary.orphans:
        stdout.print(f"[yellow]obsolete[/] {path}; preview cleanup with clean --dry-run")
    if summary.warning_count and check:
        stderr.print("Orphan scan skipped: resolve source warnings to determine ownership.")
    if diff and not summary.fatal_errors and not summary.error_count:
        changed = {
            plan.output_path: plan.rendered
            for plan in summary.plans
            if plan.output_path in summary.written
        }
        changed.update(dict.fromkeys(summary.orphans, ""))
        for path, content in changed.items():
            try:
                stdout.print(
                    core.output_diff(path, content),
                    end="",
                    markup=False,
                    highlight=False,
                    soft_wrap=True,
                )
            except (OSError, UnicodeError) as e:
                summary.fatal_errors.append((path, str(e)))
                stderr.print(f"Could not preview {path}: {e}", markup=False)
    if verbose:
        for path in summary.skipped_unchanged:
            stdout.print(f"[dim]unchanged[/] {path}")

    summary_verb = "would change" if no_write else "written"
    stdout.print(
        f"[bold]Summary[/]: "
        f"{len(summary.written)} {summary_verb}, "
        f"{len(summary.skipped_unchanged)} unchanged, "
        f"{len(summary.orphans)} obsolete, "
        f"{summary.warning_count} warnings, "
        f"{len(summary.fatal_errors) + summary.error_count} errors"
    )

    if summary.fatal_errors:
        raise typer.Exit(2)
    if summary.error_count or (strict and summary.warning_count):
        raise typer.Exit(1)
    if check and (summary.written or summary.orphans):
        raise typer.Exit(1)


@app.command(name="check")
def check_command(
    global_: GlobalOpt = False,
    project: ProjectOpt = False,
    strict: StrictOpt = False,
    diff: DiffOpt = False,
    verbose: VerboseOpt = False,
    target: TargetOpt = None,
    config_path: ConfigOpt = None,
    source_dir: SourceOpt = None,
) -> None:
    """Check missing, modified, and obsolete outputs without writing."""
    build_command(
        global_=global_,
        project=project,
        check=True,
        strict=strict,
        diff=diff,
        verbose=verbose,
        target=target,
        config_path=config_path,
        source_dir=source_dir,
    )


@app.command(name="clean")
def clean_command(
    global_: GlobalOpt = False,
    project: ProjectOpt = False,
    dry_run: DryRunOpt = False,
    target: TargetOpt = None,
    config_path: ConfigOpt = None,
    source_dir: SourceOpt = None,
) -> None:
    """Remove orphaned outputs (marker-bearing files no longer produced)."""
    config = _load_config(config_path)
    scope = _resolve_scope(global_, project)
    targets = _resolve_targets(target, config)
    _show_scope(scope, global_ or project, source_dir)
    try:
        orphans = core.find_orphans(scope, config, targets=targets, source_dir=source_dir)
    except (core.ParseError, core.DuplicateSourceError) as e:
        stderr.print(f"[red]ERROR[/]: {e}")
        raise typer.Exit(2) from None
    if not orphans:
        stdout.print("[dim]Nothing to clean.[/]")
        return
    for path in orphans:
        if dry_run:
            stdout.print(f"[cyan]would remove[/] {path}")
            continue
        try:
            path.unlink()
        except OSError as e:
            stderr.print(f"[red]ERROR[/] {path}: {e}")
            raise typer.Exit(2) from e
        stdout.print(f"[red]removed[/] {path}")


@app.command(name="init")
def init_command(
    name: Annotated[
        str,
        typer.Argument(help="Source name (lowercase letters, digits, '-' or '_'). '.md' optional."),
    ],
    global_: GlobalOpt = False,
    project: ProjectOpt = False,
    force: ForceOpt = False,
    source_dir: SourceOpt = None,
    target: TargetOpt = None,
    config_path: ConfigOpt = None,
) -> None:
    """Scaffold a new source file with target boilerplate."""
    stem = name.removesuffix(".md")
    if not core.SOURCE_FILENAME_RE.match(f"{stem}.md"):
        raise typer.BadParameter(
            f"name {name!r} must match ^[a-z0-9][a-z0-9_-]*$ (lowercase letters, digits, '-_')."
        )
    scope = _resolve_scope(global_, project)
    config = _load_config(config_path)
    targets = _resolve_targets(target, config)
    _show_scope(scope, global_ or project, source_dir)
    selected = sorted(targets) if targets is not None else list(_INIT_TARGETS)
    blocks = "".join(
        f"{key}:\n{_INIT_TARGETS[key]}" if _INIT_TARGETS.get(key) else f"{key}: {{}}\n"
        for key in selected
    )
    root = source_dir or source_root(scope)
    target_path = root / f"{stem}.md"
    if target_path.is_symlink():
        stderr.print(f"[red]ERROR[/]: refusing to replace a symlink: {target_path}")
        raise typer.Exit(1)
    if target_path.exists() and not force:
        stderr.print(f"[red]ERROR[/]: {target_path} already exists. Use --force to overwrite.")
        raise typer.Exit(1)
    title = stem.replace("-", " ").replace("_", " ").title()
    try:
        core.atomic_write(
            target_path, _INIT_TEMPLATE.format(name=stem, title=title, targets=blocks)
        )
    except OSError as e:
        stderr.print(f"[red]ERROR[/]: could not initialize {target_path}: {e}")
        raise typer.Exit(2) from e
    stdout.print(f"[green]created[/] {target_path}")


@app.command(name="list")
def list_command(
    global_: GlobalOpt = False,
    project: ProjectOpt = False,
    target: TargetOpt = None,
    config_path: ConfigOpt = None,
    source_dir: SourceOpt = None,
) -> None:
    """List defined sources and the outputs each would produce."""
    config = _load_config(config_path)
    scope = _resolve_scope(global_, project)
    targets = _resolve_targets(target, config)
    _show_scope(scope, global_ or project, source_dir)
    cwd = Path.cwd()
    sources, fatal_errors = core.collect_sources(scope, config, cwd, source_dir)
    for path, msg in fatal_errors:
        stderr.print(f"[red]ERROR[/] {path}: {msg}")
    if fatal_errors:
        raise typer.Exit(2)
    if not sources:
        stdout.print("[dim]No sources found.[/]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Source", style="bold")
    table.add_column("Target", style="cyan")
    table.add_column("Output")
    for src in sources:
        for plan in core.plan_source(src, config, scope, cwd, targets):
            table.add_row(src.name, plan.target_name, str(plan.output_path))
    stdout.print(table)
    for src in sources:
        for message in src.warnings:
            stderr.print(f"[yellow]WARN[/] {src.path}: {message}")
        for message in src.errors:
            stderr.print(f"[red]ERROR[/] {src.path}: {message}")
    if any(src.errors for src in sources):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
