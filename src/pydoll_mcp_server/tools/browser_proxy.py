"""Read-only browser proxy diagnostics."""

from __future__ import annotations

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import StructuredError
from pydoll_mcp_server.json_types import JsonObject


async def proxy_get(client_id: str, browser_id: str) -> JsonObject:
    try:
        browser = get_registry().get_browser(client_id, browser_id)
    except StructuredError as exc:
        return exc.to_dict()
    return {
        'success': True,
        'browser_id': browser_id,
        'proxy_enabled': bool(browser.proxy_server),
        'proxy_server': browser.proxy_server,
        'proxy_scheme': browser.proxy_scheme,
        'proxy_has_credentials': browser.proxy_has_credentials,
        'proxy_bypass_list': browser.proxy_bypass_list,
    }
