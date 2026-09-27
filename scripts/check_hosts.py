"""Probe installed hosts with a synthetic project; never execute an agent task."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from supagents import core
from supagents.config import DEFAULT_TARGETS, Config

HOSTS = {
    "AGY": ("agy", ["agents"]),
    "CLAUDE": ("claude", None),
    "CODEX": ("codex", None),
    "COPILOT": ("copilot", None),
    "CURSOR": ("cursor-agent", None),
    "GEMINI": ("gemini", None),
    "GROK": ("grok", ["inspect", "--json"]),
    "KILO": ("kilo", None),
    "OPENCODE": ("opencode", ["debug", "agent", "supagents-compatibility-reviewer", "--pure"]),
}


def probe() -> bool:
    """Report versions and discovery; return false on a failed installed-host probe."""
    example = Path(__file__).resolve().parents[1] / "examples/reviewer.md"
    with tempfile.TemporaryDirectory(prefix="supagents-hosts-") as directory:
        project = Path(directory)
        root = project / ".agents/supagents"
        root.mkdir(parents=True)
        name = "supagents-compatibility-reviewer"
        (root / f"{name}.md").write_text(
            example.read_text().replace("name: reviewer\n", f"name: {name}\n"),
            encoding="utf-8",
        )
        built = core.build("project", cwd=project, strict=True)
        if built.fatal_errors or built.error_count or built.warning_count:
            raise RuntimeError("synthetic compatibility source did not compile cleanly")
        # AGY 1.2.12's standalone listing observes global profiles. Compile that
        # scope into a disposable home; never touch the user's installed agents.
        probe_home = project / "home"
        agy_config = Config(
            targets={
                **DEFAULT_TARGETS,
                "AGY": DEFAULT_TARGETS["AGY"].model_copy(
                    update={
                        "global_path": probe_home / ".gemini/config/agents",
                    }
                ),
            }
        )
        global_build = core.build(
            "global",
            config=agy_config,
            cwd=project,
            source_dir=root,
            targets={"AGY"},
            strict=True,
        )
        if global_build.fatal_errors or global_build.error_count or global_build.warning_count:
            raise RuntimeError("synthetic global AGY profile did not compile cleanly")
        passed = True
        for target, (executable, discovery) in HOSTS.items():
            record: dict[str, str | bool] = {
                "target": target,
                "compiled": True,
                "version": "unavailable",
                "discovery": "not tested",
                "runtime_permissions": "not tested",
                "scope": "global" if target == "AGY" else "project",
            }
            if command := shutil.which(executable):
                try:
                    version = subprocess.run(  # noqa: S603 - fixed commands resolved from the local tool PATH.
                        [command, "--version"],
                        cwd=project,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=30,
                    )
                    record["version"] = version.stdout.strip().splitlines()[0]
                    if discovery is not None:
                        probe_env = (
                            {**os.environ, "HOME": str(probe_home)} if target == "AGY" else None
                        )
                        result = subprocess.run(  # noqa: S603 - fixed commands resolved from the local tool PATH.
                            [command, *discovery],
                            cwd=project,
                            capture_output=True,
                            text=True,
                            check=True,
                            timeout=30,
                            env=probe_env,
                        )
                        found = name in result.stdout
                        record["discovery"] = "passed" if found else "failed"
                        passed = passed and found
                except (OSError, subprocess.SubprocessError, IndexError) as error:
                    # Host dumps may include personal configuration. Report only
                    # the error class, never captured stdout/stderr or exception text.
                    record["probe_error"] = type(error).__name__
                    passed = False
            print(json.dumps(record))  # noqa: T201
        return passed


if __name__ == "__main__":
    raise SystemExit(0 if probe() else 1)
