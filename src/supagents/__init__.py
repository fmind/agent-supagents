"""Compile a single AI supagent into multiple AI subagents."""

from importlib.metadata import version

__version__ = version("supagents")
__all__ = ["__version__"]
