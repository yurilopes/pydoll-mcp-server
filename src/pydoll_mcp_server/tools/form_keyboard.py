from __future__ import annotations

import asyncio

from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError
from pydoll_mcp_server.json_types import JsonObject, get_bool, get_string
from pydoll_mcp_server.security.site_signals import inspect_element_security
from pydoll_mcp_server.tools.element_resolver import resolve_element
from pydoll_mcp_server.tools.form_element_references import read_filled_state_via_page_reference
from pydoll_mcp_server.tools.form_input_modes import (
    keyboard_fallback_decision,
    read_filled_state,
)


async def safe_keyboard_target(
    tab_info: TabInfo,
    element_id: str,
    original: WebElement,
) -> tuple[WebElement | None, str]:
    """Re-resolve a field before keyboard fallback and re-check its safety."""

    try:
        refreshed = await resolve_element(tab_info, element_id)
        target = refreshed or original
        if await inspect_element_security(target):
            return None, 'security_control'
        decision = await keyboard_fallback_decision(target)
        if get_bool(decision, 'allowed', False):
            return target, 'allowed'
        return None, get_string(decision, 'reason', 'inspection_unavailable')
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        return None, 'inspection_unavailable'


async def read_keyboard_state(
    tab_info: TabInfo,
    element_id: str,
    fallback: WebElement,
) -> JsonObject:
    """Read the replacement node after a controlled input may have rerendered."""

    await asyncio.sleep(0.12)
    referenced = await read_filled_state_via_page_reference(tab_info, element_id)
    if referenced is not None and not get_string(referenced, 'error', ''):
        return referenced
    observed = await resolve_element(tab_info, element_id) or fallback
    return await read_filled_state(observed)
