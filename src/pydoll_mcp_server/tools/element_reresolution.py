"""Stale element re-resolution tools."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_string, require_json_object


async def element_resolve_again(
    client_id: str,
    tab_id: str,
    element_id: Annotated[str, Field(description='Stale or previously cached element_id to recover.')],
    selector_hint: Annotated[str, Field(description='Optional CSS selector hint from the previous resolution.')] = '',
    xpath_hint: Annotated[str, Field(description='Optional XPath hint from the previous resolution.')] = '',
    text: Annotated[str, Field(description='Optional visible text fallback for resolution.')] = '',
    role: Annotated[str, Field(description='Optional ARIA role filter for the text fallback.')] = '',
    within_element_id: Annotated[
        str,
        Field(description='Optional cached container element_id that limits the recovery search.'),
    ] = '',
    max_candidates: Annotated[int, Field(description='Maximum candidates returned when recovery is ambiguous.')] = 5,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    cache = get_element_cache()
    old_entry = cache.get_valid(element_id, tab_info.tab_id, tab_info.document_generation)

    hint_selector = selector_hint or (old_entry.selector_hint if old_entry else '')
    hint_xpath = xpath_hint or (old_entry.xpath_hint if old_entry else '')

    if not hint_selector and not hint_xpath and not text:
        return StructuredError(
            ErrorCode.STALE_ELEMENT,
            f'Element {element_id} is stale and no resolution hints are available.',
            retryable=False,
            recovery_hint='Use element_find or page_get_tree to find the element again.',
        ).to_dict()

    candidates: JsonArray = []
    safe_max = max(1, min(max_candidates, 20))

    if hint_selector:
        try:
            elements = await tab_info.pydoll_tab.query(
                hint_selector,
                timeout=3,
                find_all=True,
                raise_exc=False,
            )
            if elements:
                for el in elements[:safe_max]:
                    candidates.append(await _describe_element(el))
        except PydollException:
            pass

    if hint_xpath and len(candidates) == 0:
        try:
            elements = await tab_info.pydoll_tab.query(
                hint_xpath,
                timeout=3,
                find_all=True,
                raise_exc=False,
            )
            if elements:
                for el in elements[:safe_max]:
                    candidates.append(await _describe_element(el))
        except PydollException:
            pass

    if len(candidates) == 0:
        return StructuredError(
            ErrorCode.STALE_ELEMENT,
            f'Element {element_id} could not be re-resolved.',
            retryable=False,
            recovery_hint='The element has been removed from the DOM.',
        ).to_dict()

    if len(candidates) > 1:
        return StructuredError(
            ErrorCode.AMBIGUOUS_ELEMENT,
            f'Multiple candidates found when re-resolving {element_id}.',
            retryable=True,
            details={'candidates': candidates},
            recovery_hint='Use selector_hint or xpath_hint to identify the single correct element.',
        ).to_dict()

    new_element = require_json_object(candidates[0], 'resolved candidate')
    new_id = f'el_resolved_{element_id}'
    cache.store(
        ElementCacheEntry(
            element_id=new_id,
            tab_id=tab_id,
            document_generation=tab_info.document_generation,
            tag_name=get_string(new_element, 'tag', ''),
            text_summary=get_string(new_element, 'text', '')[:100],
            selector_hint=hint_selector,
            xpath_hint=hint_xpath,
        )
    )

    return {
        'success': True,
        'resolved': True,
        'old_element_id': element_id,
        'element_id': new_id,
        'candidate': new_element,
        'strategy_used': 'selector_hint' if hint_selector else 'xpath_hint',
        'warnings': [],
    }


async def _describe_element(element: WebElement) -> JsonObject:
    try:
        tag = element.tag_name or ''
        result = await element.execute_script(
            'const r=this.getBoundingClientRect();'
            "return {text:this.innerText||this.textContent||'',"
            "role:this.getAttribute('role')||'',enabled:!this.disabled};",
            return_by_value=True,
        )
        data = extract_script_object(result)
        return {
            'tag': tag,
            'text': get_string(data, 'text', '')[:100],
            'role': get_string(data, 'role', ''),
            'enabled': bool(data.get('enabled', False)),
        }
    except (PydollException, InvalidScriptResponseError):
        return {'tag': '', 'text': '', 'role': '', 'enabled': False}
