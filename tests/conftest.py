"""Shared pytest fixtures."""

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from supagents.cli import main

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CI_OUTPUT_RELATIVE: tuple[Path, ...] = (
    Path(".claude/agents/code_investigator.md"),
    Path(".gemini/agents/code_investigator.md"),
    Path(".github/agents/code_investigator.agent.md"),
)

MakeSource = Callable[[str, str], Path]


@dataclass(frozen=True, slots=True)
class CLIResult:
    """Captured output and exit code from an in-process CLI invocation."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


RunCLI = Callable[..., CLIResult]


@pytest.fixture(autouse=True)
def isolated_home(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Redirect ``$HOME`` to a unique temp dir and disable color forcing in tests."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows fallback used by expanduser
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("PYTHON_COLORS", raising=False)
    return home


@pytest.fixture
def run_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> RunCLI:
    """Invoke ``supagents.cli.main`` in-process, optionally changing ``cwd``."""

    def _invoke(*args: str, cwd: Path | None = None) -> CLIResult:
        if cwd is not None:
            monkeypatch.chdir(cwd)
        exit_code = 0
        try:
            main(list(args))
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        captured = capsys.readouterr()
        return CLIResult(exit_code=exit_code, stdout=captured.out, stderr=captured.err)

    return _invoke


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def project_source_dir(tmp_path: Path) -> Path:
    """An empty ``.agents/supagents/`` directory under ``tmp_path``."""
    src_dir = tmp_path / ".agents" / "supagents"
    src_dir.mkdir(parents=True)
    return src_dir


@pytest.fixture
def make_source(project_source_dir: Path) -> MakeSource:
    """Factory: write ``content`` to ``<project_source_dir>/<name>``; returns the path."""

    def _make(name: str, content: str) -> Path:
        path = project_source_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    return _make


@pytest.fixture
def mixed_workspace(project_source_dir: Path) -> Path:
    """A tmp project workspace populated with every fixture under ``tests/fixtures/``."""
    for fixture in FIXTURES_DIR.glob("*.md"):
        shutil.copy(fixture, project_source_dir / fixture.name)
    return project_source_dir.parents[1]


@pytest.fixture
def ci_workspace(project_source_dir: Path) -> Path:
    """A tmp project workspace containing only the canonical ``code_investigator`` source."""
    shutil.copy(FIXTURES_DIR / "code_investigator.md", project_source_dir / "code_investigator.md")
    return project_source_dir.parents[1]


@pytest.fixture
def ci_outputs(ci_workspace: Path) -> list[Path]:
    """Absolute paths of the three default-target outputs for the ``code_investigator`` source."""
    return [ci_workspace / p for p in CI_OUTPUT_RELATIVE]
