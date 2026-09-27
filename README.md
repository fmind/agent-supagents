# Supagents

Maintain shared subagent instructions and generate native configurations for your coding tools. For developers using multiple harnesses, Supagents keeps roles in Git while preserving explicit model, tool, and permission settings for each host.

```bash
uv tool install supagents
supagents init reviewer --project --target claude --target codex
# Replace the scaffold with the reviewer source below.
supagents build --project --diff
supagents build --project --strict
supagents check --project --strict
```

The final check reports `0 would change, 2 unchanged, 0 obsolete, 0 warnings, 0 errors`. Generation runs locally without model calls. Requires Python 3.12+. See the [changelog](https://github.com/fmind/agent-supagents/blob/main/CHANGELOG.md) for release changes.

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

Save this source as `.agents/supagents/reviewer.md`. The [complete reviewer example](https://github.com/fmind/agent-supagents/blob/main/examples/reviewer.md) includes all nine targets; retain only those you use.

Only declared target blocks produce outputs. Supagents preserves the Markdown body and merges shared metadata with each target's overrides; Codex receives the body as TOML `developer_instructions`. It does not translate tool names, permissions, or model IDs. Native settings and parent-session policies determine runtime behavior.

## Commands

| Command                                    | Purpose                                                                |
| ------------------------------------------ | ---------------------------------------------------------------------- |
| `init NAME --target claude --target codex` | Scaffold only selected targets                                         |
| `build --diff`                             | Preview content changes and source-to-output mappings                  |
| `build --strict`                           | Reject warnings before writing changed outputs                         |
| `check --strict`                           | Fail on missing, modified, obsolete outputs or warnings; write nothing |
| `list`                                     | Show source-to-output mappings                                         |
| `clean --dry-run`                          | Preview obsolete generated files before `clean` removes them           |

`init` without `--target` includes all bundled targets. `build --check` remains an alias for the read-only check, and `--dry-run` previews paths without content diffs.

Use `--project` or `--global`, repeatable `--target`, `--config`, and `--source-dir` to select scope and locations. By default, a local `.agents/supagents/` selects project scope; otherwise the CLI uses `~/.agents/supagents/`.

Commands display the selected scope and source directory. Builds refuse to overwrite handwritten files, symlinks, sources, or colliding outputs. Cleanup refuses invalid or ambiguous sources. See [usage and migration](https://github.com/fmind/agent-supagents/blob/main/docs/usage.md) for configuration precedence, safety limits, host references, and chezmoi integration.

See the [compatibility evidence](https://github.com/fmind/agent-supagents/blob/main/docs/compatibility.md) for tested host versions, discovery results, and runtime limits.

## Development

```bash
mise trust
mise run install
mise run all
```

Python 3.12+ is supported; mise pins the development toolchain and uv locks dependencies. CI qualifies Linux and macOS, with an additional Python 3.12 test run. The gate audits dependencies and smoke-tests the built wheel in an isolated environment. Lefthook calls the same check and test tasks. Local checks do not establish hosted CI or live harness delegation results.

The repository also supplies an [Agent Skill](https://github.com/fmind/agent-supagents/blob/main/skills/use-agent-supagents/SKILL.md), Claude Code, Gemini CLI, and Copilot plugin manifests, and a downstream pre-commit hook. See [plugin installation](https://github.com/fmind/agent-supagents/blob/main/docs/usage.md#plugins-and-hooks).

[MIT license](https://github.com/fmind/agent-supagents/blob/main/LICENSE).
