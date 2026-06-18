"""Nonblocking waits and operation cancellation."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from fnmatch import fnmatch

from pydoll_mcp_server.browser.inspection import get_inspection_manager
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
from pydoll_mcp_server.tools.javascript import scan_script
from pydoll_mcp_server.tools.network import network_list


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


async def page_wait_for_text(
    client_id: str,
    tab_id: str,
    text: str,
    exact: bool = False,
    timeout: float | None = None,
    poll_interval: float = 0.1,
    operation_id: str = '',
) -> JsonObject:
    return await _text_wait(client_id, tab_id, text, exact, False, timeout, poll_interval, operation_id)


async def page_wait_text_gone(
    client_id: str,
    tab_id: str,
    text: str,
    exact: bool = False,
    timeout: float | None = None,
    poll_interval: float = 0.1,
    operation_id: str = '',
) -> JsonObject:
    return await _text_wait(client_id, tab_id, text, exact, True, timeout, poll_interval, operation_id)


async def page_wait_for_selector(
    client_id: str,
    tab_id: str,
    selector: str,
    strategy: str = 'css',
    visible: bool = True,
    timeout: float | None = None,
    poll_interval: float = 0.1,
    operation_id: str = '',
) -> JsonObject:
    async def probe() -> JsonObject:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab

        async def evaluate() -> bool:
            script = _selector_script(selector, strategy, visible)
            return bool(extract_script_value(await tab.execute_script(script, return_by_value=True)))

        return await _poll(evaluate, timeout, poll_interval, f'selector {selector}')

    return await _run(client_id, operation_id, probe())


async def page_wait_for_network_idle(
    client_id: str,
    tab_id: str,
    idle_ms: int = 500,
    timeout: float | None = None,
    poll_interval: float = 0.1,
    operation_id: str = '',
) -> JsonObject:
    async def probe() -> JsonObject:
        last_count = -1
        stable_since = 0.0

        async def evaluate() -> bool:
            nonlocal last_count, stable_since
            result = await network_list(client_id, tab_id, limit=1000)
            count = len(get_array(result, 'events', []))
            now = asyncio.get_running_loop().time()
            if count != last_count:
                last_count = count
                stable_since = now
                return False
            return (now - stable_since) * 1000 >= max(0, idle_ms)

        return await _poll(evaluate, timeout, poll_interval, 'network idle')

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
    resource_type: str = '',
    has_post_data: bool | None = None,
    timeout: float | None = None,
    operation_id: str = '',
) -> JsonObject:
    return await _network_wait(
        client_id,
        tab_id,
        url_pattern,
        method,
        timeout,
        operation_id,
        resource_type=resource_type,
        has_post_data=has_post_data,
    )


async def network_wait_for_response(
    client_id: str,
    tab_id: str,
    url_pattern: str = '*',
    status: int = 0,
    request_id: str = '',
    timeout: float | None = None,
    operation_id: str = '',
) -> JsonObject:
    return await _network_wait(client_id, tab_id, url_pattern, '', timeout, operation_id, status, request_id=request_id)


async def _network_wait(
    client_id: str,
    tab_id: str,
    pattern: str,
    method: str,
    timeout: float | None,
    operation_id: str,
    status: int = 0,
    request_id: str = '',
    resource_type: str = '',
    has_post_data: bool | None = None,
) -> JsonObject:
    async def probe() -> JsonObject:
        found: JsonObject = {}
        get_registry().get_tab(client_id, tab_id)
        state = get_inspection_manager().get(tab_id)
        initial_ids = set(state.requests)

        async def evaluate() -> bool:
            result = await network_list(client_id, tab_id, limit=1000)
            for event_value in get_array(result, 'events', []):
                event = require_json_object(event_value, 'network event')
                if (
                    (bool(request_id) or get_string(event, 'request_id') not in initial_ids)
                    and fnmatch(get_string(event, 'url', ''), pattern)
                    and (not method or get_string(event, 'method', '') == method)
                    and (not status or get_int(event, 'status', 0) == status)
                    and (not request_id or get_string(event, 'request_id') == request_id)
                    and (not resource_type or get_string(event, 'resource_type') == resource_type)
                    and (has_post_data is None or event.get('has_post_data') is has_post_data)
                ):
                    found.update(event)
                    return True
            return False

        result = await _poll(evaluate, timeout, 0.1, 'network event')
        result['event'] = found
        return result

    return await _run(client_id, operation_id, probe())


async def _text_wait(
    client_id: str,
    tab_id: str,
    text: str,
    exact: bool,
    gone: bool,
    timeout: float | None,
    poll_interval: float,
    operation_id: str,
) -> JsonObject:
    async def probe() -> JsonObject:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab

        async def evaluate() -> bool:
            escaped = text.replace('\\', '\\\\').replace("'", "\\'")
            script = (
                "const body=(document.body?document.body.innerText:document.documentElement.innerText)||'';"
                f"const text='{escaped}';"
                f'const found={str(exact).lower()} ? body.trim()===text : body.includes(text);'
                f'return {str(gone).lower()} ? !found : found;'
            )
            return bool(extract_script_value(await tab.execute_script(script, return_by_value=True)))

        label = f'text {text}' if not gone else f'text gone {text}'
        return await _poll(evaluate, timeout, poll_interval, label)

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
    if match == 'contains':
        return pattern in url
    if match == 'regex':
        return re.search(pattern, url) is not None
    return bool(fnmatch(url, pattern))


__all__ = ['operation_cancel']


def _selector_script(selector: str, strategy: str, visible: bool) -> str:
    escaped = selector.replace('\\', '\\\\').replace("'", "\\'")
    if strategy == 'xpath':
        lookup = (
            f"document.evaluate('{escaped}',document,null,XPathResult.FIRST_ORDERED_NODE_TYPE,null).singleNodeValue"
        )
    else:
        lookup = f"document.querySelector('{escaped}')"
    return f"""
    const el = {lookup};
    if (!el) return false;
    if (!{str(visible).lower()}) return true;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    """
