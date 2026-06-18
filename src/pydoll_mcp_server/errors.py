"""Structured error model for all MCP tool responses."""

from __future__ import annotations

from enum import Enum

from pydoll_mcp_server.json_types import JsonObject


class ErrorCode(str, Enum):
    AUTH_REQUIRED = 'AUTH_REQUIRED'
    INVALID_CONFIG = 'INVALID_CONFIG'
    CLIENT_NOT_FOUND = 'CLIENT_NOT_FOUND'
    RESOURCE_NOT_FOUND = 'RESOURCE_NOT_FOUND'
    RESOURCE_LOCKED = 'RESOURCE_LOCKED'
    RESOURCE_UNHEALTHY = 'RESOURCE_UNHEALTHY'
    TIMEOUT = 'TIMEOUT'
    STALE_ELEMENT = 'STALE_ELEMENT'
    AMBIGUOUS_ELEMENT = 'AMBIGUOUS_ELEMENT'
    AMBIGUOUS_PROFILE = 'AMBIGUOUS_PROFILE'
    NAVIGATION_ERROR = 'NAVIGATION_ERROR'
    EXECUTION_ERROR = 'EXECUTION_ERROR'
    BLOCKED_PATTERN = 'BLOCKED_PATTERN'
    PERMISSION_DENIED = 'PERMISSION_DENIED'
    UNSUPPORTED = 'UNSUPPORTED'
    INTERNAL_ERROR = 'INTERNAL_ERROR'
    INVALID_INPUT = 'INVALID_INPUT'


class ResourceState(str, Enum):
    HEALTHY = 'healthy'
    DEGRADED = 'degraded'
    UNHEALTHY = 'unhealthy'
    CLOSED = 'closed'
    UNKNOWN = 'unknown'


class StructuredError(Exception):
    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        details: JsonObject | None = None,
        retryable: bool = False,
        resource_state: ResourceState = ResourceState.UNKNOWN,
        recovery_hint: str = '',
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.retryable = retryable
        self.resource_state = resource_state
        self.recovery_hint = recovery_hint

    def to_dict(self) -> JsonObject:
        result: JsonObject = {
            'error_code': self.error_code.value,
            'message': self.message,
            'retryable': self.retryable,
            'resource_state': self.resource_state.value,
        }
        if self.details:
            result['details'] = self.details
        if self.recovery_hint:
            result['recovery_hint'] = self.recovery_hint
        return result
