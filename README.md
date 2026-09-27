# Supagents

Define a role once, then compile it into native subagent profiles for nine coding harnesses. Keep instructions shared and model, tool, and permission settings explicit for each host.

```bash
uv tool install supagents
supagents init reviewer --project
# Edit .agents/supagents/reviewer.md: write the instructions and keep the desired target blocks.
supagents build --project
supagents build --project --check
```

Requires Python 3.12+. See the [changelog](https://github.com/fmind/agent-supagents/blob/main/CHANGELOG.md) for release changes.

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
AGY:
  subagent: true
  model: inherit
  inheritMcp: false
  tools: [view_file, list_dir, find_by_name, grep_search]
---

Read the assigned files and requirements. Return findings with file and line references, evidence, and unresolved gaps. Do not implement fixes or delegate further work.
```

Only declared target blocks produce outputs. Supagents preserves the Markdown body and merges shared metadata with each target's overrides; Codex receives the body as TOML `developer_instructions`. It does not translate tool names, permissions, or model IDs. Native settings and parent-session policies determine runtime behavior.

## Commands

| Command           | Purpose                                                |
| ----------------- | ------------------------------------------------------ |
| `init NAME`       | Scaffold a source with all bundled targets             |
| `build`           | Validate the complete plan, then write changed outputs |
| `build --check`   | Fail if outputs differ; write nothing                  |
| `build --dry-run` | Preview planned changes                                |
| `list`            | Show source-to-output mappings                         |
| `clean --dry-run` | Preview generated files no longer produced             |
| `clean`           | Remove those orphaned files                            |

Use `--project` or `--global`, repeatable `--target`, `--config`, and `--source-dir` to select scope and locations. By default, a local `.agents/supagents/` selects project scope; otherwise the CLI uses `~/.agents/supagents/`.

Builds refuse to overwrite handwritten files, symlinks, sources, or colliding outputs. Cleanup refuses invalid or ambiguous sources. See [usage and migration](https://github.com/fmind/agent-supagents/blob/main/docs/usage.md) for configuration precedence, safety limits, host references, and chezmoi integration.

## Development

```bash
mise trust
mise run install
mise run all
```

Python 3.12+ is supported; mise pins the development toolchain and uv locks dependencies. CI qualifies Linux and macOS, with an additional Python 3.12 test run. The gate audits dependencies and smoke-tests the built wheel in an isolated environment. Lefthook calls the same check and test tasks. Local checks do not establish hosted CI or live harness delegation results.

The repository also supplies an [Agent Skill](https://github.com/fmind/agent-supagents/blob/main/skills/use-agent-supagents/SKILL.md), Claude Code, Gemini CLI, and Copilot plugin manifests, and a downstream pre-commit hook. See [plugin installation](https://github.com/fmind/agent-supagents/blob/main/docs/usage.md#plugins-and-hooks).

[MIT license](https://github.com/fmind/agent-supagents/blob/main/LICENSE).
