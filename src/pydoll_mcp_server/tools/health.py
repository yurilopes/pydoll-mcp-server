"""Health check tools."""

from __future__ import annotations

from typing import Any

from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.server_state import get_server_state

_server_state = get_server_state()


def get_health_response(include_runtime: bool = False) -> dict[str, Any]:
    config = get_config()
    result: dict[str, Any] = {
        'status': 'ok',
        'version': '0.1.0',
        'uptime_seconds': round(_server_state.uptime_seconds, 1),
        'auth_mode': 'token' if config.auth_enabled else 'none',
    }
    if include_runtime:
        result['runtime'] = _server_state.summary()
    return result
