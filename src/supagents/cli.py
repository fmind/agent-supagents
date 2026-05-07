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
    help="Compile a single AI supagent into multiple AI subagents.",
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
        help="Exit non-zero if any output would change. Implies no writes. Useful in CI.",
    ),
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
ForceOpt = Annotated[
    bool, typer.Option("--force", "-f", help="Overwrite the file if it already exists.")
]


_INIT_TEMPLATE = """\
---
name: {name}
description: TODO — describe when this agent should be invoked.
CLAUDE:
  model: sonnet
  tools: Read, Write, Edit, Bash, Glob, Grep
GEMINI:
  kind: local
  tools: ["*"]
COPILOT:
  target: vscode
  model: ["gpt-5", "gpt-4.1"]
CURSOR:
  model: inherit
  readonly: false
OPENCODE:
  mode: subagent
KILO:
  mode: subagent
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
    verbose: VerboseOpt = False,
    target: TargetOpt = None,
    config_path: ConfigOpt = None,
) -> None:
    """Compile sources to target outputs."""
    if dry_run and check:
        raise typer.BadParameter("--dry-run and --check are mutually exclusive.")
    config = _load_config(config_path)
    scope = _resolve_scope(global_, project)
    targets = _resolve_targets(target, config)
    no_write = dry_run or check
    try:
        summary = core.build(scope=scope, config=config, dry_run=no_write, targets=targets)
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
    for path in summary.written:
        stdout.print(f"[{color}]{verb}[/] {path}")
    if verbose:
        for path in summary.skipped_unchanged:
            stdout.print(f"[dim]unchanged[/] {path}")

    summary_verb = "would change" if no_write else "written"
    stdout.print(
        f"[bold]Summary[/]: "
        f"{len(summary.written)} {summary_verb}, "
        f"{len(summary.skipped_unchanged)} unchanged, "
        f"{len(summary.fatal_errors)} errors"
    )

    if summary.fatal_errors:
        raise typer.Exit(2)
    if summary.error_count:
        raise typer.Exit(1)
    if check and summary.written:
        raise typer.Exit(1)


@app.command(name="clean")
def clean_command(
    global_: GlobalOpt = False,
    project: ProjectOpt = False,
    dry_run: DryRunOpt = False,
    target: TargetOpt = None,
    config_path: ConfigOpt = None,
) -> None:
    """Remove orphaned outputs (marker-bearing files no longer produced)."""
    config = _load_config(config_path)
    scope = _resolve_scope(global_, project)
    targets = _resolve_targets(target, config)
    orphans = core.find_orphans(scope, config, targets=targets)
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
) -> None:
    """Scaffold a new source file with target boilerplate."""
    stem = name.removesuffix(".md")
    if not core.SOURCE_FILENAME_RE.match(f"{stem}.md"):
        raise typer.BadParameter(
            f"name {name!r} must match ^[a-z0-9][a-z0-9_-]*$ (lowercase letters, digits, '-_')."
        )
    scope = _resolve_scope(global_, project)
    root = source_root(scope)
    target_path = root / f"{stem}.md"
    if target_path.exists() and not force:
        stderr.print(f"[red]ERROR[/]: {target_path} already exists. Use --force to overwrite.")
        raise typer.Exit(1)
    title = stem.replace("-", " ").replace("_", " ").title()
    root.mkdir(parents=True, exist_ok=True)
    target_path.write_text(_INIT_TEMPLATE.format(name=stem, title=title), encoding="utf-8")
    stdout.print(f"[green]created[/] {target_path}")


@app.command(name="list")
def list_command(
    global_: GlobalOpt = False,
    project: ProjectOpt = False,
    target: TargetOpt = None,
    config_path: ConfigOpt = None,
) -> None:
    """List defined sources and the outputs each would produce."""
    config = _load_config(config_path)
    scope = _resolve_scope(global_, project)
    targets = _resolve_targets(target, config)
    cwd = Path.cwd()
    sources, fatal_errors = core.collect_sources(scope, config, cwd)
    for path, msg in fatal_errors:
        stderr.print(f"[red]ERROR[/] {path}: {msg}")
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


if __name__ == "__main__":
    app()
