"""Tests for error model and structured errors."""

from __future__ import annotations

from pydoll_mcp_server.errors import ErrorCode, ResourceState, StructuredError
from tests.typing_helpers import object_at


class TestStructuredError:
    def test_to_dict_minimal(self) -> None:
        error = StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message='Operation timed out',
        )
        d = error.to_dict()
        assert d['error_code'] == 'TIMEOUT'
        assert d['message'] == 'Operation timed out'
        assert d['retryable'] is False
        assert d['resource_state'] == 'unknown'

    def test_to_dict_full(self) -> None:
        error = StructuredError(
            error_code=ErrorCode.AUTH_REQUIRED,
            message='Auth required',
            details={'hint': 'Provide token'},
            retryable=True,
            resource_state=ResourceState.CLOSED,
            recovery_hint='Set PYDOLL_MCP_AUTH_TOKEN',
        )
        d = error.to_dict()
        assert d['error_code'] == 'AUTH_REQUIRED'
        assert d['retryable'] is True
        assert object_at(d, 'details')['hint'] == 'Provide token'
        assert d['recovery_hint'] == 'Set PYDOLL_MCP_AUTH_TOKEN'
        assert d['resource_state'] == 'closed'

    def test_all_error_codes(self) -> None:
        for code in ErrorCode:
            error = StructuredError(error_code=code, message='test')
            d = error.to_dict()
            assert d['error_code'] == code.value

    def test_all_resource_states(self) -> None:
        for state in ResourceState:
            error = StructuredError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message='test',
                resource_state=state,
            )
            d = error.to_dict()
            assert d['resource_state'] == state.value
