"""Runtime state for the selected MCP tool exposure profile."""

from __future__ import annotations

from pydoll_mcp_server.tool_metadata import ToolProfile

_active_tool_profile = ToolProfile.JOBS
_active_tool_count = 0


def set_active_tool_profile(profile: ToolProfile, count: int) -> None:
    """Record the profile and count used by the current server instance."""

    global _active_tool_count, _active_tool_profile
    _active_tool_profile = profile
    _active_tool_count = count


def get_active_tool_profile() -> ToolProfile:
    """Return the profile used by the current server instance."""

    return _active_tool_profile


def get_active_tool_count() -> int:
    """Return the number of tools registered by the current server instance."""

    return _active_tool_count


__all__ = [
    'get_active_tool_count',
    'get_active_tool_profile',
    'set_active_tool_profile',
]
