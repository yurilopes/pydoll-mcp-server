"""Tab recovery and health checking."""

from __future__ import annotations

import asyncio

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.models import ResourceHealth
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_object
from pydoll_mcp_server.errors import StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_string, normalize_json_value
from pydoll_mcp_server.server_state import get_server_state

HEALTH_CHECK_JS = 'return {url: location.href, title: document.title, readyState: document.readyState};'


async def check_tab_health(client_id: str, tab_id: str) -> JsonObject:
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return {'healthy': False, 'state': 'closed', 'error': str(e.message)}

    pydoll_tab = tab_info.pydoll_tab

    try:
        result = await asyncio.wait_for(
            pydoll_tab.execute_script(HEALTH_CHECK_JS, return_by_value=True),
            timeout=5.0,
        )
        raw = extract_script_object(result)

        tab_info.url = get_string(raw, 'url', tab_info.url)
        tab_info.title = get_string(raw, 'title', tab_info.title)
        tab_info.health = ResourceHealth.HEALTHY

        return {
            'healthy': True,
            'state': 'healthy',
            'url': tab_info.url,
            'title': tab_info.title,
            'ready_state': get_string(raw, 'readyState', 'unknown'),
        }
    except asyncio.TimeoutError:
        tab_info.health = ResourceHealth.DEGRADED
        get_server_state().record_unhealthy_tab()
        return {
            'healthy': False,
            'state': 'degraded',
            'error': 'Health check timed out',
        }
    except (PydollException, TypeError, ValueError) as e:
        tab_info.health = ResourceHealth.UNHEALTHY
        get_server_state().record_unhealthy_tab()
        return {
            'healthy': False,
            'state': 'unhealthy',
            'error': str(e),
        }


async def check_browser_health(client_id: str, browser_id: str) -> JsonObject:
    registry = get_registry()

    try:
        browser_info = registry.get_browser(client_id, browser_id)
    except StructuredError as e:
        return {'healthy': False, 'state': 'closed', 'error': str(e.message)}

    pydoll_browser = browser_info.pydoll_browser

    try:
        version = await asyncio.wait_for(
            pydoll_browser.get_version(),
            timeout=5.0,
        )
        browser_info.health = ResourceHealth.HEALTHY
        version_value = normalize_json_value(version, 'browser version')
        return {
            'healthy': True,
            'state': 'healthy',
            'version': version_value,
        }
    except asyncio.TimeoutError:
        browser_info.health = ResourceHealth.DEGRADED
        return {'healthy': False, 'state': 'degraded', 'error': 'Health check timed out'}
    except (PydollException, TypeError, ValueError) as e:
        browser_info.health = ResourceHealth.UNHEALTHY
        return {'healthy': False, 'state': 'unhealthy', 'error': str(e)}
