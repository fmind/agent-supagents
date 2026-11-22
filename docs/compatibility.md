# Compatibility evidence

This matrix records local checks on Linux (2026-11-22, post-v1.6.0 working tree). Host versions are observations, not minimum-version promises. CI qualifies Linux and macOS on Python 3.14, plus Linux on Python 3.12 and 3.15, separately from native hosts. Automated checks do not verify effective runtime permissions.

| Target      | Host version inspected | Generated format and shared body | Native discovery              |
| ----------- | ---------------------- | -------------------------------- | ----------------------------- |
| Antigravity | 1.5.14                 | Passed                           | Passed, isolated global scope |
| Claude Code | Unavailable            | Passed                           | Not tested                    |
| Codex       | Unavailable            | Passed, TOML parsed              | Not tested                    |
| Copilot CLI | 1.0.114                | Passed                           | Not tested                    |
| Cursor      | Unavailable            | Passed                           | Not tested                    |
| Gemini CLI  | Unavailable            | Passed                           | Not tested                    |
| Grok Build  | Unavailable            | Passed                           | Not tested                    |
| Kilo Code   | Unavailable            | Passed                           | Not tested                    |
| OpenCode    | Unavailable            | Passed                           | Not tested                    |

## Reproduce

```bash
mise run test
mise run check:hosts
```

- **Compiler verification (`tests/test_verification.py`)**: compiles [the reviewer example](../examples/reviewer.md) for all nine bundled targets, checks shared-body preservation and Codex TOML, and verifies idempotence and orphan absence.
- **Host probes (`mise run check:hosts`)**: builds a synthetic reviewer in a temporary project using bundled target defaults (ignoring personal config) and probes `agy agent`, `grok inspect --json`, and `opencode debug agents --standalone`. Antigravity compiles into a separate temporary `HOME`.
- **Safety limits**: probes print only host versions and status, discard raw output, and make zero model calls. Missing tools or unconfigured mise shims report `unavailable`; a failed probe of an active tool exits nonzero.

Antigravity 1.5.14's standalone `agy agent` lists global `mainAgent: true` (default) profiles in isolated global scope while omitting project profiles and `mainAgent: false` roles. [Antigravity's documentation](https://antigravity.google/docs/subagents/#agent-location-and-discovery) specifies both project and global locations; project-session and subagent-only discovery remain unverified by this listing probe.

## Interpret the results

1. **Generated** establishes output syntax, shared instructions, and reproducibility.
1. **Discovered** establishes that a specific installed host recognizes the named profile in the tested scope.
1. **Runtime permissions** require a separately authorized bounded task that exercises allowed and denied actions under the actual parent policy. No runtime permission claim is made here.

The reviewer example includes explicit restrictions for several hosts; other fields use host defaults. Instructions alone do not enforce read-only access, and shell tools, plugins, MCP, and parent policy affect effective access. Consult [native references and permission limits](usage.md#native-behavior-and-verification) before deployment.

Refresh this matrix after changing native fields or upgrading a host, keeping the exact host version, scope, observed result, and verification limit.
