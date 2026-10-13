"""The compatibility probe must keep generated profiles inside its temporary directory."""

from scripts import check_hosts


def test_host_probe_ignores_personal_output_configuration(tmp_path, monkeypatch, capsys):
    config_home = tmp_path / "config"
    config_dir = config_home / "supagents"
    config_dir.mkdir(parents=True)
    installed_profiles = tmp_path / "installed-profiles"
    (config_dir / "config.yaml").write_text(
        f"targets:\n  CLAUDE:\n    project_path: {installed_profiles}\n"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setattr(check_hosts.shutil, "which", lambda _name: None)

    assert check_hosts.probe()
    assert not installed_profiles.exists()
    assert len(capsys.readouterr().out.splitlines()) == len(check_hosts.HOSTS)
