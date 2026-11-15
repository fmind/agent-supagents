# Compatibility evidence

This matrix records local checks for the post-1.4.1 candidate on Linux, 2026-11-15. Host versions are observations, not minimum-version promises. CI runs the compiler suite on Python 3.12, the pinned 3.14 development interpreter, and Python 3.15; Linux and macOS qualify the package separately from native hosts. Local results do not establish hosted CI results for this candidate.

| Target      | Host version inspected | Generated format and shared body | Native discovery              | Effective runtime permissions |
| ----------- | ---------------------- | -------------------------------- | ----------------------------- | ----------------------------- |
| Antigravity | 1.5.9                  | Passed                           | Passed, isolated global scope | Not tested                    |
| Claude Code | 2.1.325                | Passed                           | Not tested                    | Not tested                    |
| Codex       | Not installed          | Passed, TOML parsed              | Not tested                    | Not tested                    |
| Copilot CLI | 1.0.112                | Passed                           | Not tested                    | Not tested                    |
| Cursor      | Not installed          | Passed                           | Not tested                    | Not tested                    |
| Gemini CLI  | Not installed          | Passed                           | Not tested                    | Not tested                    |
| Grok Build  | Not installed          | Passed                           | Not tested                    | Not tested                    |
| Kilo Code   | Not installed          | Passed                           | Not tested                    | Not tested                    |
| OpenCode    | 2.3.0                  | Passed                           | Passed, project scope         | Not tested                    |

## Reproduce

```bash
mise run test
mise run check:hosts
```

`tests/test_verification.py` compiles [the reviewer example](../examples/reviewer.md) for all nine bundled targets, checks shared-body preservation and Codex TOML, then checks idempotence and orphan absence. These tests validate compiler behavior rather than each host's complete native schema.

`check:hosts` builds a synthetic reviewer in a temporary project using bundled target settings, ignoring personal Supagents configuration. It reads installed CLI versions and probes `agy agent`, `grok inspect --json`, and `opencode debug agents --standalone`. Antigravity uses a separate temporary home for its global profile. The probe prints only host versions and status, discards captured configuration output, and makes no model calls. Missing tools are reported as unavailable; a failed probe of an installed tool exits nonzero. Other hosts currently receive version inspection only.

Antigravity 1.5.9's standalone `agy agent` lists global `mainAgent: true` (default) profiles in isolated global scope while omitting project profiles and `mainAgent: false` roles. [Antigravity's documentation](https://antigravity.google/docs/subagents/#agent-location-and-discovery) specifies both project and global locations; project-session and subagent-only discovery remain unverified by this listing probe.

## Interpret the results

1. **Generated** establishes output syntax, shared instructions, and reproducibility.
1. **Discovered** establishes that a specific installed host recognizes the named profile in the tested scope.
1. **Runtime permissions** require a separately authorized bounded task that exercises allowed and denied actions with the actual parent policy. No such runtime result is claimed here.

The reviewer example includes explicit restrictions for several hosts. Other fields use host defaults. Its instructions alone do not enforce read-only access, and shell tools, plugins, MCP, and parent policy can affect effective access. Consult the [native references and permission limits](usage.md#native-behavior-and-verification) before deployment.

Refresh the matrix after changing native fields or upgrading a host: retain the exact host version, scope, observed result, and verification limit. A package test or discovery probe must not be reported as permission enforcement or successful delegation.
