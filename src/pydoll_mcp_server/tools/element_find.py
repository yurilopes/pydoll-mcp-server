"""Element lookup with cached semantic references."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.config import get_timeout_config
from pydoll_mcp_server.dom.element_cache import get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_bool, get_string
from pydoll_mcp_server.logging import get_logger
from pydoll_mcp_server.tools.element_resolver import (
    cache_element_with_reference,
    safe_is_visible,
    safe_text,
)


async def element_find(
    client_id: str,
    tab_id: str,
    selector: str,
    strategy: Annotated[
        str,
        Field(
            description='Selector strategy: css, xpath, or text.',
            json_schema_extra={'enum': ['css', 'xpath', 'text']},
        ),
    ] = 'css',
    timeout: float | None = None,
    find_all: bool = False,
) -> JsonObject:
    """Find elements with CSS, XPath, or visible text and return short-lived references."""

    config = get_timeout_config()
    timeout = min(timeout or config.wait_selector, config.max_timeout)
    registry = get_registry()
    get_logger()
    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    try:
        if strategy == 'text':
            from pydoll_mcp_server.tools.text_ranking import element_find_by_text_candidates

            ranked = await element_find_by_text_candidates(
                client_id=client_id,
                tab_id=tab_id,
                text=selector,
                exact=True,
                max_candidates=100 if find_all else 20,
            )
            if not ranked.get('success'):
                return ranked
            candidates = ranked.get('candidates')
            ambiguous = bool(ranked.get('ambiguous'))
            if not isinstance(candidates, list) or not candidates:
                deep_candidates = await _find_text_in_deep_surface(client_id, tab_id, selector)
                if deep_candidates:
                    candidates = deep_candidates
                    ambiguous = len(deep_candidates) > 1
            if not isinstance(candidates, list) or not candidates:
                return StructuredError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    f'No visible element found for text: {selector}',
                    details={'selector': selector, 'strategy': strategy},
                ).to_dict()
            if not find_all and ambiguous:
                return StructuredError(
                    ErrorCode.AMBIGUOUS_ELEMENT,
                    f'Multiple visible elements matched text: {selector}',
                    details={'candidates': candidates},
                    retryable=False,
                ).to_dict()
            if find_all:
                return {'success': True, 'found': len(candidates), 'elements': candidates}
            first_value = candidates[0]
            if not isinstance(first_value, dict):
                return StructuredError(
                    ErrorCode.EXECUTION_ERROR,
                    'Text ranking returned a malformed candidate.',
                    retryable=False,
                ).to_dict()
            first = first_value
            return {
                'success': True,
                'element_id': str(first.get('element_id', '')),
                'tag': str(first.get('tag', '')),
                'text': str(first.get('text', '')),
                'visible': bool(first.get('visible', False)),
                'score': first.get('score', 0),
            }
        if strategy not in {'css', 'xpath'}:
            return StructuredError(
                ErrorCode.INVALID_INPUT,
                f'Unknown strategy: {strategy}. Use css, xpath, or text.',
            ).to_dict()
        elements = await tab_info.pydoll_tab.query(
            selector,
            timeout=max(0, int(timeout)),
            find_all=find_all,
            raise_exc=False,
        )
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Element find error: {exc}', retryable=True).to_dict()

    if elements is None:
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f'No element found for selector: {selector}',
            details={'selector': selector, 'strategy': strategy},
        ).to_dict()

    cache = get_element_cache()
    if find_all and isinstance(elements, list):
        results: list[JsonObject] = []
        for index, element in enumerate(elements):
            element_id = await cache_element_with_reference(
                cache,
                tab_info,
                element,
                fallback_selector=selector,
                match_index=index,
            )
            results.append(
                {
                    'element_id': element_id,
                    'tag': element.tag_name,
                    'text': (await safe_text(element))[:100],
                    'visible': await safe_is_visible(element),
                }
            )
        result_values: JsonArray = list(results)
        return {'success': True, 'found': len(results), 'elements': result_values}

    element = elements[0] if isinstance(elements, list) else elements
    element_id = await cache_element_with_reference(cache, tab_info, element, fallback_selector=selector)
    return {
        'success': True,
        'element_id': element_id,
        'tag': element.tag_name,
        'text': (await safe_text(element))[:100],
        'visible': await safe_is_visible(element),
    }


async def _find_text_in_deep_surface(client_id: str, tab_id: str, text: str) -> JsonArray:
    from pydoll_mcp_server.dom.deep_traversal import page_get_tree_deep

    deep = await page_get_tree_deep(
        client_id,
        tab_id,
        max_nodes=1000,
        timeout=5.0,
        include_shadow=True,
        include_iframes=False,
    )
    if not deep.get('success'):
        return []
    wanted = ' '.join(text.casefold().split())
    matches: JsonArray = []
    for item in get_array(deep, 'elements', []):
        if not isinstance(item, dict) or not get_bool(item, 'visible', False):
            continue
        values = [get_string(item, key, '').casefold() for key in ('label', 'text', 'name')]
        normalized = ' '.join(' '.join(value.split()) for value in values if value).strip()
        if normalized == wanted or wanted in normalized:
            matches.append(item)
    return matches


__all__ = ['element_find']
