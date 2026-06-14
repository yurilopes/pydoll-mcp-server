"""Tab recovery and health checking."""

from __future__ import annotations

import asyncio
from typing import Any

from pydoll_mcp_server.browser.models import ResourceHealth
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_value
from pydoll_mcp_server.errors import StructuredError
from pydoll_mcp_server.server_state import get_server_state

HEALTH_CHECK_JS = 'return {url: location.href, title: document.title, readyState: document.readyState};'


async def check_tab_health(client_id: str, tab_id: str) -> dict[str, Any]:
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return {'healthy': False, 'state': 'closed', 'error': str(e.message)}

    pydoll_tab = tab_info._pydoll_tab

    try:
        result = await asyncio.wait_for(
            pydoll_tab.execute_script(HEALTH_CHECK_JS, return_by_value=True),
            timeout=5.0,
        )
        raw = extract_script_value(result) or {}
        if isinstance(raw, str):
            import json
            raw = json.loads(raw)

        tab_info.url = raw.get('url', tab_info.url)
        tab_info.title = raw.get('title', tab_info.title)
        tab_info.health = ResourceHealth.HEALTHY

        return {
            'healthy': True,
            'state': 'healthy',
            'url': tab_info.url,
            'title': tab_info.title,
            'ready_state': raw.get('readyState', 'unknown'),
        }
    except asyncio.TimeoutError:
        tab_info.health = ResourceHealth.DEGRADED
        get_server_state().record_unhealthy_tab()
        return {
            'healthy': False,
            'state': 'degraded',
            'error': 'Health check timed out',
        }
    except Exception as e:
        tab_info.health = ResourceHealth.UNHEALTHY
        get_server_state().record_unhealthy_tab()
        return {
            'healthy': False,
            'state': 'unhealthy',
            'error': str(e),
        }


async def check_browser_health(client_id: str, browser_id: str) -> dict[str, Any]:
    registry = get_registry()

    try:
        browser_info = registry.get_browser(client_id, browser_id)
    except StructuredError as e:
        return {'healthy': False, 'state': 'closed', 'error': str(e.message)}

    pydoll_browser = browser_info._pydoll_browser

    try:
        version = await asyncio.wait_for(
            pydoll_browser.get_version(),
            timeout=5.0,
        )
        browser_info.health = ResourceHealth.HEALTHY
        return {
            'healthy': True,
            'state': 'healthy',
            'version': version if isinstance(version, dict) else str(version),
        }
    except asyncio.TimeoutError:
        browser_info.health = ResourceHealth.DEGRADED
        return {'healthy': False, 'state': 'degraded', 'error': 'Health check timed out'}
    except Exception as e:
        browser_info.health = ResourceHealth.UNHEALTHY
        return {'healthy': False, 'state': 'unhealthy', 'error': str(e)}
