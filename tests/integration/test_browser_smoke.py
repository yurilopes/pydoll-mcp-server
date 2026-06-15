"""Smoke tests with real browser (headless). Opt-in via -m browser_smoke marker."""

from __future__ import annotations

import asyncio
import atexit
import importlib.util
import os
import tempfile
import threading
import time
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from pydoll.browser.chromium.base import Browser
from pydoll.browser.tab import Tab

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.pydoll_compat import create_chromium_options, stop_browser
from pydoll_mcp_server.json_types import JsonArray, JsonObject, require_json_object
from tests.typing_helpers import array_at, int_at, string_at

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]

FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures' / 'pages'


class _QuietFixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@lru_cache
def _fixture_server() -> ThreadingHTTPServer:
    # Browser smoke tests use HTTP because production navigation blocks local file reads.
    handler = partial(_QuietFixtureHandler, directory=str(FIXTURES_DIR))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    atexit.register(server.shutdown)
    return server


def build_fixture_url(filename: str) -> str:
    server = _fixture_server()
    return f'http://127.0.0.1:{server.server_port}/{filename}'


async def launch_and_goto_fixture(page_file: str) -> tuple[Browser, Tab]:
    from pydoll.browser import Chrome

    options = create_chromium_options()
    options.headless = True
    options.add_argument('--no-sandbox')
    browser = Chrome(options=options)
    tab = await asyncio.wait_for(browser.start(), timeout=30.0)
    await asyncio.wait_for(
        tab.go_to(build_fixture_url(page_file), timeout=10),
        timeout=15.0,
    )
    return browser, tab


async def stop_smoke_browser(browser: Browser) -> None:
    # Browser cleanup is best-effort because test assertions must preserve the original failure.
    try:
        await asyncio.wait_for(stop_browser(browser), timeout=10.0)
    except Exception:
        return


async def register_smoke_tab(browser: Browser, tab: Tab, client_id: str) -> TabInfo:
    from pydoll_mcp_server.browser.profiles import ProfileManager
    from pydoll_mcp_server.browser.registry import get_registry
    from pydoll_mcp_server.config import get_config

    runtime_dir = Path(tempfile.gettempdir()) / 'pydoll-mcp-server-smoke'
    os.environ['PYDOLL_MCP_RUNTIME_DIR'] = str(runtime_dir)
    get_config.cache_clear()
    registry = get_registry()
    profile_mgr = ProfileManager()
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


def _find_node_by_id(nodes: JsonArray, node_id: str) -> JsonObject:
    matches: list[JsonObject] = []
    for value in nodes:
        node = require_json_object(value, 'tree node')
        attrs = require_json_object(node.get('attrs'), 'tree node attrs')
        if attrs.get('id') == node_id:
            matches.append(node)
    assert matches, f'Node with id={node_id!r} not found'
    return matches[0]


@pytest.mark.asyncio
async def test_browser_smoke_launch_navigate_interact() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await launch_and_goto_fixture('simple.html')
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
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_page_get_tree_returns_nodes() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await launch_and_goto_fixture('simple.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.browser.profiles import ProfileManager
            from pydoll_mcp_server.browser.registry import get_registry
            from pydoll_mcp_server.config import get_config
            from pydoll_mcp_server.dom.tree import build_page_tree

            runtime_dir = Path(tempfile.gettempdir()) / 'pydoll-mcp-server-smoke'
            os.environ['PYDOLL_MCP_RUNTIME_DIR'] = str(runtime_dir)
            get_config.cache_clear()
            registry = get_registry()
            profile_mgr = ProfileManager()
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
                'smoke-test-client',
                tab_info.tab_id,
            )

            assert result['success'] is True, f'Tree build failed: {result}'
            assert int_at(result, 'count') > 0, f'Tree is empty: {result}'
            assert result['root_id'] is not None, 'root_id is None'
            nodes = array_at(result, 'nodes')
            assert len(nodes) > 0, 'No nodes'

            button_nodes = [
                require_json_object(node, 'tree node')
                for node in nodes
                if require_json_object(node, 'tree node').get('tag') == 'button'
            ]
            assert len(button_nodes) > 0, f'No button node found. Nodes: {nodes[:5]}'
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_observe_tree_then_click_by_element_id() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await launch_and_goto_fixture('simple.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.browser.script_utils import extract_script_value
            from pydoll_mcp_server.dom.tree import build_page_tree
            from pydoll_mcp_server.tools.elements import element_click

            tab_info = await register_smoke_tab(browser, tab, 'smoke-observe-click')
            tree = await build_page_tree('smoke-observe-click', tab_info.tab_id)
            button_node = _find_node_by_id(array_at(tree, 'nodes'), 'btn-click')

            click_result = await element_click(
                'smoke-observe-click',
                tab_info.tab_id,
                string_at(button_node, 'elementId'),
            )
            assert click_result['success'] is True, click_result

            await asyncio.sleep(0.2)
            result = await tab.execute_script(
                'return document.getElementById("result").textContent;',
                return_by_value=True,
            )
            assert extract_script_value(result) == 'clicked'
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_observe_tree_then_fill_utf8_by_element_id() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await launch_and_goto_fixture('form.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.browser.script_utils import extract_script_value
            from pydoll_mcp_server.dom.tree import build_page_tree
            from pydoll_mcp_server.tools.elements import element_fill

            tab_info = await register_smoke_tab(browser, tab, 'smoke-observe-fill')
            tree = await build_page_tree('smoke-observe-fill', tab_info.tab_id)
            input_node = _find_node_by_id(array_at(tree, 'nodes'), 'input-text')
            text = 'Olá mundo, 日本語, 한국어, 中文'

            fill_result = await element_fill(
                'smoke-observe-fill',
                tab_info.tab_id,
                string_at(input_node, 'elementId'),
                text,
            )
            assert fill_result['success'] is True, fill_result

            result = await tab.execute_script(
                'return document.getElementById("input-text").value;',
                return_by_value=True,
            )
            assert extract_script_value(result) == text
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_js_evaluate_returns_object() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await launch_and_goto_fixture('simple.html')
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
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_page_screenshot_base64_no_path() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    browser, tab = await launch_and_goto_fixture('simple.html')
    try:
        screenshot = await tab.take_screenshot(as_base64=True)
        assert screenshot is not None and len(screenshot) > 0, 'Screenshot is empty'
    finally:
        await stop_smoke_browser(browser)
