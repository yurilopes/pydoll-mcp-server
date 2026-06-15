"""Tab management tools: list, activate, close, recover."""

from __future__ import annotations

import asyncio

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.models import ResourceHealth
from pydoll_mcp_server.browser.pydoll_compat import (
    bring_tab_to_front,
    close_tab,
    get_tab_title,
    get_tab_url,
    refresh_tab,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, ResourceState, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject
from pydoll_mcp_server.logging import get_logger
from pydoll_mcp_server.server_state import get_server_state


async def tab_list(
    client_id: str,
    browser_id: str = '',
) -> JsonObject:
    registry = get_registry()
    tabs = registry.list_tabs(client_id, browser_id if browser_id else None)

    for t in tabs:
        pydoll_tab = t.pydoll_tab
        live_url = await get_tab_url(pydoll_tab)
        if live_url:
            t.url = live_url
        live_title = await get_tab_title(pydoll_tab)
        if live_title:
            t.title = live_title

    return {
        'success': True,
        'tabs': [t.summary() for t in tabs],
    }


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
        return e.to_dict()

    try:
        async with tab_operation_lock(tab_id):
            pydoll_tab = tab_info.pydoll_tab
            try:
                await asyncio.wait_for(close_tab(pydoll_tab), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning(f'Tab {tab_id} close timed out')
            except Exception as e:
                logger.error(f'Error closing tab {tab_id}: {e}')

            registry.remove_tab(client_id, tab_id)
        return {
            'success': True,
            'tab_id': tab_id,
            'closed': True,
        }
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f'Error closing tab: {e}',
            retryable=True,
        ).to_dict()


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
            async with tab_operation_lock(tab_id):
                pydoll_browser = browser_info.pydoll_browser
                new_tab = await asyncio.wait_for(
                    pydoll_browser.new_tab(),
                    timeout=30.0,
                )
                tab_info.pydoll_tab = new_tab
                tab_info.health = ResourceHealth.HEALTHY
                tab_info.document_generation += 1
                state.record_recovery()
                return {
                    'success': True,
                    'tab_id': tab_id,
                    'actions_attempted': actions_attempted,
                    'final_state': 'healthy',
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
