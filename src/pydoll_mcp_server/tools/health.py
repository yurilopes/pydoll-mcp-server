"""Health check tools."""

from __future__ import annotations

from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.server_state import get_server_state
from pydoll_mcp_server.version import get_version

_server_state = get_server_state()


def get_health_response(include_runtime: bool = False) -> JsonObject:
    config = get_config()
    result: JsonObject = {
        'status': 'ok',
        'version': get_version(),
        'uptime_seconds': round(_server_state.uptime_seconds, 1),
        'auth_mode': 'token' if config.auth_enabled else 'none',
    }
    if include_runtime:
        result['runtime'] = _server_state.summary()
    return result
