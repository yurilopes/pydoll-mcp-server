"""Shared server state and response metadata."""

from __future__ import annotations

import time
import uuid

from pydoll_mcp_server.errors import StructuredError
from pydoll_mcp_server.json_types import JsonObject

SCHEMA_VERSION = '2026-06-16.v0.4'
_START_TIME = time.time()


class ServerState:
    def __init__(self) -> None:
        self._tool_counts: dict[str, int] = {}
        self._failure_counts: dict[str, int] = {}
        self._timeouts = 0
        self._tab_unhealthy = 0
        self._recoveries = 0

    def record_tool(self, tool_name: str) -> None:
        self._tool_counts[tool_name] = self._tool_counts.get(tool_name, 0) + 1

    def record_failure(self, error_code: str) -> None:
        self._failure_counts[error_code] = self._failure_counts.get(error_code, 0) + 1

    def record_timeout(self) -> None:
        self._timeouts += 1

    def record_unhealthy_tab(self) -> None:
        self._tab_unhealthy += 1

    def record_recovery(self) -> None:
        self._recoveries += 1

    @property
    def uptime_seconds(self) -> float:
        return time.time() - _START_TIME

    def summary(self) -> JsonObject:
        return {
            'uptime_seconds': round(self.uptime_seconds, 1),
            'tool_calls': dict(self._tool_counts),
            'failures': dict(self._failure_counts),
            'timeouts': self._timeouts,
            'unhealthy_tabs': self._tab_unhealthy,
            'recoveries': self._recoveries,
        }


_SERVER_STATE = ServerState()


def get_server_state() -> ServerState:
    return _SERVER_STATE


def generate_request_id() -> str:
    return uuid.uuid4().hex[:12]


def error_response(error: StructuredError) -> JsonObject:
    _SERVER_STATE.record_failure(error.error_code.value)
    return {'success': False, **error.to_dict()}
