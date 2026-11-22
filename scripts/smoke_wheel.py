"""Smoke-test the built wheel in a fresh venv with hash-locked runtime dependencies."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed local uv/venv invocations.
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )


def main() -> int:
    """Install the built wheel outside the repo and run CLI smoke checks."""
    uv = shutil.which("uv")
    if uv is None:
        sys.stderr.write("error: uv executable not found on PATH\n")
        return 1
    wheels = sorted((REPO_ROOT / "dist").glob("supagents-*.whl"))
    if len(wheels) != 1:
        sys.stderr.write(f"error: expected 1 wheel in dist/, found {len(wheels)}\n")
        return 1
    wheel = wheels[0].resolve()

    with tempfile.TemporaryDirectory(prefix="supagents-smoke-") as directory:
        tmp = Path(directory)
        requirements = tmp / "requirements.txt"
        venv = tmp / "venv"
        try:
            _run(
                [
                    uv,
                    "export",
                    "--locked",
                    "--no-dev",
                    "--no-emit-project",
                    "-o",
                    str(requirements),
                ],
                cwd=REPO_ROOT,
            )
            _run([uv, "venv", "--python", sys.executable, str(venv)], cwd=tmp)
            bin_dir = venv / ("Scripts" if sys.platform == "win32" else "bin")
            venv_python = bin_dir / ("python.exe" if sys.platform == "win32" else "python")
            supagents_bin = bin_dir / ("supagents.exe" if sys.platform == "win32" else "supagents")

            _run(
                [
                    uv,
                    "pip",
                    "sync",
                    "--python",
                    str(venv_python),
                    "--require-hashes",
                    str(requirements),
                ],
                cwd=tmp,
            )
            _run(
                [uv, "pip", "install", "--python", str(venv_python), "--no-deps", str(wheel)],
                cwd=tmp,
            )

            ver = _run([str(supagents_bin), "--version"], cwd=tmp)
            mod = _run([str(venv_python), "-m", "supagents", "--version"], cwd=tmp)
            _run([str(supagents_bin), "-h"], cwd=tmp)
            _run([str(supagents_bin), "--help"], cwd=tmp)
        except subprocess.CalledProcessError as error:
            sys.stderr.write(f"error: command failed ({error.returncode}): {error.cmd}\n")
            if error.stderr:
                sys.stderr.write(error.stderr)
            if error.stdout:
                sys.stderr.write(error.stdout)
            return 1
        except subprocess.TimeoutExpired as error:
            sys.stderr.write(f"error: command timed out: {error.cmd}\n")
            return 1
        if not ver.stdout.startswith("supagents ") or ver.stdout != mod.stdout:
            sys.stderr.write(f"error: unexpected version output: {ver.stdout!r} / {mod.stdout!r}\n")
            return 1
        sys.stdout.write(ver.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
