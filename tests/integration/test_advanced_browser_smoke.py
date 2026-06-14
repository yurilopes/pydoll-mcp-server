"""Real-browser smoke coverage for v0.2 agent-friendly tools."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import os
from unittest.mock import patch

import pytest

from tests.integration.test_browser_smoke import _launch_and_goto, _register_smoke_tab

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]


@pytest.mark.asyncio
async def test_advanced_observe_interact_wait_console_and_pdf() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')
    from pydoll_mcp_server.dom.element_cache import get_element_cache
    from pydoll_mcp_server.tools.element_advanced import (
        element_check,
        element_find_by_test_id,
        element_get_state,
        element_select_option,
    )
    from pydoll_mcp_server.tools.element_resolver import _cache_element
    from pydoll_mcp_server.tools.elements import element_click
    from pydoll_mcp_server.tools.files_advanced import page_print_pdf
    from pydoll_mcp_server.tools.inspection import console_enable, console_list
    from pydoll_mcp_server.tools.page_advanced import page_get_accessibility_tree, page_snapshot
    from pydoll_mcp_server.tools.waits import page_wait_for_function

    browser, tab = await _launch_and_goto('advanced.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_ALLOW_NO_AUTH': 'true'}):
            info = await _register_smoke_tab(browser, tab, 'smoke-advanced')
        found = await element_find_by_test_id('smoke-advanced', info.tab_id, 'agent-input')
        assert found['success'] is True

        check = await element_find_by_test_id('smoke-advanced', info.tab_id, 'missing')
        assert check['error_code'] == 'RESOURCE_NOT_FOUND'

        checkbox = await tab.query('#agree', timeout=3, raise_exc=False)
        checkbox_id = _cache_element(get_element_cache(), info, checkbox)
        assert (await element_check('smoke-advanced', info.tab_id, checkbox_id))['success'] is True
        assert (await element_get_state('smoke-advanced', info.tab_id, checkbox_id))['state']['checked'] is True

        select = await tab.query('#choice', timeout=3, raise_exc=False)
        select_id = _cache_element(get_element_cache(), info, select)
        selected = await element_select_option('smoke-advanced', info.tab_id, select_id, values=['two'])
        assert selected['success'] is True

        await console_enable('smoke-advanced', info.tab_id)
        log = await tab.query('#log', timeout=3, raise_exc=False)
        log_id = _cache_element(get_element_cache(), info, log)
        await element_click('smoke-advanced', info.tab_id, log_id)
        await asyncio.sleep(0.3)
        assert (await console_list('smoke-advanced', info.tab_id))['count'] >= 1

        snapshot = await page_snapshot('smoke-advanced', info.tab_id)
        assert snapshot['snapshot_id']
        assert (await page_get_accessibility_tree('smoke-advanced', info.tab_id))['count'] > 0
        waited = await page_wait_for_function(
            'smoke-advanced', info.tab_id, 'return document.readyState === "complete"',
        )
        assert waited['success'] is True
        pdf = await page_print_pdf('smoke-advanced', info.tab_id, as_base64=True)
        assert pdf['success'] is True and pdf['data']
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)


@pytest.mark.asyncio
async def test_advanced_popup_and_download_workflows() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')
    from pydoll_mcp_server.dom.element_cache import get_element_cache
    from pydoll_mcp_server.tools.element_resolver import _cache_element
    from pydoll_mcp_server.tools.elements import element_click
    from pydoll_mcp_server.tools.files_advanced import download_prepare, download_wait
    from pydoll_mcp_server.tools.tab_advanced import popup_prepare, popup_wait

    browser, tab = await _launch_and_goto('advanced.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_ALLOW_NO_AUTH': 'true'}):
            info = await _register_smoke_tab(browser, tab, 'smoke-events')
        cache = get_element_cache()

        popup_watch = await popup_prepare('smoke-events', info.tab_id)
        popup = await tab.query('#popup', timeout=3, raise_exc=False)
        await element_click('smoke-events', info.tab_id, _cache_element(cache, info, popup))
        opened = await popup_wait('smoke-events', popup_watch['watch_id'], timeout=10)
        assert opened['success'] is True

        download_watch = await download_prepare('smoke-events', info.tab_id, timeout=15)
        await asyncio.sleep(0.2)
        download = await tab.query('#download', timeout=3, raise_exc=False)
        await element_click('smoke-events', info.tab_id, _cache_element(cache, info, download))
        downloaded = await download_wait('smoke-events', download_watch['watch_id'], timeout=15)
        assert downloaded['success'] is True
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(browser.stop(), timeout=10.0)
