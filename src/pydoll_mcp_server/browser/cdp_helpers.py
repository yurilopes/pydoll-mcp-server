"""CDP-backed helpers for user agent, viewport, and other browser settings."""

from __future__ import annotations

import contextlib
from typing import Any

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_value
from pydoll_mcp_server.errors import ErrorCode, StructuredError


async def set_user_agent(
    client_id: str,
    tab_id: str = '',
    browser_id: str = '',
    user_agent: str = '',
) -> dict[str, Any]:
    if not tab_id and not browser_id:
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message='Either tab_id or browser_id is required',
            retryable=False,
        ).to_dict()

    registry = get_registry()

    try:
        if tab_id:
            tab_info = registry.get_tab(client_id, tab_id)
            pydoll_tab = tab_info._pydoll_tab
            js = f"""
            Object.defineProperty(navigator, 'userAgent', {{
                get: function() {{ return {__import__('json').dumps(user_agent)}; }},
                configurable: true
            }});
            """
            with contextlib.suppress(Exception):
                await pydoll_tab.execute_script(js, return_by_value=True)
        elif browser_id:
            registry.get_pydoll_browser(client_id, browser_id)
            pass

        return {
            'success': True,
            'user_agent': user_agent,
        }
    except StructuredError as e:
        return e.to_dict()
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to set user agent: {e}',
            retryable=True,
        ).to_dict()


async def set_viewport(
    client_id: str,
    tab_id: str,
    width: int,
    height: int,
    scale: float = 1.0,
) -> dict[str, Any]:
    if width < 100 or width > 10000 or height < 100 or height > 10000:
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message=f'Invalid viewport size: {width}x{height}. Min 100, max 10000.',
            retryable=False,
        ).to_dict()

    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
        pydoll_tab = tab_info._pydoll_tab
    except StructuredError as e:
        return e.to_dict()

    try:
        js = f"""
        try {{
            window.resizeTo({width}, {height});
        }} catch(e) {{}}
        return {{width: window.innerWidth, height: window.innerHeight}};
        """
        result = await pydoll_tab.execute_script(js, return_by_value=True)
        value = extract_script_value(result) or {'width': width, 'height': height}

        return {
            'success': True,
            'viewport': value,
        }
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to set viewport: {e}',
            retryable=True,
        ).to_dict()
