from __future__ import annotations

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.script_utils import extract_normalized_object
from pydoll_mcp_server.dom.element_cache import get_element_cache
from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.tools.form_scripts import (
    fill_reference_script,
    read_filled_state_reference_script,
)


def page_reference(tab_info: TabInfo, element_id: str) -> str:
    """Return a safe same-document reference for a cached field."""

    entry = get_element_cache().get_for_tab(element_id, tab_info.tab_id)
    if entry is None or entry.frame_path or entry.shadow_path:
        return ''
    return entry.xpath_hint or entry.selector_hint


async def fill_via_page_reference(tab_info: TabInfo, element_id: str, payload: str) -> JsonObject | None:
    reference = page_reference(tab_info, element_id)
    if not reference:
        return None
    response = await tab_info.pydoll_tab.execute_script(fill_reference_script(reference, payload), return_by_value=True)
    return extract_normalized_object(response, 'form_fill')


async def read_filled_state_via_page_reference(tab_info: TabInfo, element_id: str) -> JsonObject | None:
    reference = page_reference(tab_info, element_id)
    if not reference:
        return None
    response = await tab_info.pydoll_tab.execute_script(
        read_filled_state_reference_script(reference), return_by_value=True
    )
    return extract_normalized_object(response, 'read_filled_state')
