"""Package version resolution."""

from __future__ import annotations


def get_version() -> str:
    try:
        from importlib.metadata import version
        return version('pydoll-mcp-server')
    except Exception:
        return '0.2.0a1'
