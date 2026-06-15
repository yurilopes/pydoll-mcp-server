"""End-to-end browser workflow through a real MCP stdio session."""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_string, require_json_object
from pydoll_mcp_server.version import get_version
from tests.integration.test_browser_smoke import build_fixture_url

pytestmark = [pytest.mark.mcp_e2e, pytest.mark.browser, pytest.mark.slow]

CLIENT_ID = 'mcp-e2e-client'
UTF8_TEXT = 'Olá mundo, 日本語, 한국어, 中文'
CALL_TIMEOUT = timedelta(seconds=45)


async def call_tool(session: ClientSession, name: str, arguments: JsonObject) -> JsonObject:
    result = await session.call_tool(name, arguments, read_timeout_seconds=CALL_TIMEOUT)
    assert result.isError is not True, f'{name} returned an MCP error: {result.content}'
    assert len(result.content) == 1, f'{name} returned unexpected content: {result.content}'
    content = result.content[0]
    assert isinstance(content, TextContent), f'{name} did not return text JSON: {content}'
    decoded: object = json.loads(content.text)
    response = require_json_object(decoded, f'{name} response')
    assert 'error_code' not in response, f'{name} returned a structured error: {response}'
    return response


def find_tree_element(nodes: JsonArray, html_id: str) -> JsonObject:
    for node_value in nodes:
        node = require_json_object(node_value, 'page tree node')
        attrs = require_json_object(node.get('attrs'), 'page tree node attrs')
        if attrs.get('id') == html_id:
            return node
    raise AssertionError(f'Element with id={html_id!r} was not returned by page_get_tree')


@pytest.mark.asyncio
async def test_real_stdio_agent_browser_workflow(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    environment = dict(os.environ)
    environment.update(
        {
            'PYTHONIOENCODING': 'utf-8',
            'PYDOLL_MCP_TRANSPORT': 'stdio',
            'PYDOLL_MCP_ALLOW_NO_AUTH': 'true',
            'PYDOLL_MCP_RUNTIME_DIR': str(tmp_path / 'runtime'),
            'PYTHONPATH': str(root / 'src'),
        }
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'pydoll_mcp_server.cli', '--transport', 'stdio'],
        env=environment,
        cwd=root,
        encoding='utf-8',
        encoding_error_handler='strict',
    )

    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        catalog = await session.list_tools()
        tool_names = {tool.name for tool in catalog.tools}
        assert {
            'health_check',
            'server_status',
            'browser_launch',
            'page_get_tree',
            'page_get_tree_deep',
            'element_click',
            'element_fill',
            'network_enable',
            'network_list',
            'network_disable',
            'browser_close',
        } <= tool_names
        assert all(tool.outputSchema is None for tool in catalog.tools)

        health = await call_tool(session, 'health_check', {'include_runtime': False})
        status = await call_tool(session, 'server_status', {'client_id': CLIENT_ID})
        assert health['version'] == get_version()
        assert status['version'] == get_version()

        launched = await call_tool(
            session,
            'browser_launch',
            {'client_id': CLIENT_ID, 'headless': True, 'profile_mode': 'temporary'},
        )
        browser_id = get_string(launched, 'browser_id')
        tab_id = get_string(launched, 'tab_id')
        assert browser_id and tab_id

        try:
            await call_tool(
                session,
                'page_goto',
                {'client_id': CLIENT_ID, 'tab_id': tab_id, 'url': build_fixture_url('simple.html')},
            )
            tree = await call_tool(session, 'page_get_tree', {'client_id': CLIENT_ID, 'tab_id': tab_id})
            button = find_tree_element(get_array(tree, 'nodes'), 'btn-click')
            button_id = get_string(button, 'elementId')
            assert button_id
            await call_tool(
                session,
                'element_click',
                {'client_id': CLIENT_ID, 'tab_id': tab_id, 'element_id': button_id},
            )
            click_state = await call_tool(
                session,
                'js_evaluate_readonly',
                {
                    'client_id': CLIENT_ID,
                    'tab_id': tab_id,
                    'script': "return document.getElementById('result').textContent;",
                },
            )
            assert json.loads(get_string(click_state, 'value')) == 'clicked'

            await call_tool(
                session,
                'page_goto',
                {'client_id': CLIENT_ID, 'tab_id': tab_id, 'url': build_fixture_url('form.html')},
            )
            form_tree = await call_tool(session, 'page_get_tree', {'client_id': CLIENT_ID, 'tab_id': tab_id})
            input_node = find_tree_element(get_array(form_tree, 'nodes'), 'input-text')
            input_id = get_string(input_node, 'elementId')
            assert input_id
            await call_tool(
                session,
                'element_fill',
                {'client_id': CLIENT_ID, 'tab_id': tab_id, 'element_id': input_id, 'value': UTF8_TEXT},
            )
            input_state = await call_tool(
                session,
                'js_evaluate_readonly',
                {
                    'client_id': CLIENT_ID,
                    'tab_id': tab_id,
                    'script': "return document.getElementById('input-text').value;",
                },
            )
            assert json.loads(get_string(input_state, 'value')) == UTF8_TEXT

            for fixture, expected_path_key in (
                ('iframe-parent.html', 'frame_path'),
                ('nested-iframe.html', 'frame_path'),
                ('shadow-dom.html', 'shadow_path'),
            ):
                await call_tool(
                    session,
                    'page_goto',
                    {'client_id': CLIENT_ID, 'tab_id': tab_id, 'url': build_fixture_url(fixture)},
                )
                deep = await call_tool(
                    session,
                    'page_get_tree_deep',
                    {'client_id': CLIENT_ID, 'tab_id': tab_id, 'timeout': 20},
                )
                assert any(
                    get_array(require_json_object(node, 'deep node'), expected_path_key)
                    for node in get_array(deep, 'elements')
                ), deep

            await call_tool(session, 'network_enable', {'client_id': CLIENT_ID, 'tab_id': tab_id})
            await call_tool(
                session,
                'page_goto',
                {
                    'client_id': CLIENT_ID,
                    'tab_id': tab_id,
                    'url': build_fixture_url('simple.html?token=secret-value'),
                },
            )
            network = await call_tool(session, 'network_list', {'client_id': CLIENT_ID, 'tab_id': tab_id})
            serialized_network = json.dumps(network, ensure_ascii=False)
            assert 'secret-value' not in serialized_network
            assert 'REDACTED' in serialized_network
            await call_tool(session, 'network_disable', {'client_id': CLIENT_ID, 'tab_id': tab_id})

            diagnostics = await call_tool(session, 'diagnostics_snapshot', {'client_id': CLIENT_ID})
            assert diagnostics['success'] is True
        finally:
            closed = await call_tool(
                session,
                'browser_close',
                {'client_id': CLIENT_ID, 'browser_id': browser_id},
            )
            assert closed['success'] is True
