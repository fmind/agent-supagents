---
name: supagent
description: "Scaffold, compile, check, and clean subagent profiles and _*.md partials with supagents CLI for Antigravity, Claude, Codex, Copilot, Cursor, Gemini, Grok, Kilo, and OpenCode."
license: MIT
metadata:
  kind: task
  author: Médéric HURIER (Fmind)
  source: github.com/fmind/agent-supagents/tree/main/skills/supagent
  created: "2026-05-07"
  updated: "2026-11-22"
---

# Supagent

Compile one Markdown role file with shared instructions and explicit native target blocks into per-harness subagent definitions. Read [usage and configuration](https://github.com/fmind/agent-supagents/blob/main/docs/usage.md) for target paths and precedence, and [compatibility evidence](https://github.com/fmind/agent-supagents/blob/main/docs/compatibility.md) for verified host versions.

## Workflow

1. Inspect existing sources, generated outputs, Git status, and installed harness versions; preserve handwritten profiles and unrelated work.
1. Pick project (`.agents/supagents/`) or global (`~/.agents/supagents/`) scope, then scaffold only active harnesses:
   ```bash
   supagents init NAME --project --target claude --target codex
   ```
1. Write a bounded role: task inputs, allowed actions, handoff format, and stop conditions. Keep shared `name`, `description`, and the body portable; put model, tool allowlists, and permission settings inside each host's uppercase target block after checking current host docs.
1. Preview diffs and mappings without writing:
   ```bash
   supagents build --project --diff
   ```
   Pass `--source-dir PATH --config FILE` consistently for custom or chezmoi layouts; pass `--json` for machine-readable output.
1. Compile and verify strictly with zero warnings, errors, drift, or obsolete files:
   ```bash
   supagents build --project --strict
   supagents check --project --strict
   ```
1. Verify native discovery in each installed host separately from compilation and bounded runtime runs.

## Native Formats

- `AGY`, `CLAUDE`, `COPILOT`, `CURSOR`, `GEMINI`, `GROK`, `KILO`, and `OPENCODE` emit Markdown with merged YAML frontmatter.
- `CODEX` emits TOML (`name` and `description` required) and stores the body plus `APPEND_BODY` in `developer_instructions`.
- `OUTPUT` overrides an output path (relative paths resolve beside the source); custom targets in config can set `format: toml` and `body_key`.
- Shared `_*.md` partials in the source directory factor repeated target settings and body slots (`{{BODY}}`) via `extends: _name` or `extends: [_a, _b]`; `TARGET: false` disables an inherited target.

## Gotchas

- **Respect ownership markers**: never insert a generated marker into a handwritten file; back up and reconcile into the source first.
- **Preview deletions first**: run `supagents clean --dry-run` (`-n`) before authorized `supagents clean`; auto-detected global cleanup requires `--global` or `--yes` (`-y`), and cleanup scans only configured output directories.
- **No implicit safety parity**: Supagents passes target metadata verbatim without translating tools or validating full host schemas, and role instructions alone do not enforce permissions.
- **Do not write deployed home during chezmoi edits**: compile into chezmoi source paths (`--project --source-dir ... --config ...`) and apply via chezmoi.
