# Changelog

All notable changes to this project are documented in this file.

## [1.5.0] - 2026-11-15

### 🚀 Features

- Replace `/use-agent-supagents` with standalone `/supagent` skill and add repository maintenance skills (`harnesses`, `release`).
- Publish a single-page README documentation site via Zensical on GitHub Pages (`https://fmind.github.io/agent-supagents/`).

### 🐛 Bug Fixes

- Preserve canonical sources during cleanup when source and output directories overlap.
- Quote scaffold names and custom target keys correctly; reject target names without an uppercase form.
- Reject unencodable output before writing and remove temporary files after encoding failures.
- Keep compatibility probes independent of personal Supagents output configuration.
- Isolate `ruamel.yaml` round-trip parser/dumper state per call so YAML directives cannot leak across rendered outputs.
- Detect generated ownership markers across CRLF line endings and expand `~` on `--config` and `--source-dir`.
- Align Antigravity reviewer example tools with current `agy` registry names and update the OpenCode 2.x discovery probe (`opencode debug agents --standalone`).

### 🧹 Miscellaneous

- Refresh the development toolchain (`uv_build`, `jactionlint`, `betterleaks`, `dprint`, `uv`), Python dependencies (including `typer` 0.29), `linux-arm64` lockfile support, and pinned GitHub Actions; automate tag-driven PyPI/GitHub releases, Docs deployment, and weekly security scans across Python 3.12, 3.14, and 3.15.

## [1.4.1] - 2026-10-06

### 🐛 Bug Fixes

- _(cli)_ Print paths and diagnostics verbatim

### 🧹 Miscellaneous

- _(deps)_ Upgrade mise tools to latest
- _(deps)_ Upgrade python dependencies to latest
- _(deps)_ Upgrade github actions to latest
- _(deps)_ Upgrade dprint plugins to latest
- Align metadata and task descriptions
- Remove unreferenced hero image

## [1.4.0] - 2026-09-27

### 🚀 Features

- Add strict verification and clearer agent onboarding

### 🐛 Bug Fixes

- Preserve long paths and diagnostics in CLI output

## [1.3.0] - 2026-09-27

### 🚀 Features

- Compile native subagents safely across coding harnesses

### 🧹 Miscellaneous

- Add skill source URLs to metadata and bump minor version

## [1.1.0] - 2026-05-31

### 🚀 Features

- Add support for OpenCode

### 🐛 Bug Fixes

- Move image position on README.md

### 📚 Documentation

- _(readme)_ Add hero image at the top

## [1.0.0] - 2026-05-07

### 🚀 Features

- Initial release of supagents v1.0.0

### 🐛 Bug Fixes

- _(ci)_ Pin astral-sh/setup-uv to v8.1.0
