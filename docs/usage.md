# Usage and configuration

## Source contract

Sources are UTF-8 Markdown files with YAML frontmatter and a body (empty child bodies are allowed when inheriting a non-empty preamble partial without `{{BODY}}`). Filenames match `[a-z0-9][a-z0-9_-]*.md`; discovery reads the selected directory without recursion. Files starting with `_` (`_[a-z0-9][a-z0-9_-]*.md`) are partials rather than standalone sources. BOM and CRLF line endings are accepted.

Frontmatter fields split into shared metadata and target blocks:

- **Shared keys**: lowercase and camelCase fields propagate to every target. `extends` is reserved for partial inheritance and omitted from outputs.
- **Target blocks**: uppercase keys select targets. An empty block (`CODEX: {}`) enables a target; `CODEX: false` disables it (standalone or suppressing an inherited target).
- **Overrides & validation**: target metadata overrides shared keys without deep merging. Unknown targets and directives warn on concrete sources, fail closed on `_*.md` partials, and malformed `OUTPUT` values are errors.

Two uppercase directives are supported inside a target:

- `APPEND_BODY`: append host-specific instructions after the shared body (chained base-then-child when inheriting).
- `OUTPUT`: override the output file. Relative paths resolve beside the source; `~` expands to the current home. Paths outside the selected scope warn.

### Partial inheritance

Factor repeated target settings, permissions, and output contracts into `_*.md` partials in the same source directory.

`.agents/supagents/_readonly.md`:

```markdown
---
CLAUDE:
  model: inherit
  tools: Read, Glob, Grep
CODEX:
  sandbox_mode: read-only
---

{{BODY}}

## Output Contract

Return findings with file:line evidence.
```

`.agents/supagents/security.md`:

```markdown
---
extends: _readonly
name: security
description: Audit security boundaries.
---

Inspect inputs, secrets, and permissions.
```

Inheritance rules:

- **Order & deduplication**: pass `extends: _partial` or a left-to-right list `extends: [_a, _b]`. Ancestors linearize in deduplicated post-order so shared bases never clobber sibling overrides or duplicate text.
- **Body merging**: partials may be frontmatter-only, place `{{BODY}}` once as a child slot (non-slot siblings insert above `{{BODY}}` without consuming it), or supply a preamble prepended before the child body.
- **Opt-outs & safety**: re-enabling a `TARGET: false` target later starts from a fresh block. Symlinked partials, path traversal, and inheritance cycles are rejected.

Codex output requires nonempty `name` and `description` strings and reserves `developer_instructions` for the body. TOML serialization preserves nested tables and multiline instructions; YAML values that TOML cannot represent (such as `null`) fail before any writes. Other metadata passes through unchanged.

## Locations and precedence

1. `--project` (`-p`) and `--global` (`-g`) explicitly select output scope and are mutually exclusive.
1. Otherwise, `.agents/supagents/` in the current directory selects project scope; absence selects global scope. Parent directories are not searched.
1. `--source-dir PATH` overrides only source discovery, including for `init`, `list`, and `clean`. A missing explicit source directory fails except when `init` creates it.
1. `--config FILE` (`-c`) selects configuration; otherwise Supagents reads `$XDG_CONFIG_HOME/supagents/config.yaml` (fallback `~/.config/supagents/config.yaml`).
1. Configuration overrides bundled target settings per field. Invalid files, broken default config symlinks, or duplicate case-colliding target keys fail closed.
1. Source `OUTPUT` takes precedence over configured directories and suffixes.

| Target     | Global directory             | Format / suffix        |
| ---------- | ---------------------------- | ---------------------- |
| `AGY`      | `~/.gemini/config/agents/`   | Markdown / `.md`       |
| `CLAUDE`   | `~/.claude/agents/`          | Markdown / `.md`       |
| `CODEX`    | `~/.codex/agents/`           | TOML / `.toml`         |
| `COPILOT`  | `~/.copilot/agents/`         | Markdown / `.agent.md` |
| `CURSOR`   | `~/.cursor/agents/`          | Markdown / `.md`       |
| `GEMINI`   | `~/.gemini/agents/`          | Markdown / `.md`       |
| `GROK`     | `~/.grok/agents/`            | Markdown / `.md`       |
| `KILO`     | `~/.config/kilo/agents/`     | Markdown / `.md`       |
| `OPENCODE` | `~/.config/opencode/agents/` | Markdown / `.md`       |

Antigravity and Gemini CLI are separate targets and directories. OpenCode and Kilo global directories can be overridden for a custom config home.

```yaml
# https://github.com/fmind/agent-supagents/blob/main/docs/usage.md
targets:
  CODEX:
    project_path: dot_codex/agents
  CLAUDE:
    project_path: dot_claude/agents
  MYTOOL:
    global_path: ~/.mytool/agents
    project_path: .mytool/agents
    filename_suffix: .toml
    format: toml
    body_key: instructions
```

Custom targets need both paths and a name containing a letter with an uppercase form. `format` defaults to `markdown`, `filename_suffix` to `.md`, and TOML `body_key` to `developer_instructions`. Relative `project_path` values resolve from the current working directory (`~` expands in both scopes).

## Chezmoi integration

Keep canonical sources in `dot_agents/supagents/`. Use a repository-only config to map project outputs into chezmoi's source paths (`dot_claude/agents`, `dot_codex/agents`, `dot_gemini/private_config/agents`, and so on).

```bash
supagents build --project --source-dir dot_agents/supagents --config supagents.yaml
supagents check --strict --project --source-dir dot_agents/supagents --config supagents.yaml
```

Exclude `supagents.yaml` from chezmoi deployment. Keep generated native files tracked and exempt them from other formatters; use the second command as a repository gate. Preview and apply the affected targets through chezmoi without writing directly into the deployed home while editing the source repository.

## Verification, previews, and automation

```bash
supagents init reviewer --project --target claude --target codex
supagents build --project --diff
supagents build --project --strict
supagents check --project --strict --json
```

- **Scaffolding (`init`)**: `--target` is repeatable, case-insensitive, accepts custom targets from `--config`, and rejects unknown targets. Without `--target`, all nine bundled targets are included. `-n`/`--dry-run` previews creation without writing. Start from the [reviewer example](../examples/reviewer.md) for practical defaults.
- **Previews (`--diff`, `-n`/`--dry-run`)**: `build --diff` previews additions and edits as unified diffs without writing; `check --diff` also previews obsolete files as removals. Output is plain text with zero emoji or markup rewriting.
- **Machine output (`--json`, `-q`/`--quiet`)**: all five commands accept `--json` (one schema-stable JSON object on `stdout`, empty `stdout` + `stderr` diagnostics on fatal failure) and `-q`/`--quiet` to suppress routine status lines. Color follows TTY, `NO_COLOR`, and `TERM=dumb`.
- **Checks (`check`, `build --check`)**: fail on missing, modified, or obsolete outputs; `--strict` also fails on warnings. Non-strict checks skip orphan scanning when warnings exist. Checks require an existing source directory (empty is valid).
- **Orphan scope**: orphan scans inspect marker-bearing regular files directly in selected targets' configured output directories, preserving handwritten files and symlinks. Unreadable directories fail closed.

## Safety guarantees

- **Validate before writing**: builds validate every source, UTF-8 encoding, output collision, and existing-file ownership before writing. Each file is written via same-directory temp file + `fsync` + atomic rename, honoring umask.
- **Ownership markers**: only marker-bearing regular files are overwritten; handwritten files, symlinks, directories, and FIFOs fail closed. Back up and reconcile handwritten files into sources instead of adding markers manually.
- **Safe cleanup (`clean`)**: removes only marker-bearing orphan files in configured output directories, preserving handwritten files, symlinks, sources, and partials (even when directories overlap). Invalid or missing sources abort cleanup with exact failing paths; auto-detected global cleanup requires `--global`, `--yes` (`-y`), or interactive TTY confirmation (`--no-input` disables prompts).
- **Safe scaffolding (`init`)**: refuses source symlinks even with `--force` and writes regular files atomically.

## Exit codes

| Code  | Meaning                                                                                                                 |
| ----- | ----------------------------------------------------------------------------------------------------------------------- |
| `0`   | Success (including explicit `-h`/`--help`, `--version`, and clean `BrokenPipeError`)                                    |
| `1`   | Operational failure (drift, config/source/partial/I/O error, `--strict` warning, unconfirmed global `clean`)            |
| `2`   | CLI usage error (unknown flag, unknown `--target`, mutually exclusive options, invalid `init` name, missing subcommand) |
| `130` | Interrupted (`SIGINT`)                                                                                                  |

## Upgrading

- **From 1.6 to 2.0**: operational, config, parse, and I/O failures now exit `1`, reserving exit `2` for CLI usage errors. Auto-detected global `clean` now requires `--global`, `--yes`, or TTY confirmation. Stdlib `argparse` and `dataclasses` replaced `typer`, `rich`, and `pydantic`.
- **From 1.5 to 1.6**: lowercase `extends` is reserved for `_*.md` partials (non-`_*` values fail with `ParseError`), `_*.md` files are excluded from concrete sources, and warnings/errors inside partials fail closed.
- **From 1.2/1.3 to 1.4+**: `build --check` rejects obsolete outputs and missing source directories, `list` fails on invalid sources, and invalid config shapes fail closed instead of falling back to defaults.

See [CHANGELOG.md](../CHANGELOG.md) for full release notes.

## Native behavior and verification

The [compatibility matrix](compatibility.md) records tested versions and separates compiler, discovery, and permission evidence. Consult upstream host documentation for fields and discovery: [Antigravity](https://antigravity.google/docs/subagents/), [Claude Code](https://code.claude.com/docs/en/sub-agents), [Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Copilot](https://docs.github.com/en/copilot/reference/custom-agents-configuration), [Cursor](https://cursor.com/docs/subagents), [Gemini CLI](https://geminicli.com/docs/core/subagents/), [Grok Build](https://docs.x.ai/build/features/subagents), [Kilo Code](https://kilo.ai/docs/customize/custom-subagents), and [OpenCode](https://opencode.ai/docs/agents/).

Avoid pinning models unless the task needs one; omission and `inherit` are host-specific. Tool allowlists use native names, shell tools can still mutate files without an edit tool, and Codex sandbox defaults can be overridden by parent runtime policy. Agent instructions alone are not access control.

Give each child agent the exact task, relevant files or diff, acceptance criteria, and expected output format. Verify generated syntax, native discovery, and a bounded runtime task separately.

## Plugins and hooks

The [/supagent skill](../skills/supagent/SKILL.md) explains operation; skill or plugin installation does not install the Python CLI. Install a matching Supagents package separately (`uv tool install supagents`). Install the standalone skill or host plugins from this repository:

```bash
skills add fmind/agent-supagents -s supagent
claude plugin marketplace add fmind/agent-supagents
claude plugin install agent-supagents
# Gemini CLI:
gemini extensions install https://github.com/fmind/agent-supagents
# Copilot:
copilot plugin install fmind/agent-supagents
```

The `.pre-commit-hooks.yaml` hook runs `supagents build` for conventional `.agents/supagents/*.md` and `_*.md` sources. Custom layouts must override `args` and `files`. Pin a released tag or immutable revision in downstream configuration.
