"""Server-wide browser cleanup shared by all transports."""

from __future__ import annotations

import asyncio

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.profile_leases import get_profile_lease_manager
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject


async def shutdown_browsers() -> JsonObject:
    """Close every browser owned by this server instance during shutdown."""

    from pydoll_mcp_server.tools.browser import browser_close

    registry = get_registry()
    results: list[JsonObject] = []
    failures: JsonArray = []
    try:
        for browser in list(registry.list_all_browsers()):
            try:
                result = await browser_close(browser.client_id, browser.browser_id)
            except (AttributeError, OSError, PydollException, RuntimeError, asyncio.TimeoutError) as exc:
                result = StructuredError(
                    ErrorCode.INTERNAL_ERROR,
                    f'Error closing browser {browser.browser_id}: {exc}',
                    retryable=True,
                ).to_dict()
            results.append(result)
            if result.get('success') is not True:
                failures.append(result)
    finally:
        get_profile_lease_manager().release_all()
    return {
        'success': not failures,
        'closed': len(results) - len(failures),
        'failed': len(failures),
        'failures': failures,
    }
