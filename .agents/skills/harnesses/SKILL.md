---
name: harnesses
description: "Add, update, or verify coding-harness targets, scaffolds, examples, and isolated host discovery probes in agent-supagents."
license: MIT
metadata:
  kind: task
  author: Médéric HURIER (Fmind)
  source: github.com/fmind/agent-supagents/tree/main/.agents/skills/harnesses
  created: "2026-11-15"
  updated: "2026-11-22"
---

# Harness Targets

Maintain target definitions, scaffolds, examples, and isolated discovery probes across supported coding harnesses without regressing compilation or safety contracts.

## Workflow

1. Check upstream host documentation for native paths, file suffixes, frontmatter/TOML fields, tool names, and standalone agent listing flags.
1. Update the code, manifests, ignores, and example assets in lockstep:
   - [src/supagents/config.py](../../../src/supagents/config.py): `DEFAULT_TARGETS` (`global_path`, `project_path`, `filename_suffix`, `format`, `body_key`).
   - [src/supagents/cli.py](../../../src/supagents/cli.py): `_INIT_TARGET_DEFAULTS` non-empty boilerplate overrides (keep `AGY` at default `mainAgent: true` so `agy agent` discovers it).
   - [examples/reviewer.md](../../../examples/reviewer.md): valid current native metadata for all bundled targets.
   - [scripts/check_hosts.py](../../../scripts/check_hosts.py): CLI executable and standalone discovery command.
   - [.gitignore](../../../.gitignore) and `keywords` arrays in [pyproject.toml](../../../pyproject.toml), [.claude-plugin/plugin.json](../../../.claude-plugin/plugin.json), [.claude-plugin/marketplace.json](../../../.claude-plugin/marketplace.json), and [plugin.json](../../../plugin.json).
1. Update unit tests under [tests/](../../../tests/) and run the offline host discovery probe:
   ```bash
   mise run check:hosts
   ```
1. Sync documentation strictly separating compilation, discovery, and runtime enforcement: [docs/compatibility.md](../../../docs/compatibility.md), [docs/usage.md](../../../docs/usage.md), [README.md](../../../README.md), [AGENTS.md](../../../AGENTS.md), and [skills/supagent/SKILL.md](../../../skills/supagent/SKILL.md).
1. Run the full gate:
   ```bash
   mise run all
   ```

## Gotchas

- **Isolate host probes**: compile global probes (such as `AGY`) into a temporary `HOME`, pass `--standalone` or equivalent non-daemon flags (`opencode debug agents --standalone`), never execute live model calls, and never print raw captured host stdout/stderr.
- **No cross-harness translation**: keep Supagents as a pass-through metadata + body compiler; do not introduce host schema translators or model aliases.
