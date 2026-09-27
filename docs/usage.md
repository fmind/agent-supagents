# Usage and configuration

## Source contract

Sources are UTF-8 Markdown files with YAML frontmatter and a nonempty body. Filenames match `[a-z0-9][a-z0-9_-]*.md`; discovery reads the selected directory without recursion. A BOM and CRLF line endings are accepted.

Lowercase and camelCase frontmatter fields are shared. Uppercase keys select targets; an empty block (`CODEX: {}`) enables a target. Target metadata overrides shared fields without a deep merge. Keep host-specific settings inside their target blocks. Unknown targets and directives produce warnings; malformed `OUTPUT` values are errors.

Two uppercase directives are supported inside a target:

- `APPEND_BODY`: append host-specific instructions after the shared body.
- `OUTPUT`: override the output file. Relative paths resolve beside the source; `~` expands to the current home. Paths outside the selected scope produce a warning; use only trusted sources and configuration.

Codex output requires nonempty `name` and `description` strings and reserves `developer_instructions` for the body. TOML serialization preserves nested tables and multiline instructions; YAML values that TOML cannot represent, such as null, fail before any writes. Other metadata passes through unchanged: Supagents does not claim complete validation against each harness's evolving schema.

## Locations and precedence

1. `--project` and `--global` explicitly select output scope and are mutually exclusive.
1. Otherwise, `.agents/supagents/` in the current directory selects project scope; absence selects global scope. Parent directories are not searched.
1. `--source-dir PATH` overrides only source discovery, including for `init`, `list`, and `clean`. Specify scope explicitly for custom layouts. A missing explicit source directory is an error except when `init` creates it.
1. `--config FILE` selects configuration. Otherwise, read `$XDG_CONFIG_HOME/supagents/config.yaml`, falling back to `~/.config/supagents/config.yaml`.
1. Configuration overrides bundled target settings per field. Invalid files fail; an absent default configuration uses bundled defaults. Config target names are case-insensitive.
1. Source `OUTPUT` takes precedence over the configured directory and suffix.

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

Custom targets need both paths. `format` defaults to `markdown`, `filename_suffix` to `.md`, and TOML `body_key` to `developer_instructions`. Paths in `project_path` resolve from the current working directory, not the config file. Prefer relative project paths; sources and configuration are trusted local inputs, not sandboxed capabilities.

## Chezmoi integration

Keep canonical sources in `dot_agents/supagents/`. Use a repository-only config to map project outputs into chezmoi's source paths (`dot_claude/agents`, `dot_codex/agents`, `dot_gemini/private_config/agents`, and so on).

```bash
supagents build --project --source-dir dot_agents/supagents --config supagents.yaml
supagents check --strict --project --source-dir dot_agents/supagents --config supagents.yaml
```

Exclude `supagents.yaml` from chezmoi deployment. Keep generated native files tracked and exempt them from other formatters; use the second command as a repository gate. Preview and apply the affected targets through chezmoi. Generation should not run as an installation hook or write directly into the deployed home while editing the source repository.

## Verification and previews

```bash
supagents init reviewer --project --target claude --target codex
supagents build --project --diff
supagents build --project --strict
supagents check --project --strict --diff
```

`init --target` is repeatable and case-insensitive, accepts custom targets from `--config`, and rejects unknown target names. With no target filter it retains the nine bundled targets for compatibility. Scaffolds contain TODO instructions; use the [reviewer example](../examples/reviewer.md) as a practical starting point and retain the targets you need.

`build --diff` previews additions and edits as unified content diffs, without writing. `check --diff` also previews obsolete files as removals; it never removes them. `--diff` can accompany `--dry-run` or `--check`. Every command reports explicit or auto-detected scope and the source directory; previews show source → target → output mappings.

`check` and `build --check` both fail on missing, modified, or obsolete generated outputs. `--strict` additionally fails on source warnings, including unknown target/directive names. `build --strict` rejects warnings before any writes. A warning during a non-strict check skips orphan scanning because ownership is ambiguous; use `check --strict` in CI. Checks require an existing source directory, even with default paths; an empty existing directory is valid.

Orphan checks and cleanup inspect marker-bearing regular files directly in the selected targets' configured output directories. They cannot locate old directories after configuration changes or obsolete custom `OUTPUT` paths elsewhere. Unreadable output directories/files fail the scan. Handwritten files and symlinks are preserved. Missing or modified expected outputs are checked wherever their current `OUTPUT` points.

## Safety and migration from 1.2

Builds now validate every source, rendering, output collision, and existing-file ownership before writing. Invalid sources no longer permit partial successful writes. Each file is replaced atomically, but the entire build is not a transaction: filesystem failures can leave a partially written set, and concurrent writers are not locked. Rerun after fixing the reported error.

Only marker-bearing generated files can be replaced. An existing handwritten file or symlink causes failure even in `--check`. Move it to a deliberate backup and reconcile its content into the source before generating; no overwrite flag bypasses ownership. The generated marker is an ownership convention, not tamper protection. Parent directories may be symlinks; inspect configured paths before building.

`clean` removes only marker-bearing orphan files directly in configured output directories, never handwritten files or symlinks. Missing or unreadable source directories, broken source links, invalid sources, and source warnings abort cleanup. An existing empty source directory deliberately permits orphan cleanup. It does not discover old directories after configuration changes, nested `OUTPUT` files, or custom paths outside those directories. Preview first; move obsolete files separately when migrating paths.

`init` refuses source symlinks even with `--force` and replaces regular files atomically. Invalid output paths and filesystem errors produce CLI diagnostics instead of tracebacks.

Build/check exit 0 on success, 1 for target errors, check drift, or warnings with `--strict`, and 2 for fatal source/configuration/I/O errors. Since 1.4, `build --check` also rejects obsolete outputs and missing source directories; use `clean --dry-run` to review obsolete files before cleanup. `list` now fails for invalid sources. Invalid configuration shapes no longer silently fall back to defaults. An unknown source target is a warning unless `--strict` is selected; an unknown CLI `--target` is always an error.

## Native behavior and verification

The [compatibility matrix](compatibility.md) records tested versions and separates compiler, discovery, and permission evidence. Use host documentation for fields and discovery: [Antigravity](https://antigravity.google/docs/subagents/), [Claude Code](https://code.claude.com/docs/en/sub-agents), [Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Copilot](https://docs.github.com/en/copilot/reference/custom-agents-configuration), [Cursor](https://cursor.com/docs/subagents), [Gemini CLI](https://geminicli.com/docs/core/subagents/), [Grok Build](https://docs.x.ai/build/features/subagents), [Kilo Code](https://kilo.ai/docs/customize/custom-subagents), and [OpenCode](https://opencode.ai/docs/agents/).

Avoid pinning models unless the task needs one. Omission or `inherit` is host-specific. Tool allowlists use native names; shell access can write files even if the edit tool is absent. Codex sandbox defaults can be overridden by parent runtime policy. Agent instructions alone are not access control.

Give the child the exact task, relevant files/diff, acceptance criteria, and expected result. Parent-context inheritance and delegation routing differ across harnesses. Verify generated syntax, native discovery, and a bounded runtime task separately; compilation does not prove that a host selects an agent, applies its tool restrictions, or succeeds with its provider.

## Plugins and hooks

The skill explains operation; plugin installation does not install the Python CLI. Install a matching Supagents package separately. Existing manifests remain available for their host plugin managers:

```bash
claude plugin marketplace add fmind/agent-supagents
claude plugin install agent-supagents
# Gemini CLI:
gemini extensions install https://github.com/fmind/agent-supagents
# Copilot:
copilot plugin install fmind/agent-supagents
```

The `.pre-commit-hooks.yaml` hook runs `supagents build` for conventional `.agents/supagents/*.md` sources. Custom layouts must override `args` and `files`. Pin a released tag or immutable revision in downstream configuration. This repository uses mise and Lefthook for its own development checks.
