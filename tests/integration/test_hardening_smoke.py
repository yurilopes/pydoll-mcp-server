"""Browser validation for stable references, reactive forms, security signals, and shadow DOM."""

from __future__ import annotations

import pytest

from pydoll_mcp_server.dom.deep_traversal import page_get_tree_deep
from pydoll_mcp_server.dom.tree import build_page_tree
from pydoll_mcp_server.json_types import (
    InvalidJsonValueError,
    JsonObject,
    get_array,
    get_object,
    get_string,
    require_json_object,
)
from pydoll_mcp_server.tools.browser import browser_close, browser_launch
from pydoll_mcp_server.tools.elements import element_click, element_fill, element_find
from pydoll_mcp_server.tools.page import page_goto
from pydoll_mcp_server.tools.page_advanced import page_snapshot
from tests.integration.test_plan14_smoke import build_fixture_url

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]


@pytest.mark.asyncio
async def test_generic_application_hardening() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
        client_id = 'hardening-smoke'
        launched = await browser_launch(client_id, headless=True, profile_mode='temporary')
        assert launched.get('success') is True, launched
        tab_id = str(launched.get('tab_id', ''))
        try:
            navigated = await page_goto(client_id, tab_id, build_fixture_url('hardening.html'))
            assert navigated.get('success') is True, navigated

            tree = await build_page_tree(client_id, tab_id, max_nodes=300)
            headers: list[JsonObject] = []
            for node_value in get_array(tree, 'nodes', []):
                try:
                    node = require_json_object(node_value, 'tree node')
                except InvalidJsonValueError:
                    continue
                attrs = get_object(node, 'attrs', {})
                if get_string(node, 'tag') == 'button' and get_string(attrs, 'data-testid') == 'accordion-header':
                    headers.append(node)
            assert len(headers) == 4, tree
            fourth_id = get_string(headers[3], 'elementId')
            clicked = await element_click(client_id, tab_id, fourth_id)
            assert clicked.get('success') is True, clicked

            reactive_input = await element_find(client_id, tab_id, '#react-name')
            dependent = await element_find(client_id, tab_id, '#dependent-submit')
            assert reactive_input.get('success') is True
            assert dependent.get('success') is True
            input_id = str(reactive_input.get('element_id', ''))
            dependent_id = str(dependent.get('element_id', ''))
            first_fill = await element_fill(
                client_id,
                tab_id,
                input_id,
                'Brasília',
                expected_enabled_element_id=dependent_id,
            )
            assert first_fill.get('success') is True, first_fill
            second_fill = await element_fill(client_id, tab_id, input_id, 'João\u00a0D\u2019Ávila')
            assert second_fill.get('success') is True, second_fill
            submitted = await element_click(
                client_id,
                tab_id,
                dependent_id,
                expect_text='Continued',
            )
            assert submitted.get('success') is True, submitted

            deep = await page_get_tree_deep(client_id, tab_id, max_nodes=300)
            shadow_nodes: list[JsonObject] = []
            for node_value in get_array(deep, 'elements', []):
                try:
                    node = require_json_object(node_value, 'deep node')
                except InvalidJsonValueError:
                    continue
                attrs = get_object(node, 'attrs', {})
                if get_string(attrs, 'id') == 'street-input':
                    shadow_nodes.append(node)
            assert shadow_nodes, deep
            shadow_id = get_string(shadow_nodes[0], 'element_id')
            shadow_fill = await element_fill(client_id, tab_id, shadow_id, 'Rua das Flores')
            assert shadow_fill.get('success') is True, shadow_fill

            snapshot = await page_snapshot(client_id, tab_id, max_nodes=300)
            controls = get_array(snapshot, 'security_controls', [])
            assert any(isinstance(item, dict) and item.get('kind') == 'captcha' for item in controls), snapshot
            otp = await element_find(client_id, tab_id, '#otp-control')
            otp_result = await element_fill(client_id, tab_id, str(otp.get('element_id', '')), '123456')
            assert otp_result.get('error_code') == 'SECURITY_CONTROL_PRESENT', otp_result
        finally:
            closed = await browser_close(client_id, browser_id='')
            assert closed.get('success') is True or 'not found' in str(closed.get('message', '')).lower()
