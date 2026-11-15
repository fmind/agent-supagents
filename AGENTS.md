# AGENTS.md

## Overview

- `agent-supagents` is a Python CLI (`supagents`) that compiles one Markdown source into per-target subagent files for Antigravity, Claude Code, Codex, Gemini CLI, GitHub Copilot, Grok, Cursor, OpenCode, and Kilo Code.
- The repository ships harness manifests (`.claude-plugin/`, `gemini-extension.json`, `plugin.json`), the distributable `/supagent` skill (`skills/supagent/SKILL.md`), and maintainer skills in `.agents/skills/` (`.claude/skills` symlinks `../.agents/skills`).
- Python ≥ 3.12. Tight dependency surface: `typer`, `rich`, `ruamel.yaml`, `pydantic`, `tomli-w`. No I/O outside documented source/output paths.

## Conventions

- **Stack & tooling.** uv for env/lock (`uv_build`); ruff (`format` + `check`) for style; `ty` for types; `pytest` (+ `pytest-cov`, ≥90% gate) for tests; Zensical for the single-page `README.md` docs site. `mise` owns pinned tools and tasks (`mise.toml` / `mise.lock`).
- **Local checks.** `mise run all` (format, check including `jactionlint`, `betterleaks`, and `verify_release.py`, audit, test, docs build, wheel/sdist build, and isolated wheel smoke test) mirrors CI. Run it before delivery.
- **Hooks.** Lefthook runs `check` before commit and `test` before push (`lefthook.yml`). Never bypass with `--no-verify` — fix the root cause.
- **Skill files.** Keep each `SKILL.md` concise (aim for ≤ 110 lines, imperative voice, strict frontmatter per Agent Skills). `skills/supagent/SKILL.md` must stay self-contained without `../../` links outside its folder.

## Workflow

- Keep diffs focused: source-only changes shouldn't touch generated outputs from other repos.
- Follow [.agents/skills/harnesses/SKILL.md](.agents/skills/harnesses/SKILL.md) when adding or updating target harnesses, examples, or host discovery probes (`mise run check:hosts`).
- Follow [.agents/skills/release/SKILL.md](.agents/skills/release/SKILL.md) when cutting releases; run `uv run --locked python scripts/verify_release.py` before tagging.

## Layout

- `src/supagents/` — Python package (`cli.py`, `config.py`, `core.py`, `__main__.py`).
- `tests/` — `pytest` suite (`conftest.py`, `fixtures/`, core/cli/config/hosts/metadata tests).
- `skills/supagent/SKILL.md` — distributable user skill (`/supagent`).
- `.agents/skills/{harnesses,release}/SKILL.md` — repo maintenance skills (linked at `.claude/skills`).
- `zensical.toml` & `docs/index.md` — single-page `README.md` site deployed to GitHub Pages.
- `.github/workflows/{ci,cd,docs,security}.yml` — CI, tag-driven PyPI/GitHub Release CD, Pages deploy, and weekly full-history security scan.
- `scripts/` — `check_hosts.py` (offline host discovery probes) and `verify_release.py` (manifest/tag/changelog verifier).
- `docs/{usage,compatibility}.md` & `examples/reviewer.md` — reference contracts, compatibility matrix, and portable example.
