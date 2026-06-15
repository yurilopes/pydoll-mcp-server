"""Real-browser smoke coverage for v0.2 agent-friendly tools."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from unittest.mock import patch

import pytest
from pydoll.elements.web_element import WebElement

from tests.integration.test_browser_smoke import launch_and_goto_fixture, register_smoke_tab, stop_smoke_browser
from tests.typing_helpers import int_at, object_at, string_at

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
    from pydoll_mcp_server.tools.element_resolver import cache_element
    from pydoll_mcp_server.tools.elements import element_click
    from pydoll_mcp_server.tools.files_advanced import page_print_pdf
    from pydoll_mcp_server.tools.inspection import console_enable, console_list
    from pydoll_mcp_server.tools.page_advanced import page_get_accessibility_tree, page_snapshot
    from pydoll_mcp_server.tools.waits import page_wait_for_function

    browser, tab = await launch_and_goto_fixture('advanced.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_ALLOW_NO_AUTH': 'true'}):
            info = await register_smoke_tab(browser, tab, 'smoke-advanced')
        found = await element_find_by_test_id('smoke-advanced', info.tab_id, 'agent-input')
        assert found['success'] is True

        check = await element_find_by_test_id('smoke-advanced', info.tab_id, 'missing')
        assert check['error_code'] == 'RESOURCE_NOT_FOUND'

        checkbox = await tab.query('#agree', timeout=3, raise_exc=False)
        assert isinstance(checkbox, WebElement)
        checkbox_id = cache_element(get_element_cache(), info, checkbox)
        assert (await element_check('smoke-advanced', info.tab_id, checkbox_id))['success'] is True
        checkbox_state = object_at(await element_get_state('smoke-advanced', info.tab_id, checkbox_id), 'state')
        assert checkbox_state['checked'] is True

        select = await tab.query('#choice', timeout=3, raise_exc=False)
        assert isinstance(select, WebElement)
        select_id = cache_element(get_element_cache(), info, select)
        selected = await element_select_option('smoke-advanced', info.tab_id, select_id, values=['two'])
        assert selected['success'] is True

        await console_enable('smoke-advanced', info.tab_id)
        log = await tab.query('#log', timeout=3, raise_exc=False)
        assert isinstance(log, WebElement)
        log_id = cache_element(get_element_cache(), info, log)
        await element_click('smoke-advanced', info.tab_id, log_id)
        await asyncio.sleep(0.3)
        assert int_at(await console_list('smoke-advanced', info.tab_id), 'count') >= 1

        snapshot = await page_snapshot('smoke-advanced', info.tab_id)
        assert string_at(snapshot, 'snapshot_id')
        assert int_at(await page_get_accessibility_tree('smoke-advanced', info.tab_id), 'count') > 0
        waited = await page_wait_for_function(
            'smoke-advanced',
            info.tab_id,
            'return document.readyState === "complete"',
        )
        assert waited['success'] is True
        pdf = await page_print_pdf('smoke-advanced', info.tab_id, as_base64=True)
        assert pdf['success'] is True and string_at(pdf, 'data')
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_advanced_popup_and_download_workflows() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')
    from pydoll_mcp_server.dom.element_cache import get_element_cache
    from pydoll_mcp_server.tools.element_resolver import cache_element
    from pydoll_mcp_server.tools.elements import element_click
    from pydoll_mcp_server.tools.files_advanced import download_prepare, download_wait
    from pydoll_mcp_server.tools.tab_advanced import popup_prepare, popup_wait

    browser, tab = await launch_and_goto_fixture('advanced.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_ALLOW_NO_AUTH': 'true'}):
            info = await register_smoke_tab(browser, tab, 'smoke-events')
        cache = get_element_cache()

        popup_watch = await popup_prepare('smoke-events', info.tab_id)
        popup = await tab.query('#popup', timeout=3, raise_exc=False)
        assert isinstance(popup, WebElement)
        await element_click('smoke-events', info.tab_id, cache_element(cache, info, popup))
        opened = await popup_wait('smoke-events', string_at(popup_watch, 'watch_id'), timeout=10)
        assert opened['success'] is True

        download_watch = await download_prepare('smoke-events', info.tab_id, timeout=15)
        await asyncio.sleep(0.2)
        download = await tab.query('#download', timeout=3, raise_exc=False)
        assert isinstance(download, WebElement)
        await element_click('smoke-events', info.tab_id, cache_element(cache, info, download))
        downloaded = await download_wait('smoke-events', string_at(download_watch, 'watch_id'), timeout=15)
        assert downloaded['success'] is True
    finally:
        await stop_smoke_browser(browser)
