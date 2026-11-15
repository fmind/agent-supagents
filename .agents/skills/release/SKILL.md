---
name: release
description: "Prepare, tag, publish, and verify a supagents release to PyPI, GitHub Releases, and GitHub Pages when authorized."
license: MIT
metadata:
  kind: task
  author: Médéric HURIER (Fmind)
  source: github.com/fmind/agent-supagents/tree/main/.agents/skills/release
  created: "2026-11-15"
  updated: "2026-11-15"
---

# Release

One owner instruction to release authorizes the end-to-end flow: bump manifests, qualify locally, push `main`, wait for CI and Docs, push `vX.Y.Z`, watch automated CD, and verify PyPI, GitHub Release, and Pages. Published versions and tags are immutable.

## Workflow

1. Inspect state: verify clean `git status`, `main` synced with `origin/main`, existing tags (`git ls-remote --tags origin`), and live PyPI (`curl -fsS https://pypi.org/pypi/supagents/json | jq -r .info.version`).
1. Compute SemVer: `feat` -> minor, `fix` -> patch, breaking CLI/config/target removal or `requires-python` bump -> major.
1. Bump versions in lockstep:
   - Run `uv version X.Y.Z` to update `pyproject.toml` and `uv.lock`.
   - Set `"version": "X.Y.Z"` in `.claude-plugin/plugin.json`, `gemini-extension.json`, and `plugin.json`.
1. Hand-curate `CHANGELOG.md` (`## [X.Y.Z] - YYYY-MM-DD` UTC date); never overwrite prior entries with `git-cliff -o`.
1. Qualify locally before committing:
   ```bash
   uv run --locked python scripts/verify_release.py "vX.Y.Z"
   mise run all
   mise run check:hosts
   mise run clean
   ```
1. Commit `chore(release): vX.Y.Z` and push `main`. Let Lefthook run; never pass `--no-verify` or AI co-author trailers.
1. Wait for exact-HEAD CI and Docs workflows to succeed before tagging:
   ```bash
   sha=$(git rev-parse HEAD)
   gh run list --commit "$sha" --json databaseId,workflowName,status,conclusion
   ```
1. Tag and push `vX.Y.Z` (use `-m` without `-a` so git tag signing stays enabled), then watch CD (`cd.yml`):
   ```bash
   git tag "vX.Y.Z" -m "vX.Y.Z" "$sha"
   git push origin "refs/tags/vX.Y.Z"
   ```
1. Verify all published targets:
   - Peeled remote tag `refs/tags/vX.Y.Z^{}` equals `$sha`.
   - PyPI `https://pypi.org/pypi/supagents/X.Y.Z/json` and PEP 740 provenance `https://pypi.org/integrity/supagents/X.Y.Z/supagents-X.Y.Z-py3-none-any.whl/provenance`.
   - Immutable GitHub Release (`gh release view vX.Y.Z --json tagName,isDraft,isImmutable,assets,url`) and `gh attestation verify` against `--signer-workflow fmind/agent-supagents/.github/workflows/cd.yml`.
   - Live docs site `https://fmind.github.io/agent-supagents/` and `uvx --refresh supagents@X.Y.Z --version`.

## Gotchas

- **Recover CD without moving tags**: if CD hits a transient upstream failure, rerun failed jobs via `gh run rerun <id> --failed`; never move or force-push a tag.
