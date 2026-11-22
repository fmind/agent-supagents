"""The compatibility probe must isolate outputs and handle inactive mise shims safely."""

import json
import subprocess

from scripts import check_hosts


def test_host_probe_ignores_personal_output_configuration(tmp_path, monkeypatch, capsys):
    config_home = tmp_path / "config"
    config_dir = config_home / "supagents"
    config_dir.mkdir(parents=True)
    installed_profiles = tmp_path / "installed-profiles"
    (config_dir / "config.yaml").write_text(
        f"targets:\n  CLAUDE:\n    project_path: {installed_profiles}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setattr(check_hosts.shutil, "which", lambda _name: None)

    assert check_hosts.probe()
    assert not installed_profiles.exists()
    assert len(capsys.readouterr().out.splitlines()) == len(check_hosts.HOSTS)


def test_host_probe_treats_unconfigured_mise_shim_as_unavailable(monkeypatch, capsys):
    def fake_which(name: str) -> str | None:
        if name == "claude":
            return "/home/user/.local/share/mise/shims/claude"
        return None

    def fake_run(args, **_kwargs):
        raise subprocess.CalledProcessError(
            1, args, output="", stderr="mise ERROR No version is set for shim: claude\n"
        )

    monkeypatch.setattr(check_hosts.shutil, "which", fake_which)
    monkeypatch.setattr(check_hosts.subprocess, "run", fake_run)

    assert check_hosts.probe()
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    claude = next(r for r in records if r["target"] == "CLAUDE")
    assert claude["version"] == "unavailable"
    assert "probe_error" not in claude


def test_host_probe_reports_real_failure_without_leaking_stderr(monkeypatch, capsys):
    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/claude" if name == "claude" else None

    def fake_run(args, **_kwargs):
        raise subprocess.CalledProcessError(1, args, output="SECRET_TOKEN", stderr="PERSONAL_CFG")

    monkeypatch.setattr(check_hosts.shutil, "which", fake_which)
    monkeypatch.setattr(check_hosts.subprocess, "run", fake_run)

    assert not check_hosts.probe()
    out = capsys.readouterr().out
    assert "SECRET_TOKEN" not in out
    assert "PERSONAL_CFG" not in out
    assert '"probe_error": "CalledProcessError"' in out
