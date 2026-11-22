"""Maintain shared subagent instructions and generate native coding-tool configurations."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    __version__: str

__all__ = ["__version__"]


def __getattr__(name: str) -> str:
    if name == "__version__":
        from importlib.metadata import version

        val = version("supagents")
        globals()["__version__"] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
