"""Smoke tests with real browser (headless). Opt-in via -m browser_smoke marker."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]

FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures' / 'pages'


def _build_page_url(filename: str) -> str:
    return (FIXTURES_DIR / filename).as_uri()


async def _launch_and_goto(page_file: str) -> tuple:
    from pydoll.browser import Chrome
    from pydoll.browser.options import ChromiumOptions

    options = ChromiumOptions()
    options.headless = True
    options.add_argument('--no-sandbox')
    browser = Chrome(options=options)
    tab = await asyncio.wait_for(browser.start(), timeout=30.0)
    await asyncio.wait_for(
        tab.go_to(_build_page_url(page_file), timeout=10), timeout=15.0,
    )
    return browser, tab


async def _register_smoke_tab(browser, tab, client_id: str):
    from pydoll_mcp_server.browser.profiles import get_profile_manager
    from pydoll_mcp_server.browser.registry import get_registry

    registry = get_registry()
    profile_mgr = get_profile_manager()
    profile = profile_mgr.create_temporary(client_id)

    browser_info = registry.register_browser(
        client_id=client_id,
        browser=browser,
        profile=profile,
        headless=True,
    )
    return registry.register_tab(
        client_id=client_id,
        browser_id=browser_info.browser_id,
        pydoll_tab=tab,
        url=await tab.current_url,
        title=await tab.title,
    )


def _find_node_by_id(nodes: list[dict], node_id: str) -> dict:
    matches = [
        node for node in nodes
        if isinstance(node.get('attrs'), dict) and node['attrs'].get('id') == node_id
    ]
    assert matches, f'Node with id={node_id!r} not found'
    return matches[0]


@pytest.mark.asyncio
async def test_browser_smoke_launch_navigate_interact() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await _launch_and_goto('simple.html')
    try:
        title = await tab.title
        assert isinstance(title, str) and len(title) > 0, f'Title empty: {title!r}'

        url = await tab.current_url
        assert 'simple.html' in str(url), f'URL mismatch: {url}'

        btn = await tab.query('#btn-click', timeout=5, find_all=False, raise_exc=False)
        assert btn is not None, 'Button not found'

        await btn.click()
        time.sleep(0.5)  # noqa: ASYNC251

        result_el = await tab.query('#result', timeout=3, find_all=False, raise_exc=False)
        assert result_el is not None, 'Result span not found'

        result_text = await result_el.text
        assert 'clicked' in str(result_text).lower(), f'Unexpected result: {result_text}'
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)


@pytest.mark.asyncio
async def test_page_get_tree_returns_nodes() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await _launch_and_goto('simple.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.browser.profiles import get_profile_manager
            from pydoll_mcp_server.browser.registry import get_registry
            from pydoll_mcp_server.dom.tree import build_page_tree

            registry = get_registry()
            profile_mgr = get_profile_manager()
            profile = profile_mgr.create_temporary('smoke-test-client')

            browser_info = registry.register_browser(
                client_id='smoke-test-client',
                browser=browser,
                profile=profile,
                headless=True,
            )
            tab_info = registry.register_tab(
                client_id='smoke-test-client',
                browser_id=browser_info.browser_id,
                pydoll_tab=tab,
                url=await tab.current_url,
                title=await tab.title,
            )

            result = await build_page_tree(
                'smoke-test-client', tab_info.tab_id,
            )

            assert result['success'] is True, f'Tree build failed: {result}'
            assert result['count'] > 0, f'Tree is empty: {result}'
            assert result['root_id'] is not None, 'root_id is None'
            assert result['nodes'] is not None and len(result['nodes']) > 0, 'No nodes'

            button_nodes = [n for n in result['nodes'] if n.get('tag') == 'button']
            assert len(button_nodes) > 0, (
                f'No button node found. Nodes: {result["nodes"][:5]}'
            )
    finally:
        if browser is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(browser.stop(), timeout=10.0)


@pytest.mark.asyncio
async def test_observe_tree_then_click_by_element_id() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await _launch_and_goto('simple.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.browser.script_utils import extract_script_value
            from pydoll_mcp_server.dom.tree import build_page_tree
            from pydoll_mcp_server.tools.elements import element_click

            tab_info = await _register_smoke_tab(browser, tab, 'smoke-observe-click')
            tree = await build_page_tree('smoke-observe-click', tab_info.tab_id)
            button_node = _find_node_by_id(tree['nodes'], 'btn-click')

            click_result = await element_click(
                'smoke-observe-click',
                tab_info.tab_id,
                button_node['elementId'],
            )
            assert click_result['success'] is True, click_result

            await asyncio.sleep(0.2)
            result = await tab.execute_script(
                'return document.getElementById("result").textContent;',
                return_by_value=True,
            )
            assert extract_script_value(result) == 'clicked'
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)


@pytest.mark.asyncio
async def test_observe_tree_then_fill_utf8_by_element_id() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await _launch_and_goto('form.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.browser.script_utils import extract_script_value
            from pydoll_mcp_server.dom.tree import build_page_tree
            from pydoll_mcp_server.tools.elements import element_fill

            tab_info = await _register_smoke_tab(browser, tab, 'smoke-observe-fill')
            tree = await build_page_tree('smoke-observe-fill', tab_info.tab_id)
            input_node = _find_node_by_id(tree['nodes'], 'input-text')
            text = 'Olá mundo, 日本語, 한국어, 中文'

            fill_result = await element_fill(
                'smoke-observe-fill',
                tab_info.tab_id,
                input_node['elementId'],
                text,
            )
            assert fill_result['success'] is True, fill_result

            result = await tab.execute_script(
                'return document.getElementById("input-text").value;',
                return_by_value=True,
            )
            assert extract_script_value(result) == text
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)


@pytest.mark.asyncio
async def test_js_evaluate_returns_object() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await _launch_and_goto('simple.html')
    try:
        result = await tab.execute_script(
            'return {answer: 42, text: "ok"};',
            return_by_value=True,
        )

        from pydoll_mcp_server.browser.script_utils import extract_script_value
        raw_value = extract_script_value(result)
        assert raw_value is not None, f'js_evaluate returned None: {result}'
        assert isinstance(raw_value, dict), f'Expected dict, got {type(raw_value)}: {raw_value}'
        assert raw_value.get('answer') == 42, f'Expected answer=42, got {raw_value}'
        assert raw_value.get('text') == 'ok', f'Expected text=ok, got {raw_value}'
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)


@pytest.mark.asyncio
async def test_page_screenshot_base64_no_path() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await _launch_and_goto('simple.html')
    try:
        screenshot = await tab.take_screenshot(as_base64=True)
        assert screenshot is not None and len(screenshot) > 0, 'Screenshot is empty'
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)


@pytest.mark.asyncio
async def test_deep_tree_simple_iframe_and_find_deep() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await _launch_and_goto('iframe-parent.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.dom.deep_traversal import (
                element_find_deep,
                page_get_tree_deep,
            )

            tab_info = await _register_smoke_tab(browser, tab, 'smoke-deep-iframe')
            result = await page_get_tree_deep(
                'smoke-deep-iframe', tab_info.tab_id, timeout=10,
            )
            assert result['success'] is True, result
            assert result['partial'] is False, result
            assert any(result['frames']), result
            assert any(
                node.get('text') == 'Click in Iframe' and node.get('frame_path')
                for node in result['elements']
            ), result['elements']

            found = await element_find_deep(
                'smoke-deep-iframe', tab_info.tab_id, '#iframe-btn', timeout=8,
            )
            assert found['success'] is True, found
            assert found['elements'][0]['frame_path'] == ['#iframe-1']
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)


@pytest.mark.asyncio
async def test_deep_tree_nested_iframe_and_find_deep() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await _launch_and_goto('nested-iframe.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.dom.deep_traversal import (
                element_find_deep,
                page_get_tree_deep,
            )

            tab_info = await _register_smoke_tab(browser, tab, 'smoke-deep-nested')
            result = await page_get_tree_deep(
                'smoke-deep-nested', tab_info.tab_id, timeout=10,
            )
            assert result['success'] is True, result
            assert result['partial'] is False, result
            assert any(
                node.get('text') == 'Click in Iframe'
                and node.get('frame_path') == ['#nested-iframe', '#iframe-1']
                for node in result['elements']
            ), result['elements']

            found = await element_find_deep(
                'smoke-deep-nested', tab_info.tab_id, '#iframe-btn', timeout=8,
            )
            assert found['success'] is True, found
            assert found['elements'][0]['frame_path'] == ['#nested-iframe', '#iframe-1']
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)


@pytest.mark.asyncio
async def test_deep_tree_shadow_dom_and_find_deep() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await _launch_and_goto('shadow-dom.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.dom.deep_traversal import (
                element_find_deep,
                page_get_tree_deep,
            )

            tab_info = await _register_smoke_tab(browser, tab, 'smoke-deep-shadow')
            result = await page_get_tree_deep(
                'smoke-deep-shadow', tab_info.tab_id, timeout=10,
            )
            assert result['success'] is True, result
            assert result['partial'] is False, result
            assert result['shadow_roots'], result
            assert any(
                node.get('text') == 'Shadow Button'
                and node.get('shadow_path') == ['#shadow-host']
                for node in result['elements']
            ), result['elements']

            found = await element_find_deep(
                'smoke-deep-shadow', tab_info.tab_id, '#shadow-btn', timeout=8,
            )
            assert found['success'] is True, found
            assert found['elements'][0]['shadow_path'] == ['#shadow-host']
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)
