"""Contract tests for MCP tool list and basic operations."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest
from starlette.routing import BaseRoute, Mount, Route
from starlette.testclient import TestClient

from pydoll_mcp_server.json_types import JsonObject, require_json_object

pytestmark = [pytest.mark.integration, pytest.mark.contract]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _reset_config_cache() -> None:
    from pydoll_mcp_server.config import get_config

    get_config.cache_clear()


def _route_has_path(route: BaseRoute, path: str) -> bool:
    return isinstance(route, Route | Mount) and route.path == path


class TestAppTransport:
    def test_create_app_with_token(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import create_app

            app = create_app()
            assert app is not None

    def test_health_no_auth_required(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import create_app

            app = create_app()
            client = TestClient(app)
            response = client.get('/health')
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'ok'
            assert 'version' in data

    def test_health_does_not_leak_token(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import create_app

            app = create_app()
            client = TestClient(app)
            response = client.get('/health')
            data = response.json()
            assert 'token' not in str(data).lower()

    def test_mcp_requires_auth(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import create_app

            app = create_app()
            client = TestClient(app)
            response = client.post('/mcp', json={})
            assert response.status_code == 401

    def test_mcp_accepts_valid_token(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import create_app

            app = create_app()
            assert any(_route_has_path(route, '/mcp') for route in app.routes), '/mcp mount not found in app routes'

    def test_sse_mount_exists(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import create_app

            app = create_app()
            assert any(_route_has_path(route, '/sse') for route in app.routes), '/sse mount not found in app routes'

    def test_mcp_rejects_invalid_token(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import create_app

            app = create_app()
            client = TestClient(app)
            response = client.post(
                '/mcp/',
                json={},
                headers={'Authorization': 'Bearer wrong-token'},
            )
            assert response.status_code == 401

    def test_sse_endpoint_exists(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import create_app

            app = create_app()
            assert any(_route_has_path(route, '/sse') for route in app.routes), '/sse mount not found in app routes'

    def test_mcp_route_mounted(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.server import create_app

            app = create_app()
            assert any(_route_has_path(route, '/mcp') for route in app.routes), '/mcp mount not found in app routes'

    def test_no_http_app_reference(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            import inspect

            from pydoll_mcp_server.server import create_app

            source = inspect.getsource(create_app)
            assert 'mcp.http_app()' not in source
            assert 'streamable_http_app' in source

    def test_loopback_http_server_health_and_mcp_auth(self) -> None:
        import uvicorn

        token = 'loopback-token'
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': token}):
            _reset_config_cache()
            from pydoll_mcp_server.server import create_app

            port = _free_port()
            app = create_app()
            config = uvicorn.Config(
                app,
                host='127.0.0.1',
                port=port,
                log_level='critical',
                access_log=False,
            )
            server = uvicorn.Server(config)

            thread = threading.Thread(
                target=lambda: asyncio.run(server.serve()),
                daemon=True,
            )
            thread.start()
            base = f'http://127.0.0.1:{port}'

            try:
                deadline = time.time() + 10
                health_data: JsonObject | None = None
                while time.time() < deadline:
                    try:
                        with urllib.request.urlopen(f'{base}/health', timeout=1) as response:
                            health_data = require_json_object(
                                json.loads(response.read().decode('utf-8')),
                                'health response',
                            )
                            break
                    except Exception:
                        time.sleep(0.05)

                assert health_data is not None
                assert health_data['status'] == 'ok'

                no_auth_request = urllib.request.Request(
                    f'{base}/mcp/',
                    data=b'{}',
                    headers={'Content-Type': 'application/json'},
                    method='POST',
                )
                with pytest.raises(urllib.error.HTTPError) as no_auth_error:
                    urllib.request.urlopen(no_auth_request, timeout=3)
                assert no_auth_error.value.code == 401

                auth_request = urllib.request.Request(
                    f'{base}/mcp/',
                    data=b'{}',
                    headers={
                        'Authorization': f'Bearer {token}',
                        'Content-Type': 'application/json',
                    },
                    method='POST',
                )
                try:
                    urllib.request.urlopen(auth_request, timeout=3)
                except urllib.error.HTTPError as exc:
                    assert exc.code != 401
            finally:
                server.should_exit = True
                thread.join(timeout=10)


class TestMCPTools:
    def test_health_check_tool(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test'}):
            from pydoll_mcp_server.tools.health import get_health_response

            result = get_health_response(include_runtime=False)
            assert result['status'] == 'ok'
            assert 'version' in result

    def test_server_status(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test'}):
            from pydoll_mcp_server.server import server_status

            result = server_status(client_id='test-client')
            assert result['status'] == 'ok'

    def test_error_model(self) -> None:
        from pydoll_mcp_server.errors import ErrorCode, StructuredError

        error = StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message='Test error',
            retryable=True,
        )
        d = error.to_dict()
        assert d['error_code'] == 'TIMEOUT'
        assert d['retryable'] is True

    def test_no_prohibited_tools(self) -> None:
        from pydoll_mcp_server.security.policy import PROHIBITED_METHODS
        from pydoll_mcp_server.tool_catalog import TOOLS

        tool_names = {tool.__name__ for tool in TOOLS}
        for prohibited in PROHIBITED_METHODS:
            assert prohibited not in tool_names

    @pytest.mark.asyncio
    async def test_mcp_tool_catalog_contains_expected_alpha_tools(self) -> None:
        from pydoll_mcp_server.server import mcp

        tools = await mcp.list_tools()
        tool_names = {tool.name for tool in tools}
        expected_p0 = {
            'health_check',
            'server_status',
            'browser_launch',
            'browser_list',
            'browser_close',
            'http_request',
            'network_replay_request',
            'tab_list',
            'tab_activate',
            'tab_close',
            'tab_recover',
            'page_goto',
            'page_reload',
            'page_wait',
            'page_screenshot',
            'page_get_text',
            'page_get_tree',
            'element_find',
            'element_click',
            'element_click_by_text',
            'element_click_center',
            'element_type',
            'element_fill',
            'element_fill_and_verify',
            'element_get_text',
            'element_get_attribute',
            'js_evaluate_readonly',
            'js_evaluate',
            'user_agent_set',
            'user_agent_get',
            'viewport_set',
            'viewport_get',
            'page_get_interactive_summary',
            'page_wait_for_text',
            'page_wait_text_gone',
            'page_wait_for_selector',
            'page_wait_for_network_idle',
            'element_wait_value',
            'form_snapshot',
            'form_errors',
            'combobox_get_options',
            'select_get_options',
            'combobox_type_and_select',
            'combobox_select_option',
            'file_upload_state',
            'artifact_get_paths',
            'artifact_import',
            'mouse_click',
            'page_get_active_surface',
            'element_find_by_text_candidates',
            'element_resolve_again',
            'form_fill_fields',
            'form_select_choice',
            'page_click_primary_action',
            'artifact_prepare_upload',
            'submission_wait_for_confirmation',
            'profile_list',
            'profile_promote',
        }
        assert expected_p0.issubset(tool_names)

    @pytest.mark.asyncio
    async def test_tool_catalog_does_not_generate_recursive_output_schemas(self) -> None:
        from pydoll_mcp_server.server import mcp

        tools = await mcp.list_tools()

        assert tools
        assert all(tool.outputSchema is None for tool in tools)
