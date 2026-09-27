# AGENTS.md

## Overview

- agent-supagents is a Python CLI (`supagents`) that compiles one markdown source into per-target subagent files for Antigravity, Claude Code, Codex, Gemini CLI, GitHub Copilot, Grok, Cursor, OpenCode, and Kilo Code.
- The repo also ships harness manifests (`.claude-plugin/`, `gemini-extension.json`, `plugin.json`) and an Agent Skill under `skills/use-agent-supagents/` so the same tree installs as a plugin in Claude Code, Gemini CLI, and GitHub Copilot.
- Python ≥ 3.12. Tight dependency surface: `typer`, `rich`, `ruamel.yaml`, `pydantic`, `tomli-w`. No I/O outside the documented source/output paths.

## Conventions

- **Stack & tooling.** uv for env/lock; ruff (`format` + `check`) for style; [`ty`](https://docs.astral.sh/ty/) for types; `pytest` (+ `pytest-cov`, ≥90% gate) for tests. `mise` owns pinned tools and tasks.
- **Local checks.** `mise run all` (format, check, audit, test, build and isolated wheel smoke test) mirrors CI. Run it before delivery.
- **Hooks.** Lefthook runs `check` before commit and `test` before push (see `lefthook.yml`). Don't bypass with `--no-verify` — fix the underlying issue.
- **Skill files.** Skill bodies (`skills/*/SKILL.md`) load into agent context on every run; verbosity costs budget. Aim for ≤ 110 lines per `SKILL.md`. Use the imperative ("Read X, then write Y") and avoid second-person flavor text aimed at the human reader — that belongs in the README.

## Workflow

- For non-trivial changes, work on a feature branch and open a PR. Keep diffs focused: source-only changes shouldn't touch generated outputs from other repos.
- When changing `src/supagents/`, rerun `mise run check` and `mise run test` — the test suite covers parsing, planning, and idempotent writes.
- When changing `skills/use-agent-supagents/SKILL.md`, re-read the whole file end-to-end after the edit — agents load it as a unit, so coherence matters more than line-level diffs.

## Layout

- `src/supagents/` — Python package: `cli.py` (Typer entry points), `config.py` (targets, scopes), `core.py` (parse/plan/write), `__main__.py` (`python -m supagents`).
- `tests/` — `pytest` suite with fixtures under `tests/fixtures/`; `conftest.py` holds shared scaffolding.
- `skills/use-agent-supagents/SKILL.md` — user-facing Agent Skill: how to author sources, run the CLI, gate CI.
- `.claude-plugin/` — Claude Code plugin manifest (`plugin.json`) and bundled marketplace (`marketplace.json`).
- `gemini-extension.json` — Gemini CLI extension manifest.
- `plugin.json` — GitHub Copilot plugin manifest.
- `.pre-commit-hooks.yaml` — exposes the `supagents-build` hook so downstream repos can `repo: https://github.com/fmind/agent-supagents` it.
- `.github/workflows/{ci,cd}.yml` — CI (lint + test on push/PR) and CD (qualified artifacts published after a GitHub release).
- `mise.toml` / `mise.lock` — tools and canonical tasks; `lefthook.yml` — local hooks.
- `docs/usage.md` — source format, native target references, configuration, and migration contracts.
