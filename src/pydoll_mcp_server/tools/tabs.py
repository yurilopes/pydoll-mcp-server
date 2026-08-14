"""Tab management tools: list, activate, close, recover."""

from __future__ import annotations

import asyncio

from pydoll.browser.chromium.base import Browser
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import browser_operation_lock, tab_operation_lock
from pydoll_mcp_server.browser.models import ResourceHealth
from pydoll_mcp_server.browser.pydoll_compat import (
    bring_tab_to_front,
    close_tab,
    get_opened_tabs,
    get_tab_target_id,
    get_tab_title,
    get_tab_url,
    refresh_tab,
    tab_has_dialog,
    try_close_tab,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.tab_reconciliation import TabSyncResult, sync_browser_tabs
from pydoll_mcp_server.config import get_limits_config
from pydoll_mcp_server.errors import ErrorCode, ResourceState, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject
from pydoll_mcp_server.logging import get_logger
from pydoll_mcp_server.server_state import get_server_state
from pydoll_mcp_server.tools.form_runtime import mark_document_changed


async def tab_list(
    client_id: str,
    browser_id: str = '',
) -> JsonObject:
    registry = get_registry()
    browsers = registry.list_browsers(client_id)
    if browser_id:
        browsers = [browser for browser in browsers if browser.browser_id == browser_id]
    sync_results: list[TabSyncResult] = []
    for browser in browsers:
        async with browser_operation_lock(browser.browser_id):
            sync_results.append(await sync_browser_tabs(client_id, browser.browser_id))
    tabs = registry.list_tabs(client_id, browser_id if browser_id else None)

    for t in tabs:
        pydoll_tab = t.pydoll_tab
        try:
            live_url = await get_tab_url(pydoll_tab)
            if live_url:
                t.url = live_url
            live_title = await get_tab_title(pydoll_tab)
            if live_title:
                t.title = live_title
        except Exception:
            t.health = ResourceHealth.DEGRADED

    max_tabs = get_limits_config().max_tabs_per_browser
    result: JsonObject = {
        'success': True,
        'tabs': [t.summary() for t in tabs],
    }
    if len(sync_results) == 1:
        result.update(sync_results[0].summary(max_tabs))
    else:
        result.update(
            {
                'actual_count': sum(item.actual_count for item in sync_results),
                'managed_count': len(tabs),
                'untracked_count': sum(item.untracked_count for item in sync_results),
                'stale_registry_count': sum(item.stale for item in sync_results),
                'max_tabs': max_tabs,
                'limit_exceeded': any(item.actual_count > max_tabs for item in sync_results),
                'reconciled': all(item.reconciled for item in sync_results),
                'sync': {
                    'added': sum(item.added for item in sync_results),
                    'removed': sum(item.removed for item in sync_results),
                    'stale': sum(item.stale for item in sync_results),
                },
            }
        )
    return result


async def tab_activate(
    client_id: str,
    tab_id: str,
) -> JsonObject:
    registry = get_registry()
    get_logger()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    try:
        pydoll_tab = tab_info.pydoll_tab
        try:
            await asyncio.wait_for(bring_tab_to_front(pydoll_tab), timeout=10.0)
        except asyncio.TimeoutError:
            return StructuredError(
                error_code=ErrorCode.TIMEOUT,
                message='Tab activation timed out',
                retryable=True,
                resource_state=ResourceState.DEGRADED,
            ).to_dict()
        for sibling in registry.list_tabs(client_id, tab_info.browser_id):
            sibling.active = sibling.tab_id == tab_id
        return {
            'success': True,
            'tab_id': tab_id,
            'active': True,
        }
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f'Error activating tab: {e}',
            retryable=False,
        ).to_dict()


async def tab_close(
    client_id: str,
    tab_id: str,
) -> JsonObject:
    registry = get_registry()
    logger = get_logger()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        if registry.was_tab_closed(client_id, tab_id):
            return {'success': True, 'tab_id': tab_id, 'closed': True, 'already_closed': True}
        return e.to_dict()

    requested_target_id = tab_info.target_id
    try:
        browser_info = registry.get_browser(client_id, tab_info.browser_id)
        async with browser_operation_lock(browser_info.browser_id):
            sync = await sync_browser_tabs(client_id, browser_info.browser_id)
            if not sync.reconciled:
                return StructuredError(
                    ErrorCode.TRANSPORT_UNAVAILABLE,
                    'Tab inventory is stale; close was not attempted.',
                    retryable=True,
                    resource_state=ResourceState.DEGRADED,
                    details={
                        **sync.summary(get_limits_config().max_tabs_per_browser),
                        'stale': True,
                        'close_attempted': False,
                    },
                    recovery_hint='Refresh the tab inventory successfully, then retry the close.',
                ).to_dict()
            try:
                tab_info = registry.get_tab(client_id, tab_id)
            except StructuredError as e:
                if registry.was_tab_closed(client_id, tab_id):
                    return {'success': True, 'tab_id': tab_id, 'closed': True, 'already_closed': True}
                if requested_target_id and all(
                    tab.target_id != requested_target_id
                    for tab in registry.list_tabs(client_id, browser_info.browser_id)
                ):
                    registry.mark_tab_closed(client_id, tab_id)
                    return {
                        'success': True,
                        'tab_id': tab_id,
                        'closed': True,
                        'already_closed': True,
                        'stale_inventory_reconciled': True,
                    }
                return e.to_dict()
            target_id = tab_info.target_id or get_tab_target_id(tab_info.pydoll_tab)
            pydoll_tab = tab_info.pydoll_tab
            if await _dialog_present(pydoll_tab):
                tab_info.close_pending = True
                return _dialog_error(tab_id)
            live_registry_tabs = registry.list_tabs(client_id, browser_info.browser_id)
            if len(live_registry_tabs) <= 1:
                tab_info.one_tab_safety_blocked = True
                return StructuredError(
                    ErrorCode.TIMEOUT,
                    'Closing the only managed tab is blocked by one-tab safety.',
                    retryable=False,
                    details={
                        'tab_id': tab_id,
                        'one_tab_safety': True,
                        'confirmed_closed': False,
                        'close_attempted': False,
                        'close_pending': False,
                        'one_tab_safety_blocked': True,
                    },
                    recovery_hint='Open another tab before closing this tab, or close the browser explicitly.',
                ).to_dict()

            close_error: Exception | None = None
            async with tab_operation_lock(tab_id):
                try:
                    await asyncio.wait_for(close_tab(pydoll_tab), timeout=10.0)
                except Exception as exc:
                    close_error = exc

            if not await _wait_for_target_closed(browser_info.pydoll_browser, target_id):
                if await _dialog_present(pydoll_tab):
                    tab_info.close_pending = True
                    return _dialog_error(tab_id)
                tab_info.close_pending = True
                if close_error is not None:
                    logger.error(f'Error closing tab {tab_id}: {close_error}')
                    return StructuredError(
                        ErrorCode.EXECUTION_ERROR,
                        f'Error closing tab: {close_error}',
                        retryable=True,
                        resource_state=ResourceState.DEGRADED,
                        details={'tab_id': tab_id, 'close_pending': True, 'confirmed_closed': False},
                    ).to_dict()
                logger.warning(f'Tab {tab_id} close was not confirmed')
                return StructuredError(
                    ErrorCode.TIMEOUT,
                    'Tab close was not confirmed by the browser.',
                    retryable=True,
                    resource_state=ResourceState.DEGRADED,
                    details={'tab_id': tab_id, 'close_pending': True, 'confirmed_closed': False},
                ).to_dict()

            from pydoll_mcp_server.browser.inspection import get_inspection_manager

            get_inspection_manager().remove(tab_id)
            registry.mark_tab_closed(client_id, tab_id)
            registry.remove_tab(client_id, tab_id)
        return {
            'success': True,
            'tab_id': tab_id,
            'closed': True,
            'confirmed_closed': True,
        }
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f'Error closing tab: {e}',
            retryable=True,
        ).to_dict()


async def _dialog_present(tab: object) -> bool:
    from pydoll.browser.tab import Tab

    if not isinstance(tab, Tab):
        return False
    try:
        return await tab_has_dialog(tab)
    except (AttributeError, OSError, PydollException, RuntimeError):
        return False


def _dialog_error(tab_id: str) -> JsonObject:
    return StructuredError(
        ErrorCode.DIALOG_PRESENT,
        'A browser dialog is blocking tab closure.',
        details={'tab_id': tab_id, 'close_pending': True},
        retryable=True,
        resource_state=ResourceState.DEGRADED,
        recovery_hint='Use dialog_list and dialog_handle before retrying tab_close.',
    ).to_dict()


async def _wait_for_target_closed(browser: Browser, target_id: str, timeout: float = 5.0) -> bool:
    if not target_id:
        return False
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            live_tabs = await get_opened_tabs(browser)
        except (AttributeError, OSError, PydollException, RuntimeError, TimeoutError):
            await asyncio.sleep(0.1)
            continue
        if all(get_tab_target_id(tab) != target_id for tab in live_tabs):
            return True
        await asyncio.sleep(0.1)
    try:
        live_tabs = await get_opened_tabs(browser)
    except (AttributeError, OSError, PydollException, RuntimeError, TimeoutError):
        return False
    return all(get_tab_target_id(tab) != target_id for tab in live_tabs)


async def tab_recover(
    client_id: str,
    tab_id: str,
    mode: str = 'reload',
    force: bool = False,
) -> JsonObject:
    registry = get_registry()
    logger = get_logger()
    state = get_server_state()

    try:
        tab_info, browser_info = registry.resolve_tab_with_browser(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    actions_attempted: JsonArray = []

    if mode == 'reload':
        actions_attempted.append('reload')
        try:
            async with tab_operation_lock(tab_id):
                pydoll_tab = tab_info.pydoll_tab
                await asyncio.wait_for(refresh_tab(pydoll_tab), timeout=30.0)
                mark_document_changed(client_id, tab_id, tab_info)
                tab_info.health = ResourceHealth.HEALTHY
                state.record_recovery()
                return {
                    'success': True,
                    'tab_id': tab_id,
                    'actions_attempted': actions_attempted,
                    'final_state': 'healthy',
                }
        except Exception as e:
            logger.error(f'Tab recovery reload failed for {tab_id}: {e}')

    if mode == 'recreate':
        if not force:
            return StructuredError(
                error_code=ErrorCode.INVALID_INPUT,
                message='Tab recreate requires force=true',
                retryable=False,
                recovery_hint='Set force=true to recreate the tab. This will lose page state.',
            ).to_dict()
        actions_attempted.append('recreate')
        try:
            async with browser_operation_lock(browser_info.browser_id):
                await sync_browser_tabs(client_id, browser_info.browser_id)
                tab_info = registry.get_tab(client_id, tab_id)
                async with tab_operation_lock(tab_id):
                    pydoll_browser = browser_info.pydoll_browser
                    old_tab = tab_info.pydoll_tab
                    new_tab = await asyncio.wait_for(
                        pydoll_browser.new_tab(),
                        timeout=30.0,
                    )
                    tab_info.pydoll_tab = new_tab
                    tab_info.target_id = get_tab_target_id(new_tab)
                    old_closed = await try_close_tab(old_tab)
                    from pydoll_mcp_server.browser.inspection import get_inspection_manager

                    get_inspection_manager().remove(tab_id)
                    tab_info.health = ResourceHealth.HEALTHY
                    mark_document_changed(client_id, tab_id, tab_info)
                    tab_info.close_pending = False
                sync = await sync_browser_tabs(client_id, browser_info.browser_id)
                if not old_closed:
                    return StructuredError(
                        ErrorCode.EXECUTION_ERROR,
                        'Replacement tab opened, but the previous tab could not be closed.',
                        retryable=True,
                        resource_state=ResourceState.DEGRADED,
                        details=sync.summary(get_limits_config().max_tabs_per_browser),
                    ).to_dict()
                state.record_recovery()
                return {
                    'success': True,
                    'tab_id': tab_id,
                    'actions_attempted': actions_attempted,
                    'final_state': 'healthy',
                    **sync.summary(get_limits_config().max_tabs_per_browser),
                }
        except Exception as e:
            logger.error(f'Tab recreation failed for {tab_id}: {e}')

    tab_info.health = ResourceHealth.UNHEALTHY
    state.record_unhealthy_tab()

    return StructuredError(
        error_code=ErrorCode.RESOURCE_UNHEALTHY,
        message=f'Tab {tab_id} is unhealthy, recovery failed',
        retryable=True,
        resource_state=ResourceState.UNHEALTHY,
        details={'actions_attempted': actions_attempted},
        recovery_hint='Try tab_recover with force=true and mode=recreate.',
    ).to_dict()
