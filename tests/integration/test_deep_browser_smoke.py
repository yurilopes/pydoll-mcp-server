"""Real-browser smoke coverage for iframe and shadow DOM traversal."""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch

import pytest

from pydoll_mcp_server.json_types import require_json_object
from tests.integration.test_browser_smoke import launch_and_goto_fixture, register_smoke_tab, stop_smoke_browser
from tests.typing_helpers import array_at

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]


@pytest.mark.asyncio
async def test_deep_tree_simple_iframe_and_find_deep() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await launch_and_goto_fixture('iframe-parent.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.dom.deep_traversal import element_find_deep, page_get_tree_deep

            tab_info = await register_smoke_tab(browser, tab, 'smoke-deep-iframe')
            result = await page_get_tree_deep('smoke-deep-iframe', tab_info.tab_id, timeout=10)
            assert result['success'] is True, result
            assert result['partial'] is False, result
            assert any(array_at(result, 'frames')), result
            elements = array_at(result, 'elements')
            assert any(
                require_json_object(node, 'deep tree node').get('text') == 'Click in Iframe'
                and require_json_object(node, 'deep tree node').get('frame_path')
                for node in elements
            ), elements

            found = await element_find_deep('smoke-deep-iframe', tab_info.tab_id, '#iframe-btn', timeout=8)
            assert found['success'] is True, found
            found_elements = array_at(found, 'elements')
            assert require_json_object(found_elements[0], 'found element')['frame_path'] == ['#iframe-1']
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_deep_tree_nested_iframe_and_find_deep() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await launch_and_goto_fixture('nested-iframe.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.dom.deep_traversal import element_find_deep, page_get_tree_deep

            tab_info = await register_smoke_tab(browser, tab, 'smoke-deep-nested')
            result = await page_get_tree_deep('smoke-deep-nested', tab_info.tab_id, timeout=10)
            assert result['success'] is True, result
            assert result['partial'] is False, result
            elements = array_at(result, 'elements')
            assert any(
                require_json_object(node, 'deep tree node').get('text') == 'Click in Iframe'
                and require_json_object(node, 'deep tree node').get('frame_path') == ['#nested-iframe', '#iframe-1']
                for node in elements
            ), elements

            found = await element_find_deep('smoke-deep-nested', tab_info.tab_id, '#iframe-btn', timeout=8)
            assert found['success'] is True, found
            found_elements = array_at(found, 'elements')
            assert require_json_object(found_elements[0], 'found element')['frame_path'] == [
                '#nested-iframe',
                '#iframe-1',
            ]
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_deep_tree_shadow_dom_and_find_deep() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await launch_and_goto_fixture('shadow-dom.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.dom.deep_traversal import element_find_deep, page_get_tree_deep

            tab_info = await register_smoke_tab(browser, tab, 'smoke-deep-shadow')
            result = await page_get_tree_deep('smoke-deep-shadow', tab_info.tab_id, timeout=10)
            assert result['success'] is True, result
            assert result['partial'] is False, result
            assert array_at(result, 'shadow_roots'), result
            elements = array_at(result, 'elements')
            assert any(
                require_json_object(node, 'deep tree node').get('text') == 'Shadow Button'
                and require_json_object(node, 'deep tree node').get('shadow_path') == ['#shadow-host']
                for node in elements
            ), elements

            found = await element_find_deep('smoke-deep-shadow', tab_info.tab_id, '#shadow-btn', timeout=8)
            assert found['success'] is True, found
            found_elements = array_at(found, 'elements')
            assert require_json_object(found_elements[0], 'found element')['shadow_path'] == ['#shadow-host']
    finally:
        await stop_smoke_browser(browser)
