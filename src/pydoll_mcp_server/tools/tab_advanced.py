"""Advanced tab lifecycle, health, dialogs, and popup watches."""

from __future__ import annotations

import asyncio

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.models import ResourceHealth
from pydoll_mcp_server.browser.pydoll_compat import (
    enable_page_events,
    get_tab_title,
    get_tab_url,
    try_close_tab,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.snapshots import get_snapshot_manager
from pydoll_mcp_server.browser.watches import get_watch_manager
from pydoll_mcp_server.dom.element_cache import get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject


async def tab_new(client_id: str, browser_id: str, url: str = '') -> JsonObject:
    try:
        browser = get_registry().get_browser(client_id, browser_id)
        tab = await browser.pydoll_browser.new_tab(url=url)
        info = get_registry().register_tab(client_id, browser_id, tab, url=url)
        return {'success': True, 'tab': info.summary()}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'New tab failed: {exc}', retryable=True).to_dict()


async def tab_duplicate(client_id: str, tab_id: str) -> JsonObject:
    try:
        tab, browser = get_registry().resolve_tab_with_browser(client_id, tab_id)
        return await tab_new(client_id, browser.browser_id, await get_tab_url(tab.pydoll_tab))
    except StructuredError as exc:
        return exc.to_dict()


async def tab_health_check(client_id: str, tab_id: str, timeout: float = 5.0) -> JsonObject:
    try:
        info = get_registry().get_tab(client_id, tab_id)

        async def probe() -> tuple[str, str]:
            url = await get_tab_url(info.pydoll_tab)
            title = await get_tab_title(info.pydoll_tab)
            await info.pydoll_tab.execute_script('return document.readyState', return_by_value=True)
            return url, title

        url, title = await asyncio.wait_for(probe(), min(timeout, 15.0))
        info.health = ResourceHealth.HEALTHY
        return {
            'success': True,
            'tab_id': tab_id,
            'health': 'healthy',
            'responsive': True,
            'url': url,
            'title': title,
            'recommendation': 'none',
        }
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return {
            'success': True,
            'tab_id': tab_id,
            'health': 'unhealthy',
            'responsive': False,
            'error': str(exc),
            'recommendation': 'Use tab_recover, then tab_recreate if required.',
        }


async def tab_recreate(client_id: str, tab_id: str, force: bool = False, preserve_url: bool = True) -> JsonObject:
    if not force:
        return StructuredError(ErrorCode.INVALID_INPUT, 'tab_recreate requires force=true').to_dict()
    try:
        info, browser = get_registry().resolve_tab_with_browser(client_id, tab_id)
        url = await get_tab_url(info.pydoll_tab) if preserve_url else ''
        async with tab_operation_lock(tab_id):
            new_tab = await browser.pydoll_browser.new_tab(url=url)
            old_tab = info.pydoll_tab
            info.pydoll_tab = new_tab
            info.url = url
            info.document_generation += 1
            info.health = ResourceHealth.HEALTHY
            get_element_cache().invalidate_tab(tab_id)
            get_snapshot_manager().clear_tab(client_id, tab_id)
            await try_close_tab(old_tab)
        state_lost: JsonArray = ['dom', 'element_ids', 'snapshots', 'form_state']
        return {
            'success': True,
            'tab_id': tab_id,
            'recreated': True,
            'preserved_url': bool(url),
            'state_lost': state_lost,
        }
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Tab recreate failed: {exc}', retryable=True).to_dict()


async def dialog_list(client_id: str, tab_id: str) -> JsonObject:
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        await enable_page_events(tab)
        if not await tab.has_dialog():
            return {'success': True, 'dialogs': [], 'count': 0}
        return {'success': True, 'dialogs': [{'message': await tab.get_dialog_message()}], 'count': 1}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Dialog inspection failed: {exc}').to_dict()


async def dialog_handle(
    client_id: str,
    tab_id: str,
    action: str = 'accept',
    prompt_text: str = '',
) -> JsonObject:
    if action not in ('accept', 'dismiss'):
        return StructuredError(ErrorCode.INVALID_INPUT, 'action must be accept or dismiss').to_dict()
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        # Dialog handling must be able to release a click that is waiting inside
        # the tab mutation lock.
        await enable_page_events(tab)
        await tab.handle_dialog(action == 'accept', prompt_text or None)
        return {'success': True, 'handled': True, 'action': action}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Dialog handling failed: {exc}').to_dict()


async def popup_prepare(client_id: str, tab_id: str, timeout: float = 30.0) -> JsonObject:
    try:
        info = get_registry().get_tab(client_id, tab_id)
        baseline = {item.tab_id for item in get_registry().list_tabs(client_id, info.browser_id)}
        watch = get_watch_manager().create(client_id, tab_id, 'popup', baseline=baseline)
        return {'success': True, 'watch_id': watch.watch_id, 'timeout': timeout}
    except StructuredError as exc:
        return exc.to_dict()


async def popup_wait(client_id: str, watch_id: str, timeout: float = 30.0) -> JsonObject:
    try:
        watch = get_watch_manager().get(client_id, watch_id, 'popup')
        source = get_registry().get_tab(client_id, watch.tab_id)

        async def wait() -> JsonObject:
            while True:
                browser = get_registry().get_browser(client_id, source.browser_id)
                known_objects = {item.pydoll_tab for item in get_registry().list_tabs(client_id, source.browser_id)}
                for pydoll_tab in await browser.pydoll_browser.get_opened_tabs():
                    if pydoll_tab not in known_objects:
                        get_registry().register_tab(client_id, source.browser_id, pydoll_tab)
                tabs = get_registry().list_tabs(client_id, source.browser_id)
                created = [item for item in tabs if item.tab_id not in (watch.baseline or set())]
                if created:
                    return {'success': True, 'watch_id': watch_id, 'tab': created[0].summary()}
                await asyncio.sleep(0.1)

        return await asyncio.wait_for(wait(), min(timeout, 120.0))
    except StructuredError as exc:
        return exc.to_dict()
    except TimeoutError:
        return StructuredError(ErrorCode.TIMEOUT, 'Popup wait timed out', retryable=True).to_dict()
