"""Nonblocking waits and operation cancellation."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from fnmatch import fnmatch

from pydoll_mcp_server.browser.operations import get_operation_manager, operation_cancel
from pydoll_mcp_server.browser.pydoll_compat import get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_value
from pydoll_mcp_server.config import get_timeout_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_int,
    get_object,
    get_string,
    require_json_object,
)
from pydoll_mcp_server.tools.element_advanced import element_get_state
from pydoll_mcp_server.tools.inspection import network_list
from pydoll_mcp_server.tools.javascript import scan_script


async def page_wait_for_url(
    client_id: str,
    tab_id: str,
    pattern: str,
    match: str = 'glob',
    timeout: float | None = None,
    poll_interval: float = 0.1,
    operation_id: str = '',
) -> JsonObject:
    async def probe() -> JsonObject:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        return await _poll(lambda: _url_match(get_tab_url(tab), pattern, match), timeout, poll_interval, 'URL')

    return await _run(client_id, operation_id, probe())


async def page_wait_for_function(
    client_id: str,
    tab_id: str,
    script: str,
    timeout: float | None = None,
    poll_interval: float = 0.1,
    operation_id: str = '',
) -> JsonObject:
    blocked = scan_script(script)
    if blocked:
        blocked_patterns: JsonArray = []
        blocked_patterns.extend(blocked)
        return StructuredError(
            ErrorCode.BLOCKED_PATTERN,
            'Wait function contains sensitive side effects.',
            details={'patterns': blocked_patterns},
        ).to_dict()

    async def probe() -> JsonObject:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab

        async def evaluate() -> bool:
            return bool(extract_script_value(await tab.execute_script(script, return_by_value=True)))

        return await _poll(evaluate, timeout, poll_interval, 'function')

    return await _run(client_id, operation_id, probe())


async def element_wait_for_state(
    client_id: str,
    tab_id: str,
    element_id: str,
    state: str,
    value: bool = True,
    timeout: float | None = None,
    poll_interval: float = 0.1,
    operation_id: str = '',
) -> JsonObject:
    async def probe() -> JsonObject:
        async def evaluate() -> bool:
            result = await element_get_state(client_id, tab_id, element_id)
            state_obj = get_object(result, 'state', {})
            return state_obj.get(state) is value

        return await _poll(evaluate, timeout, poll_interval, f'element state {state}')

    return await _run(client_id, operation_id, probe())


async def network_wait_for_request(
    client_id: str,
    tab_id: str,
    url_pattern: str = '*',
    method: str = '',
    timeout: float | None = None,
    operation_id: str = '',
) -> JsonObject:
    return await _network_wait(client_id, tab_id, url_pattern, method, timeout, operation_id)


async def network_wait_for_response(
    client_id: str,
    tab_id: str,
    url_pattern: str = '*',
    status: int = 0,
    timeout: float | None = None,
    operation_id: str = '',
) -> JsonObject:
    return await _network_wait(client_id, tab_id, url_pattern, '', timeout, operation_id, status)


async def _network_wait(
    client_id: str,
    tab_id: str,
    pattern: str,
    method: str,
    timeout: float | None,
    operation_id: str,
    status: int = 0,
) -> JsonObject:
    async def probe() -> JsonObject:
        found: JsonObject = {}

        async def evaluate() -> bool:
            result = await network_list(client_id, tab_id, limit=1000)
            for event_value in get_array(result, 'events', []):
                event = require_json_object(event_value, 'network event')
                if (
                    fnmatch(get_string(event, 'url', ''), pattern)
                    and (not method or get_string(event, 'method', '') == method)
                    and (not status or get_int(event, 'status', 0) == status)
                ):
                    found.update(event)
                    return True
            return False

        result = await _poll(evaluate, timeout, 0.1, 'network event')
        result['event'] = found
        return result

    return await _run(client_id, operation_id, probe())


async def _poll(
    check: Callable[[], Awaitable[bool]],
    timeout: float | None,
    interval: float,
    label: str,
) -> JsonObject:
    limit = min(timeout or 15.0, get_timeout_config().max_timeout)

    async def wait() -> JsonObject:
        while True:
            if await check():
                return {'success': True, 'matched': True}
            await asyncio.sleep(max(0.02, min(interval, 5.0)))

    try:
        return await asyncio.wait_for(wait(), limit)
    except TimeoutError:
        return StructuredError(
            ErrorCode.TIMEOUT,
            f'Wait for {label} timed out after {limit}s',
            retryable=True,
        ).to_dict()


async def _run(client_id: str, operation_id: str, awaitable: Awaitable[JsonObject]) -> JsonObject:
    try:
        return await get_operation_manager().run(client_id, operation_id, awaitable)
    except StructuredError as exc:
        return exc.to_dict()
    except asyncio.CancelledError:
        return {'success': False, 'error_code': 'CANCELLED', 'message': 'Operation cancelled', 'retryable': True}


async def _url_match(url_awaitable: Awaitable[str], pattern: str, match: str) -> bool:
    url = await url_awaitable
    if match == 'exact':
        return url == pattern
    if match == 'regex':
        return re.search(pattern, url) is not None
    return bool(fnmatch(url, pattern))


__all__ = ['operation_cancel']
