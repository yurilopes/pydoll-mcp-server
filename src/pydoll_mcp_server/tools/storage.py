"""Cookie and storage tools with redaction."""

from __future__ import annotations

import json
from typing import Any

from pydoll_mcp_server.browser.locks import browser_operation_lock, tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_value
from pydoll_mcp_server.errors import ErrorCode, StructuredError


async def cookies_get(
    client_id: str,
    browser_id: str = '',
    tab_id: str = '',
    url_filter: str = '',
    redact_values: bool = True,
) -> dict[str, Any]:
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
            pydoll_tab = tab_info._pydoll_tab
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

    cookies = []
    for c in (raw_cookies or []):
        entry = {
            'name': c.get('name', '') if isinstance(c, dict) else getattr(c, 'name', ''),
            'domain': c.get('domain', '') if isinstance(c, dict) else getattr(c, 'domain', ''),
            'path': c.get('path', '/') if isinstance(c, dict) else getattr(c, 'path', '/'),
            'value': '[REDACTED]' if redact_values else (
                c.get('value', '') if isinstance(c, dict) else getattr(c, 'value', '')
            ),
            'http_only': c.get('httpOnly', False) if isinstance(c, dict) else getattr(c, 'httpOnly', False),
            'secure': c.get('secure', False) if isinstance(c, dict) else getattr(c, 'secure', False),
        }
        if url_filter and url_filter not in entry.get('domain', ''):
            continue
        cookies.append(entry)

    return {
        'success': True,
        'cookies': cookies,
        'count': len(cookies),
        'redacted': redact_values,
    }


async def cookies_set(
    client_id: str,
    browser_id: str = '',
    tab_id: str = '',
    cookies: list[dict] | None = None,
) -> dict[str, Any]:
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
                pydoll_tab = tab_info._pydoll_tab
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
        'domains': list({c.get('domain', '') for c in cookies if isinstance(c, dict)}),
    }


async def storage_get(
    client_id: str,
    tab_id: str,
    origin: str = '',
    keys: list[str] | None = None,
    redact_values: bool = True,
) -> dict[str, Any]:
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info._pydoll_tab

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
        raw = extract_script_value(result) or {}
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get storage: {e}',
            retryable=True,
        ).to_dict()

    if redact_values and isinstance(raw, dict):
        for storage_type in ('local', 'session'):
            if storage_type in raw and isinstance(raw[storage_type], dict):
                raw[storage_type] = dict.fromkeys(raw[storage_type], '[REDACTED]')

    return {
        'success': True,
        'storage': raw,
        'redacted': redact_values,
    }


async def storage_set(
    client_id: str,
    tab_id: str,
    origin: str = '',
    items: list[dict] | None = None,
) -> dict[str, Any]:
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

    pydoll_tab = tab_info._pydoll_tab

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
            raw_count = extract_script_value(result)
            count = int(raw_count) if isinstance(raw_count, int | float) else len(items)
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
