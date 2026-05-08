![supagents — compile one AI supagent into multiple AI subagents](image.jpeg)

# supagents

> **Compile a single AI supagent into multiple AI subagents.**

Supagents is a small Python CLI that compiles a single markdown file into target-specific subagent files for [Claude Code], [Gemini CLI], [GitHub Copilot], [Cursor], [OpenCode], and [Kilo Code]. You write the agent's persona once and ship it to every agent CLI you use.

[![CI](https://github.com/fmind/agent-supagents/actions/workflows/ci.yml/badge.svg)](https://github.com/fmind/agent-supagents/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Type checked: ty](https://img.shields.io/badge/ty-checked-blue)](https://docs.astral.sh/ty/)

[Claude Code]: https://docs.claude.com/en/docs/claude-code/sub-agents
[Gemini CLI]: https://github.com/google-gemini/gemini-cli
[GitHub Copilot]: https://docs.github.com/en/copilot
[Cursor]: https://cursor.com/docs/subagents
[OpenCode]: https://opencode.ai/docs/agents/
[Kilo Code]: https://kilo.ai/docs/customize/custom-subagents

## Why

Every agent CLI has its own subagent format. The persona is the same ("You are a code-investigation expert..."), but each one wants a different YAML frontmatter shape and a different output directory. Hand-syncing every file every time you tweak a prompt is miserable.

Supagents takes the **opposite** approach from format-conversion tools: it makes you write each target's frontmatter **verbatim** in named blocks, and then it does the boring parts — splitting the body, copying shared keys, writing files atomically, and cleaning up stale outputs.

```
   one source                                 many outputs
   ─────────                                  ────────────
                                              ~/.claude/agents/code_investigator.md
                                              ~/.gemini/agents/code_investigator.md
~/.agents/supagents/code_investigator.md  →   ~/.copilot/agents/code_investigator.agent.md
                                              ~/.cursor/agents/code_investigator.md
                                              ~/.config/opencode/agents/code_investigator.md
                                              ~/.config/kilo/agents/code_investigator.md
```

The diagram shows the full fan-out. Declare any subset of target blocks in your source and supagents emits just those — the example below picks three.

## Install

```bash
uv tool install supagents
# or:
pipx install supagents
# or, from this repo:
uv tool install --from /path/to/supagents supagents
```

Requires Python 3.12+.

## Install as a plugin or extension

The same repo doubles as a Claude Code plugin, a Gemini CLI extension, and a GitHub Copilot plugin — install it through your agent CLI and it pulls in the bundled [`use-agent-supagents` Agent Skill](skills/use-agent-supagents/SKILL.md). Your agent learns the source format and CLI semantics up front, so you don't have to paste docs into prompts.

| Tool           | Manifest in the repo                                | What it installs                |
|----------------|-----------------------------------------------------|---------------------------------|
| Claude Code    | `.claude-plugin/plugin.json` (+ `marketplace.json`) | Plugin + bundled marketplace.   |
| Gemini CLI     | `gemini-extension.json`                             | Gemini CLI extension.           |
| GitHub Copilot | `plugin.json`                                       | Copilot plugin manifest.        |

These manifests register the Skill — they don't install the `supagents` CLI binary. Install the CLI separately (above) so `supagents build` lives on `$PATH`.

## Quick start

Scaffold a new source with `supagents init <name>` (writes a template with all default target blocks), or drop one yourself at `~/.agents/supagents/code_investigator.md`. The example below declares three blocks to keep things short — add `CURSOR:`, `OPENCODE:`, or `KILO:` blocks to emit those targets too:

```markdown
---
name: code_investigator
description: Use to explore unfamiliar codebases — trace symbols, map data flow across modules, and explain how a feature is implemented.

CLAUDE:
  model: sonnet
  tools: Read, Grep, Glob, Bash

GEMINI:
  kind: local
  tools: ["*"]
  mcp_servers:
    context7:
      command: npx
      args: ["-y", "@upstash/context7-mcp@latest"]

COPILOT:
  target: vscode
  model: ["gpt-5", "gpt-4.1"]
  APPEND_BODY: |

    ## Copilot-specific
    Reference tools inline with `#tool:<name>`.
---

# Code Investigator Agent

You are the specialized code investigation agent. Help the user explore unfamiliar codebases: trace symbols, map data flow across modules, and explain how features are implemented.
```

Then build:

```bash
supagents build
```

You'll get one file per declared target — three in this example:

```
~/.claude/agents/code_investigator.md           # Claude Code subagent
~/.gemini/agents/code_investigator.md           # Gemini CLI agent
~/.copilot/agents/code_investigator.agent.md    # GitHub Copilot agent
```

Each output gets the **shared keys** (`name`, `description`) plus the **target's own keys**, the shared body, and a generation marker comment so `supagents clean` can safely identify what it owns.

Source filenames must match `^[a-z0-9][a-z0-9_-]*\.md$` — lowercase letters, digits, hyphens, and underscores only.

## How it works

The frontmatter is partitioned by case:

| Case | Where it goes |
|---|---|
| `lowercase` keys at the top | shared frontmatter — copied to every output |
| `UPPERCASE` keys at the top | target sections (`CLAUDE`, `GEMINI`, `COPILOT`) |
| `lowercase` keys inside a target | that target's frontmatter (overrides shared) |
| `UPPERCASE` keys inside a target | directives — not emitted |

Two directives are recognized:

| Directive | What it does |
|---|---|
| `OUTPUT` | Override the output path for this target only |
| `APPEND_BODY` | Append target-specific markdown to the shared body |

A target section's **presence** triggers an emit. Drop the `COPILOT:` block and you stop generating Copilot files. There is **no** field-level conversion — what you write is what gets written.

For validation rules, scope resolution, and idempotency guarantees, see the inline docstrings in [`src/supagents/`](src/supagents/) — `core.py` and `config.py`.

## CLI

```text
supagents --version
supagents build [SCOPE] [--dry-run | --check] [--target T]... [--config PATH] [-v]
supagents clean [SCOPE] [--dry-run]           [--target T]... [--config PATH]
supagents list  [SCOPE]                       [--target T]... [--config PATH]
supagents init  NAME [SCOPE] [--force]
```

`SCOPE` is `--global`/`-g` or `--project`/`-p`; if omitted, supagents auto-detects.

| Command | Purpose |
|---|---|
| `build` | Compile sources to outputs. Idempotent — unchanged files aren't rewritten (mtimes preserved). Warnings and errors print to stderr. `--check` exits 1 if anything would change — handy as a CI guard against stale outputs. See [Exit codes](#exit-codes). |
| `clean` | Delete marker-bearing outputs whose source is gone. Hand-written files in the same directory are preserved. |
| `list`  | Print a table of every source and the per-target outputs it would produce. |
| `init`  | Scaffold a new source file at `<scope>/.../NAME.md` with the default target blocks pre-filled. Refuses to overwrite without `--force`. |

### Flags

| Flag | Applies to | Notes |
|---|---|---|
| `--target T`, `-t` | `build`, `clean`, `list` | Operate only on the named target(s); repeatable, case-insensitive. Unknown targets are rejected. |
| `--check` | `build` | Don't write; exit 1 if any output would change. Mutually exclusive with `--dry-run`. Useful as a CI guard against stale generated files. |
| `--verbose`, `-v` | `build` | Also print files that were left unchanged — useful when sanity-checking idempotency. |
| `--config PATH`, `-c` | all | Override the default config path (`$XDG_CONFIG_HOME/supagents/config.yaml`). |
| `--force`, `-f` | `init` | Overwrite the file if it already exists. |
| `--version` | top-level | Print the installed version and exit. |

### Exit codes

Every command resolves to one of three exit codes — pick them up in CI to fail fast on the right thing:

| Code | Meaning |
|---|---|
| `0` | Success. Nothing wrong, nothing stale. |
| `1` | Per-target errors, or `--check` detected drift you'd need to commit. |
| `2` | Fatal parse error, or a write failed mid-build. |

### Scopes

| Scope | Source location |
|---|---|
| **Global** | `~/.agents/supagents/*.md` |
| **Project** | `./.agents/supagents/*.md` |

If neither `--global` nor `--project` is passed, supagents auto-detects: project scope when `.agents/supagents/` exists in the current directory, global otherwise.

### Bundled targets

A target only emits when its block appears in the source frontmatter. The bundled defaults:

| Target | Global output | Project output | Suffix |
|---|---|---|---|
| `CLAUDE` | `~/.claude/agents/` | `.claude/agents/` | `.md` |
| `GEMINI` | `~/.gemini/agents/` | `.gemini/agents/` | `.md` |
| `COPILOT` | `~/.copilot/agents/` | `.github/agents/` | `.agent.md` |
| `CURSOR` | `~/.cursor/agents/` | `.cursor/agents/` | `.md` |
| `OPENCODE` | `~/.config/opencode/agents/` | `.opencode/agents/` | `.md` |
| `KILO` | `~/.config/kilo/agents/` | `.kilo/agents/` | `.md` |

Override any path or add a new target via the config file (see below).

## Pre-commit integration

Drop this in your repo's `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/fmind/agent-supagents
  rev: v1.0.0  # pin to a tagged release — see https://github.com/fmind/agent-supagents/releases
  hooks:
    - id: supagents-build
```

The hook runs whenever a source file under `.agents/supagents/` (or chezmoi source state under `dot_agents/supagents/`) changes, and rewrites the generated outputs in place. Commit them alongside the sources so PRs stay self-consistent. To enforce that on the CI side, run `supagents build --check` — it exits non-zero if any generated file would change.

If you'd rather not depend on a remote hook repo, use the local form:

```yaml
- repo: local
  hooks:
    - id: supagents-build
      name: supagents build
      entry: supagents build
      language: system
      files: ^(\.agents/supagents/|dot_agents/supagents/)[a-z0-9][a-z0-9_-]*\.md$
      pass_filenames: false
```

## chezmoi integration

If you manage your dotfiles with [chezmoi], put your sources in:

```
~/.local/share/chezmoi/dot_agents/supagents/<name>.md
```

`chezmoi apply` materializes them at `~/.agents/supagents/<name>.md`. Supagents reads from the **materialized** path, so a typical flow is:

```bash
chezmoi edit ~/.agents/supagents/code_investigator.md
chezmoi apply
supagents build --global
```

The pre-commit hook above already watches the chezmoi source path (`dot_agents/supagents/`), so committing inside your dotfiles repo regenerates the outputs automatically.

[chezmoi]: https://www.chezmoi.io/

## Configuration

Six targets ship by default (`CLAUDE`, `GEMINI`, `COPILOT`, `CURSOR`, `OPENCODE`, `KILO`). To override their paths or add a new one, drop a YAML config at `~/.config/supagents/config.yaml` (XDG-compliant — honours `$XDG_CONFIG_HOME`):

```yaml
targets:
  claude:
    global_path: ~/.claude/agents
    project_path: .claude/agents
```

Per-field merge: any field you omit falls back to the bundled default. Lowercase keys in the file are normalised to UPPERCASE to match the source frontmatter convention. Once a target is registered, sources can use its UPPERCASE name in their frontmatter and supagents will emit for it.

## Development

```bash
git clone https://github.com/fmind/agent-supagents.git
cd agent-supagents
just install   # uv sync + pre-commit install
just lint      # ruff format check + ruff check + ty + uv lock --check
just test      # pytest with coverage (≥ 90% gate)
just format    # auto-fix imports and formatting
just update    # bump locked deps + pre-commit autoupdate
just clean     # drop caches and __pycache__
```

`just lint` and `just test` are exactly what CI runs — green locally means green in CI.

The build is small on purpose: a tight dependency surface (`typer`, `rich`, `ruamel.yaml`, `pydantic`), no I/O outside documented paths, [`ty`](https://docs.astral.sh/ty/) for type checks, ruff with a strict ruleset, pre-commit as the single source of truth wired into CI.

## Design

A few principles worth calling out:

- **Verbatim per-target frontmatter.** Each target gets its own block in the source; supagents copies it through unchanged. No schema conversion, no surprises.
- **Open-list targets.** Adding a new target is a few lines in `~/.config/supagents/config.yaml`. The source format already supports it.
- **Idempotent builds.** Two consecutive `supagents build` runs against an unchanged source tree perform zero writes. Generated files keep their mtimes.
- **Safe cleanup.** `supagents clean` only deletes files it can prove it generated, by checking for the marker comment at the top.

## License

[MIT](LICENSE) — Médéric Hurier (Fmind).
