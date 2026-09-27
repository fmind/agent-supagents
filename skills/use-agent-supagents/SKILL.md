---
name: use-agent-supagents
description: Compile shared role instructions into native subagent profiles for Antigravity, Claude Code, Codex, Copilot, Cursor, Gemini CLI, Grok, Kilo, and OpenCode.
license: MIT
---

# Use Supagents

Read [compatibility evidence](../../docs/compatibility.md) for tested host versions and limits. Read [usage and configuration](../../docs/usage.md) for target paths, precedence, and migration rules. Use Supagents to share role instructions while keeping model, tool, and permission settings explicit for each harness.

## Workflow

1. Inspect existing sources, generated outputs, Git status, and installed harness versions. Preserve handwritten profiles and unrelated work.
1. Select project (`.agents/supagents/`) or global (`~/.agents/supagents/`) scope. Use `supagents init NAME --project --target claude --target codex` to scaffold selected targets; adapt the target list to the installed hosts.
1. Write a bounded role: task inputs, responsibilities, allowed actions, handoff format, and stop conditions. Read the relevant host's current documentation before setting native metadata.
1. Keep shared `name` and `description` fields and the Markdown body portable. Put model choices, tool allowlists, permissions, and other host settings in their target blocks. Omit model overrides unless requested or required by the task.
1. Preview with `supagents build --project --diff`; inspect warnings and output mappings. For custom layouts pass `--source-dir PATH --config FILE` consistently.
1. Generate with `supagents build --project --strict`; verify expected and obsolete outputs with `supagents check --project --strict`. Invalid source/configuration, collisions, and unowned outputs must be fixed before generating.
1. Confirm native discovery in each installed host, then run a bounded runtime task when authorized. Report compilation, discovery, and runtime results separately.

## Native formats

- `AGY`, `CLAUDE`, `COPILOT`, `CURSOR`, `GEMINI`, `GROK`, `KILO`, and `OPENCODE` emit Markdown with merged YAML frontmatter.
- `CODEX` emits TOML and stores the shared body plus `APPEND_BODY` as `developer_instructions`; do not declare that field separately. Supply nonempty `name` and `description` strings.
- `OUTPUT` overrides a file path. Relative overrides resolve beside the source; configured project directories resolve from the working directory.
- Custom targets can select `format: toml` and a `body_key`; Supagents does not translate native fields or validate complete harness schemas.

## Boundaries

- Generated markers identify owned outputs. Never add one to a handwritten file to bypass a conflict; reconcile and back up the original deliberately.
- Run `clean --dry-run` before authorized cleanup. Cleanup fails on source warnings/errors and only scans configured output directories.
- Supply the child's task and relevant evidence explicitly; do not assume it inherits the parent transcript or global instructions.
- Tool names and policy enforcement differ by host. Instructions and format portability do not imply equivalent sandboxing or delegation.
- For chezmoi, generate into managed source paths and deploy through chezmoi. Keep the mapping config repository-only and make generation drift a check.
