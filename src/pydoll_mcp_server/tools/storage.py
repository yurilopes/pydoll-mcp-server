"""Cookie and storage tools with redaction."""

from __future__ import annotations

import json

from pydoll.protocol.network.types import CookieParam
from typing_extensions import NotRequired, TypedDict

from pydoll_mcp_server.browser.locks import browser_operation_lock, tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_number, extract_script_object
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_object


class StorageSetItem(TypedDict):
    key: str
    value: str
    type: NotRequired[str]


async def cookies_get(
    client_id: str,
    browser_id: str = '',
    tab_id: str = '',
    url_filter: str = '',
    redact_values: bool = True,
) -> JsonObject:
    if not browser_id and not tab_id:
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message='Either browser_id or tab_id is required',
            retryable=False,
        ).to_dict()

    registry = get_registry()

    try:
        if tab_id:
            tab_info = registry.get_tab(client_id, tab_id)
            pydoll_tab = tab_info.pydoll_tab
            raw_cookies = await pydoll_tab.get_cookies()
        else:
            browser = registry.get_pydoll_browser(client_id, browser_id)
            raw_cookies = await browser.get_cookies()
    except StructuredError as e:
        return e.to_dict()
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get cookies: {e}',
            retryable=True,
        ).to_dict()

    cookies: list[JsonObject] = []
    for c in raw_cookies or []:
        entry: JsonObject = {
            'name': c['name'],
            'domain': c['domain'],
            'path': c['path'],
            'value': '[REDACTED]' if redact_values else c['value'],
            'http_only': c['httpOnly'],
            'secure': c['secure'],
        }
        if url_filter and url_filter not in c['domain']:
            continue
        cookies.append(entry)

    cookie_values: JsonArray = list(cookies)
    return {
        'success': True,
        'cookies': cookie_values,
        'count': len(cookies),
        'redacted': redact_values,
    }


async def cookies_set(
    client_id: str,
    browser_id: str = '',
    tab_id: str = '',
    cookies: list[CookieParam] | None = None,
) -> JsonObject:
    if not browser_id and not tab_id:
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message='Either browser_id or tab_id is required',
            retryable=False,
        ).to_dict()

    if not cookies:
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message='At least one cookie is required',
            retryable=False,
        ).to_dict()

    registry = get_registry()

    try:
        if tab_id:
            async with tab_operation_lock(tab_id):
                tab_info = registry.get_tab(client_id, tab_id)
                pydoll_tab = tab_info.pydoll_tab
                await pydoll_tab.set_cookies(cookies)
        else:
            async with browser_operation_lock(browser_id):
                browser = registry.get_pydoll_browser(client_id, browser_id)
                await browser.set_cookies(cookies)
    except StructuredError as e:
        return e.to_dict()
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to set cookies: {e}',
            retryable=True,
        ).to_dict()

    return {
        'success': True,
        'count': len(cookies),
        'domains': list({c.get('domain', '') for c in cookies}),
    }


async def storage_get(
    client_id: str,
    tab_id: str,
    origin: str = '',
    keys: list[str] | None = None,
    redact_values: bool = True,
) -> JsonObject:
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab

    try:
        js_keys = json.dumps(keys) if keys else 'null'
        js = f"""
        const result = {{local: {{}}, session: {{}}}};
        try {{
            const keys = {js_keys};
            if (keys) {{
                for (const k of keys) {{
                    const v = localStorage.getItem(k);
                    if (v !== null) result.local[k] = v;
                    const sv = sessionStorage.getItem(k);
                    if (sv !== null) result.session[k] = sv;
                }}
            }} else {{
                for (let i = 0; i < localStorage.length; i++) {{
                    const k = localStorage.key(i);
                    result.local[k] = localStorage.getItem(k);
                }}
                for (let i = 0; i < sessionStorage.length; i++) {{
                    const k = sessionStorage.key(i);
                    result.session[k] = sessionStorage.getItem(k);
                }}
            }}
        }} catch (e) {{ result.error = e.message; }}
        return result;
        """
        result = await pydoll_tab.execute_script(js, return_by_value=True)
        raw = extract_script_object(result)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get storage: {e}',
            retryable=True,
        ).to_dict()

    if redact_values:
        for storage_type in ('local', 'session'):
            values = get_object(raw, storage_type, {})
            raw[storage_type] = dict.fromkeys(values, '[REDACTED]')

    return {
        'success': True,
        'storage': raw,
        'redacted': redact_values,
    }


async def storage_set(
    client_id: str,
    tab_id: str,
    origin: str = '',
    items: list[StorageSetItem] | None = None,
) -> JsonObject:
    if not items:
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message='items list is required with key, value, and type fields',
            retryable=False,
        ).to_dict()

    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab

    js_items = json.dumps(items)
    js = f"""
    const items = {js_items};
    let count = 0;
    for (const item of items) {{
        const storage = item.type === 'session' ? sessionStorage : localStorage;
        storage.setItem(item.key, item.value);
        count++;
    }}
    return count;
    """
    try:
        async with tab_operation_lock(tab_id):
            result = await pydoll_tab.execute_script(js, return_by_value=True)
            count = int(extract_script_number(result))
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to set storage: {e}',
            retryable=True,
        ).to_dict()

    return {
        'success': True,
        'count': count,
    }
