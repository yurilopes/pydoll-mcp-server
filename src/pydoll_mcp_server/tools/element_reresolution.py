"""Stale element re-resolution tools."""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, cache_observed_element, get_element_cache
from pydoll_mcp_server.dom.reference_scripts import reference_metadata_script
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    InvalidJsonValueError,
    JsonArray,
    JsonObject,
    fold_visible_text,
    get_string,
    require_json_object,
)
from pydoll_mcp_server.tools.element_resolver import QueryScope


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
    match_index: Annotated[
        int | None, Field(description='Optional occurrence index among repeated selector matches.')
    ] = None,
    max_candidates: Annotated[int, Field(description='Maximum candidates returned when recovery is ambiguous.')] = 5,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    cache = get_element_cache()
    old_entry = cache.get_for_tab(element_id, tab_info.tab_id)

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
    candidate_elements: list[WebElement] = []
    safe_max = max(1, min(max_candidates, 20))
    scope: QueryScope = tab_info.pydoll_tab
    if within_element_id:
        container_entry = cache.get_for_tab(within_element_id, tab_info.tab_id)
        if container_entry and container_entry.selector_hint:
            container = await tab_info.pydoll_tab.query(
                container_entry.selector_hint,
                timeout=2,
                find_all=False,
                raise_exc=False,
            )
            if container is not None:
                scope = container

    if hint_selector:
        try:
            elements = await scope.query(
                hint_selector,
                timeout=3,
                find_all=True,
                raise_exc=False,
            )
            if elements:
                for el in elements[:safe_max]:
                    candidate_elements.append(el)
                    candidates.append(await _describe_element(el))
        except PydollException:
            pass

    if hint_xpath and len(candidates) == 0:
        try:
            elements = await scope.query(
                hint_xpath,
                timeout=3,
                find_all=True,
                raise_exc=False,
            )
            if elements:
                for el in elements[:safe_max]:
                    candidate_elements.append(el)
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

    old_index = old_entry.match_index if old_entry and old_entry.match_index > 0 else None
    preferred_index = match_index if match_index is not None else old_index
    if len(candidates) > 1 and preferred_index is not None:
        indexed: list[int] = []
        for position, candidate_value in enumerate(candidates):
            candidate = require_json_object(candidate_value, 'resolution candidate')
            candidate_index = candidate.get('match_index')
            if (
                isinstance(candidate_index, int)
                and not isinstance(candidate_index, bool)
                and candidate_index == preferred_index
            ):
                indexed.append(position)
        if len(indexed) == 1:
            candidates = [candidates[indexed[0]]]
            candidate_elements = [candidate_elements[indexed[0]]]

    fingerprint_matches = [
        position
        for position, candidate_value in enumerate(candidates)
        if old_entry is not None
        and _fingerprint_matches(old_entry, require_json_object(candidate_value, 'resolution candidate'))
    ]
    if len(candidates) > 1 and len(fingerprint_matches) == 1:
        selected = fingerprint_matches[0]
        candidates = [candidates[selected]]
        candidate_elements = [candidate_elements[selected]]

    if len(candidates) > 1:
        ambiguous = StructuredError(
            ErrorCode.AMBIGUOUS_ELEMENT,
            f'Multiple candidates found when re-resolving {element_id}.',
            retryable=True,
            details={
                'candidates': candidates,
                'candidate_count': len(candidates),
                'selector_hint': hint_selector,
                'xpath_hint': hint_xpath,
                'fingerprint_match': bool(fingerprint_matches),
            },
            recovery_hint='Use selector_hint, xpath_hint, or match_index to identify the single correct element.',
        ).to_dict()
        ambiguous['resolved_again'] = False
        return ambiguous

    new_element = require_json_object(candidates[0], 'resolved candidate')
    new_id = f'el_resolved_{element_id}'
    new_element['element_id'] = new_id
    cache_observed_element(
        cache,
        tab_id,
        tab_info.document_generation,
        new_element,
        pydoll_element=candidate_elements[0],
    )

    return {
        'success': True,
        'resolved': True,
        'old_element_id': element_id,
        'element_id': new_id,
        'candidate': new_element,
        'strategy_used': (
            'fingerprint_match'
            if old_entry and _fingerprint_matches(old_entry, new_element)
            else ('selector_hint' if hint_selector else 'xpath_hint')
        ),
        'fingerprint_match': bool(old_entry and _fingerprint_matches(old_entry, new_element)),
        'candidate_count': len(candidates),
        'resolved_again': True,
        'warnings': [],
    }


async def _describe_element(element: WebElement) -> JsonObject:
    try:
        tag = element.tag_name or ''
        result = await element.execute_script(
            reference_metadata_script().replace(
                'return elementReference(this);',
                'const reference=elementReference(this);'
                'const r=this.getBoundingClientRect();'
                "return {...reference,text:this.innerText||this.textContent||'',"
                'tag:this.tagName.toLowerCase(),enabled:!this.disabled};',
            ),
            return_by_value=True,
        )
        data = extract_script_object(result)
        return {
            'tag': tag,
            'text': get_string(data, 'text', '')[:100],
            'role': get_string(data, 'role', ''),
            'enabled': bool(data.get('enabled', False)),
            'selector_hint': get_string(data, 'selector_hint', ''),
            'xpath_hint': get_string(data, 'xpath_hint', ''),
            'match_index': data.get('match_index', 0),
            'label': get_string(data, 'label', ''),
            'fingerprint': data.get('fingerprint', {}),
        }
    except (PydollException, InvalidScriptResponseError):
        return {'tag': '', 'text': '', 'role': '', 'enabled': False}


def _fingerprint_matches(old_entry: ElementCacheEntry, candidate: JsonObject) -> bool:
    old_tag = old_entry.tag_name.lower()
    new_tag = get_string(candidate, 'tag', '').lower()
    old_text = fold_visible_text(old_entry.text_summary).strip()
    new_text = fold_visible_text(get_string(candidate, 'text', '')).strip()
    if old_tag != new_tag:
        return False
    if old_text and old_text != new_text:
        return False
    try:
        old_fingerprint = require_json_object(json.loads(old_entry.fingerprint), 'cached fingerprint')
        new_fingerprint = require_json_object(candidate.get('fingerprint', {}), 'candidate fingerprint')
    except (InvalidJsonValueError, json.JSONDecodeError):
        return not old_text or old_text == new_text
    for key in ('role', 'label', 'name', 'type'):
        old_value = fold_visible_text(str(old_fingerprint.get(key, '')))
        new_value = fold_visible_text(str(new_fingerprint.get(key, '')))
        if old_value and old_value != new_value:
            return False
    return True
