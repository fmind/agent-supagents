# AGENTS.md

## Overview

- `agent-supagents` is a Python CLI (`supagents`) that compiles one Markdown source into native subagent files for Antigravity, Claude Code, Codex, Gemini CLI, GitHub Copilot, Grok, Cursor, OpenCode, and Kilo Code. See [README.md](README.md) for quickstart and user usage.
- Ships harness manifests (`.claude-plugin/`, `gemini-extension.json`, `plugin.json`), the distributable `/supagent` skill (`skills/supagent/SKILL.md`), and maintainer skills in `.agents/skills/` (`.claude/skills` symlinks `../.agents/skills`).
- Python ≥ 3.12. Minimal runtime dependencies: `ruamel.yaml` and `tomli-w` (stdlib `argparse` CLI and frozen `dataclasses` config). No I/O outside documented source/output paths.

## Conventions

- **Stack & tooling**: `uv` owns `.venv`/`uv.lock` (`uv_build`); `ruff` + `dprint` format; `ty` checks types; `deptry` checks deps; `pytest` (+ `pytest-cov` ≥90% branch gate, `pytest-socket`, `pytest-timeout`) runs offline tests; Zensical builds the single-page `README.md` docs site. `mise` pins all tools (`mise.toml` / `mise.lock`).
- **Local commands**: `mise run install` (sync deps + Lefthook), `mise run format` (rewrite sources/docs), `mise run check` (`check:local` + `check:network`), `mise run test`, `mise run build:docs`, `mise run serve:docs`, and `mise run all` (read-only `check` → `test` → `build`, mirroring CI). Run `mise run all` before delivery.
- **Hooks**: Lefthook runs staged formatters + `check:local` on `pre-commit` and `check:network` + `test` on `pre-push` (`lefthook.yml`). Never bypass with `--no-verify`.
- **Skill files**: keep each `SKILL.md` concise (≤110 lines, imperative voice, strict Agent Skills frontmatter). `skills/supagent/SKILL.md` must stay self-contained without `../` links outside its folder.

## Workflow

- Keep diffs focused: source-only changes must not touch generated outputs from other repos.
- Follow [.agents/skills/harnesses/SKILL.md](.agents/skills/harnesses/SKILL.md) when adding or updating targets, examples, or host discovery probes (`mise run check:hosts`).
- Follow [.agents/skills/release/SKILL.md](.agents/skills/release/SKILL.md) when cutting releases.

## Layout

- `src/supagents/` — package (`cli.py`, `config.py`, `core.py`, `sources.py`, `__main__.py`).
- `tests/` — `pytest` suite (`conftest.py`, `fixtures/`, `test_{cli,config,core,hosts,metadata,native_targets,partials,verification}.py`).
- `skills/supagent/SKILL.md` — distributable user skill (`/supagent`).
- `.agents/skills/{harnesses,release}/SKILL.md` — repo maintenance skills (linked at `.claude/skills`).
- `zensical.toml` & `docs/index.md` — single-page `README.md` site deployed to GitHub Pages.
- `.github/workflows/{ci,cd,docs,security}.yml` — CI, tag-driven PyPI/GitHub Release CD, Pages deploy, and weekly security/online-actions scan.
- `scripts/` — `check_hosts.py` (offline host discovery probes), `smoke_wheel.py` (hash-locked isolated wheel smoke test), and `verify_release.py` (manifest/tag/changelog verifier).
- `docs/{usage,compatibility}.md` & `examples/reviewer.md` — reference contracts, compatibility matrix, and portable example.
