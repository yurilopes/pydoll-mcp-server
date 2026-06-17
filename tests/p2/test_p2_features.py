"""P2 dedicated tests: stdio, network, trace, console, attach, capabilities."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

from pydoll_mcp_server.json_types import JsonObject
from tests.typing_helpers import array_at, int_at, object_at, string_at, value_as_object

pytestmark = [pytest.mark.unit]


class TestStdioTransport:
    def test_stdio_does_not_require_auth_token(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            from pydoll_mcp_server.cli import run_stdio

            assert callable(run_stdio)

    def test_http_still_requires_auth_by_default(self) -> None:
        from pydoll_mcp_server.config import ServerConfig

        config = ServerConfig(auth_token='test-token')
        assert config.auth_enabled is True

    def test_cli_stdio_dispatches_without_config(self) -> None:
        from unittest.mock import MagicMock

        with (
            patch.dict(os.environ, {}, clear=True),
            patch('pydoll_mcp_server.cli.run_stdio', MagicMock()) as mock_stdio,
            patch(
                'pydoll_mcp_server.cli.uvicorn.run',
                side_effect=RuntimeError('http should not be called'),
            ),
        ):
            import sys

            orig_argv = sys.argv
            try:
                sys.argv = ['prog', '--transport', 'stdio']
                from pydoll_mcp_server.cli import main

                main()
                mock_stdio.assert_called_once()
            finally:
                sys.argv = orig_argv


class TestCapabilities:
    def test_schema_version_in_server_status(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import server_status

            result = server_status(client_id='test-p2')
            assert 'schema_version' in result
            assert string_at(result, 'schema_version') == '2026-06-17.v0.5'

    def test_capabilities_includes_transports(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import server_status

            result = server_status(client_id='test-p2')
            caps = object_at(result, 'capabilities')
            transports = array_at(caps, 'transports')
            assert 'transports' in caps
            assert 'stdio' in transports
            assert 'http' in transports

    def test_capabilities_includes_inspection(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import server_status

            result = server_status(client_id='test-p2')
            caps = object_at(result, 'capabilities')
            inspection = array_at(caps, 'inspection')
            assert 'inspection' in caps
            assert 'network' in inspection

    def test_capabilities_includes_diagnostics(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import server_status

            result = server_status(client_id='test-p2')
            caps = object_at(result, 'capabilities')
            assert 'diagnostics' in caps

    def test_version_is_beta(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import server_status

            result = server_status(client_id='test-p2')
            assert 'version' in result
            assert string_at(result, 'version') == '0.4.0b1'


class TestConsoleUnsupported:
    def test_console_enable_returns_unsupported(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.tools.inspection import console_enable

            async def _run() -> JsonObject:
                return await console_enable('test', 'tab-test')

            result = asyncio.run(_run())
            assert result.get('error_code') == 'RESOURCE_NOT_FOUND'

    def test_console_disable_returns_unsupported(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.tools.inspection import console_disable

            async def _run() -> JsonObject:
                return await console_disable('test', 'tab-test')

            result = asyncio.run(_run())
            assert result.get('error_code') == 'RESOURCE_NOT_FOUND'

    def test_console_list_returns_unsupported(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.tools.inspection import console_list

            async def _run() -> JsonObject:
                return await console_list('test', 'tab-test')

            result = asyncio.run(_run())
            assert result.get('error_code') == 'RESOURCE_NOT_FOUND'


class TestBrowserAttach:
    def test_attach_nonexistent_browser(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import browser_attach

            async def _run() -> JsonObject:
                return await browser_attach('test', 'br_nonexistent')

            result = asyncio.run(_run())
            assert result.get('success') is not True

    def test_attach_no_endpoint_accepted(self) -> None:
        import inspect

        from pydoll_mcp_server.server import browser_attach

        params = list(inspect.signature(browser_attach).parameters.keys())
        assert 'endpoint' not in params
        assert 'port' not in params
        assert 'pid' not in params
        assert 'ws_endpoint' not in params
        assert 'ws_address' not in params


class TestDiagnosticsSnapshot:
    def test_snapshot_no_secrets(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import diagnostics_snapshot

            async def _run() -> JsonObject:
                return await diagnostics_snapshot('test-p2')

            result = asyncio.run(_run())
            assert result['success'] is True
            assert 'test-token' not in str(result)
            assert 'PYDOLL_MCP_AUTH_TOKEN' not in str(result)

    def test_snapshot_has_schema_version(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import diagnostics_snapshot

            async def _run() -> JsonObject:
                return await diagnostics_snapshot('test-p2')

            result = asyncio.run(_run())
        assert result.get('schema_version') == '2026-06-17.v0.5'


class TestTraceIntegration:
    def test_trace_records_diagnostics_snapshot(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import diagnostics_snapshot, trace_get, trace_start

            async def _run() -> JsonObject:
                start = await trace_start('trace-int-client', 'test')
                trace_id = string_at(start, 'trace_id')
                await diagnostics_snapshot('trace-int-client')
                return await trace_get('trace-int-client', trace_id)

            result = asyncio.run(_run())
            assert result['success'] is True
            tools = [string_at(value_as_object(event), 'tool') for event in array_at(result, 'events')]
            assert 'trace_start' in tools
            assert 'diagnostics_snapshot' in tools
            assert int_at(result, 'count') >= 2

    def test_trace_records_network_enable_via_trace_event(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import trace_get, trace_start
            from pydoll_mcp_server.tools.inspection import trace_inspection_event

            async def _run() -> JsonObject:
                start = await trace_start('trace-net-client', 'test')
                trace_id = string_at(start, 'trace_id')
                trace_inspection_event('trace-net-client', 'network_enable', 'success', 'tab-1')
                return await trace_get('trace-net-client', trace_id)

            result = asyncio.run(_run())
            tools = [string_at(value_as_object(event), 'tool') for event in array_at(result, 'events')]
            assert 'network_enable' in tools

    def test_trace_error_event(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import trace_get, trace_start
            from pydoll_mcp_server.tools.inspection import trace_inspection_event

            async def _run() -> JsonObject:
                start = await trace_start('trace-err-client', 'test')
                trace_id = string_at(start, 'trace_id')
                trace_inspection_event('trace-err-client', 'network_list', 'error', 'tab-1', 'TIMEOUT', 'test timeout')
                return await trace_get('trace-err-client', trace_id)

            result = asyncio.run(_run())
            error_events = [
                value_as_object(event)
                for event in array_at(result, 'events')
                if value_as_object(event).get('error_code')
            ]
            assert len(error_events) >= 1
            assert error_events[0]['error_code'] == 'TIMEOUT'
