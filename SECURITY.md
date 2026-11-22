# Security Policy

## Supported versions

Only the [latest release](https://github.com/fmind/agent-supagents/releases/latest) is supported. Fixes land on `main` and ship in the next release; older tags receive no backports.

## Reporting a vulnerability

Report privately through [GitHub private vulnerability reporting](https://github.com/fmind/agent-supagents/security/advisories/new) or to [contact@fmind.dev](mailto:contact@fmind.dev), the contact address published on [fmind.dev](https://www.fmind.dev/). Include the affected version, impact, and a minimal reproduction with sensitive data removed. Do not open a public issue for an undisclosed vulnerability, and never include secrets or tokens in a report.

This is a personal project maintained on a best-effort basis; there is no response-time commitment.

## Scope

In scope:

- The `src/supagents/` CLI and compiler, including YAML, Markdown, and TOML parsing and partial `extends` resolution.
- Path, symlink, and overwrite safety boundaries in `build`, `clean`, and `init`.
- Shipped GitHub Actions workflows and plugin manifests (`.claude-plugin/`, `gemini-extension.json`, `plugin.json`).

Out of scope:

- Upstream coding harnesses (Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot, Antigravity, OpenCode, Kilo Code, Grok) and their runtime sandboxes.
- User-authored agent prompt instructions, tool lists, and permissions configured in source files.
