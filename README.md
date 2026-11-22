# Supagents

[![CI](https://github.com/fmind/agent-supagents/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fmind/agent-supagents/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/supagents)](https://pypi.org/project/supagents/) [![Python 3.12+](https://img.shields.io/pypi/pyversions/supagents)](https://pypi.org/project/supagents/) [![MIT License](https://img.shields.io/github/license/fmind/agent-supagents)](https://github.com/fmind/agent-supagents/blob/main/LICENSE)

Maintain shared subagent instructions and generate native configurations for your coding tools. Supagents keeps role definitions in Git while preserving explicit model, tool, and permission settings for each harness.

[Try it](#one-source-native-settings) · [Commands](#commands) · [Usage](https://github.com/fmind/agent-supagents/blob/main/docs/usage.md) · [Compatibility](https://github.com/fmind/agent-supagents/blob/main/docs/compatibility.md) · [Changelog](https://github.com/fmind/agent-supagents/blob/main/CHANGELOG.md)

```bash
uv tool install supagents
supagents init reviewer --project --target claude --target codex
# Edit .agents/supagents/reviewer.md (see the example below).
supagents build --project --diff
supagents build --project --strict
supagents check --project --strict
```

The final check reports `0 would change, 2 unchanged, 0 obsolete, 0 warnings, 0 errors`. Generation runs locally with zero model calls and only two pure-Python runtime dependencies (`ruamel.yaml`, `tomli-w`). Requires Python 3.12+.

| Target     | Harness        | Project output                   |
| ---------- | -------------- | -------------------------------- |
| `AGY`      | Antigravity    | `.agents/agents/<name>.md`       |
| `CLAUDE`   | Claude Code    | `.claude/agents/<name>.md`       |
| `CODEX`    | Codex          | `.codex/agents/<name>.toml`      |
| `COPILOT`  | GitHub Copilot | `.github/agents/<name>.agent.md` |
| `CURSOR`   | Cursor         | `.cursor/agents/<name>.md`       |
| `GEMINI`   | Gemini CLI     | `.gemini/agents/<name>.md`       |
| `GROK`     | Grok Build     | `.grok/agents/<name>.md`         |
| `KILO`     | Kilo Code      | `.kilo/agents/<name>.md`         |
| `OPENCODE` | OpenCode       | `.opencode/agents/<name>.md`     |

## One source, native settings

```markdown
---
name: reviewer
description: Review assigned changes and report demonstrated defects.
CLAUDE:
  model: inherit
  tools: Read, Glob, Grep
CODEX:
  sandbox_mode: read-only
---

Read the assigned files and requirements. Return findings with file and line references, evidence, and unresolved gaps. Do not implement fixes or delegate further work.
```

Save this source as `.agents/supagents/reviewer.md`. The [complete reviewer example](https://github.com/fmind/agent-supagents/blob/main/examples/reviewer.md) includes all nine targets; retain only those you use. Shared `_*.md` partials reduce duplication across roles via `extends` and `{{BODY}}` (see [partial inheritance](https://github.com/fmind/agent-supagents/blob/main/docs/usage.md#partial-inheritance)).

Only declared target blocks produce outputs. Supagents preserves the Markdown body and merges shared metadata with each target's overrides; Codex receives the body as TOML `developer_instructions`. It does not translate tool names, permissions, or model IDs.

## Commands

| Command                                    | Purpose                                                                |
| ------------------------------------------ | ---------------------------------------------------------------------- |
| `init NAME --target claude --target codex` | Scaffold only selected targets (supports `-n`/`--dry-run`)             |
| `build --diff`                             | Preview content changes and source-to-output mappings                  |
| `build --strict`                           | Reject warnings before writing changed outputs                         |
| `check --strict`                           | Fail on missing, modified, obsolete outputs or warnings; write nothing |
| `list`                                     | Show source-to-output mappings (plain table or `--json`)               |
| `clean --dry-run`                          | Preview obsolete generated files before `clean` removes them           |

Every command supports `-h`/`--help`, `--project` / `--global`, repeatable `-t`/`--target`, `-c`/`--config`, `--source-dir`, `-q`/`--quiet`, and `--json`. `init` without `--target` includes all bundled targets. `build --check` remains an alias for `check`.

By default, a local `.agents/supagents/` selects project scope; otherwise the CLI uses `~/.agents/supagents/`. Builds refuse to overwrite handwritten files, symlinks, sources, or colliding outputs. `clean` refuses invalid or ambiguous sources and requires `--global`, `--yes`, or interactive confirmation before deleting auto-detected global files.

See [usage and configuration](https://github.com/fmind/agent-supagents/blob/main/docs/usage.md) for precedence, safety guarantees, exit codes, and chezmoi integration, and [compatibility evidence](https://github.com/fmind/agent-supagents/blob/main/docs/compatibility.md) for tested host versions and discovery results.

## Plugins and hooks

This repository ships the standalone [/supagent skill](https://github.com/fmind/agent-supagents/blob/main/skills/supagent/SKILL.md), Claude Code, Gemini CLI, and Copilot plugin manifests, and a downstream pre-commit hook. See [plugin installation](https://github.com/fmind/agent-supagents/blob/main/docs/usage.md#plugins-and-hooks).

## Development

```bash
mise trust
mise run install
mise run all
```

Python 3.12+ is supported; `mise` pins the development toolchain and `uv` locks dependencies. CI qualifies Linux and macOS on the pinned toolchain (Python 3.14), plus Linux on Python 3.12 and 3.15, while scheduled security runs also check lowest direct runtime dependencies. The gate audits dependencies and smoke-tests the built wheel with hash-locked runtime dependencies. Lefthook invokes the same `mise` tasks locally.

[MIT license](https://github.com/fmind/agent-supagents/blob/main/LICENSE).
