"""Deep DOM traversal through same-origin iframes and open shadow roots."""

from __future__ import annotations

import asyncio
import json
import time

from pydoll.browser.tab import Tab
from pydoll.elements.shadow_root import ShadowRoot
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_object
from pydoll_mcp_server.config import get_limits_config, get_timeout_config
from pydoll_mcp_server.dom.deep_helpers import (
    cache_deep_nodes,
    ensure_web_elements,
    raw_from_pydoll_element,
)
from pydoll_mcp_server.dom.deep_scripts import DEEP_FIND_JS, DEEP_TREE_JS
from pydoll_mcp_server.dom.models import DeepRawElement, parse_deep_element
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_bool

QueryScope = Tab | WebElement | ShadowRoot


async def page_get_tree_deep(
    client_id: str,
    tab_id: str,
    max_depth: int = 10,
    max_nodes: int = 1000,
    timeout: float | None = None,
    include_shadow: bool = True,
    include_iframes: bool = True,
) -> JsonObject:
    config = get_timeout_config()
    timeout = timeout or config.deep_tree
    timeout = min(timeout, config.max_timeout)
    limits = get_limits_config()
    max_depth = min(max_depth, limits.max_deep_depth)
    max_nodes = min(max_nodes, limits.max_deep_nodes)
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab
    start = time.time()
    errors: list[JsonObject] = []
    partial = False

    try:
        script = (
            DEEP_TREE_JS.replace('__MAX_DEPTH__', str(max_depth))
            .replace('__MAX_NODES__', str(max_nodes))
            .replace('__INCLUDE_SHADOW__', 'true' if include_shadow else 'false')
            .replace('__INCLUDE_IFRAMES__', 'true' if include_iframes else 'false')
        )
        response = await asyncio.wait_for(
            pydoll_tab.execute_script(script, return_by_value=True),
            timeout=timeout,
        )
        raw = extract_script_object(response)
    except asyncio.TimeoutError:
        raw = {}
        partial = True
        errors.append(
            {
                'path': 'root',
                'error': f'Deep traversal timed out after {timeout}s',
            }
        )
    except Exception as exc:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Deep traversal failed: {exc}',
            retryable=True,
        ).to_dict()

    raw_elements = [parse_deep_element(item) for item in get_array(raw, 'elements', [])]
    raw_frames = get_array(raw, 'frames', [])
    try:
        await collect_iframe_scope(
            scope=pydoll_tab,
            tab_info=tab_info,
            frame_path=[],
            depth=0,
            max_depth=max_depth,
            remaining=max_nodes - len(raw_elements),
            raw_elements=raw_elements,
            frames=raw_frames,
            errors=errors,
        )
    except Exception as exc:
        partial = True
        errors.append({'path': 'iframes', 'error': str(exc)})

    elements = cache_deep_nodes(tab_info, raw_elements)
    errors.extend(_error_objects(get_array(raw, 'errors', [])))
    partial = partial or get_bool(raw, 'partial')
    duration_ms = (time.time() - start) * 1000
    element_values: JsonArray = list(elements)
    error_values: JsonArray = list(errors)

    return {
        'success': True,
        'frames': raw_frames,
        'shadow_roots': get_array(raw, 'shadow_roots', []),
        'elements': element_values,
        'partial': partial,
        'errors': error_values,
        'timing_ms': round(duration_ms, 1),
    }


async def element_find_deep(
    client_id: str,
    tab_id: str,
    selector: str,
    strategy: str = 'css',
    timeout: float | None = None,
) -> JsonObject:
    if strategy not in ('css', 'xpath'):
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message=f'Unknown strategy: {strategy}. Use css or xpath.',
            retryable=False,
        ).to_dict()

    config = get_timeout_config()
    timeout = timeout or config.deep_tree
    timeout = min(timeout, config.max_timeout)
    limits = get_limits_config()
    max_depth = limits.max_deep_depth
    max_nodes = limits.max_deep_nodes
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab

    iframe_matches: list[DeepRawElement] = []
    iframe_errors: list[JsonObject] = []
    try:
        await find_in_iframe_scopes(
            scope=pydoll_tab,
            selector=selector,
            strategy=strategy,
            tab_info=tab_info,
            frame_path=[],
            depth=0,
            max_depth=max_depth,
            remaining=max_nodes,
            matches=iframe_matches,
            errors=iframe_errors,
        )
    except Exception as exc:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Deep iframe search failed: {exc}',
            retryable=True,
        ).to_dict()

    try:
        script = (
            DEEP_FIND_JS.replace('__SELECTOR__', json.dumps(selector))
            .replace('__STRATEGY__', json.dumps(strategy))
            .replace('__MAX_DEPTH__', str(max_depth))
            .replace('__MAX_NODES__', str(max_nodes))
            .replace('__INCLUDE_SHADOW__', 'true')
            .replace('__INCLUDE_IFRAMES__', 'true')
        )
        response = await asyncio.wait_for(
            pydoll_tab.execute_script(script, return_by_value=True),
            timeout=timeout,
        )
        raw = extract_script_object(response)
    except asyncio.TimeoutError:
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message=f'Deep find timed out after {timeout}s',
            retryable=True,
        ).to_dict()
    except Exception as exc:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Deep find failed: {exc}',
            retryable=True,
        ).to_dict()

    raw_elements = iframe_matches + [parse_deep_element(item) for item in get_array(raw, 'elements', [])]
    matches = cache_deep_nodes(tab_info, raw_elements)
    if not matches:
        return StructuredError(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message=f'No element found for selector: {selector} (deep search)',
            retryable=False,
        ).to_dict()

    match_values: JsonArray = list(matches)
    all_errors: JsonArray = [*iframe_errors, *get_array(raw, 'errors', [])]
    return {
        'success': True,
        'selector': selector,
        'strategy': strategy,
        'found': len(matches),
        'elements': match_values,
        'partial': bool(iframe_errors) or get_bool(raw, 'partial'),
        'errors': all_errors,
    }


async def collect_iframe_scope(
    scope: QueryScope,
    tab_info: TabInfo,
    frame_path: list[str],
    depth: int,
    max_depth: int,
    remaining: int,
    raw_elements: list[DeepRawElement],
    frames: JsonArray,
    errors: list[JsonObject],
) -> None:
    if depth >= max_depth or remaining <= 0:
        return

    frame_elements = await query_frame_elements(scope)
    for frame_el in frame_elements:
        if remaining <= 0:
            return
        frame_raw = await raw_from_pydoll_element(frame_el, frame_path, [])
        raw_elements.append(frame_raw)
        remaining -= 1
        frame_ref = frame_raw['selector_hint'] or frame_raw['element_id']
        next_frame_path = [*frame_path, str(frame_ref)]
        frames.append(
            {
                'element_id': frame_raw['element_id'],
                'selector_hint': frame_raw['selector_hint'],
                'frame_path': list(frame_path),
                'target_frame_path': list(next_frame_path),
                'src': frame_raw['attrs'].get('src', ''),
            }
        )

        try:
            child_elements = await frame_el.query(
                '*',
                timeout=0,
                find_all=True,
                raise_exc=False,
            )
            for child in ensure_web_elements(child_elements):
                if remaining <= 0:
                    return
                raw_elements.append(await raw_from_pydoll_element(child, next_frame_path, []))
                remaining -= 1
            await collect_iframe_scope(
                scope=frame_el,
                tab_info=tab_info,
                frame_path=next_frame_path,
                depth=depth + 1,
                max_depth=max_depth,
                remaining=remaining,
                raw_elements=raw_elements,
                frames=frames,
                errors=errors,
            )
        except (PydollException, TypeError, ValueError) as exc:
            errors.append(
                {
                    'path': ' > '.join(next_frame_path),
                    'error': str(exc),
                }
            )


async def find_in_iframe_scopes(
    scope: QueryScope,
    selector: str,
    strategy: str,
    tab_info: TabInfo,
    frame_path: list[str],
    depth: int,
    max_depth: int,
    remaining: int,
    matches: list[DeepRawElement],
    errors: list[JsonObject] | None = None,
) -> None:
    if depth >= max_depth or remaining <= 0:
        return

    frame_elements = await query_frame_elements(scope)
    for frame_el in frame_elements:
        frame_raw = await raw_from_pydoll_element(frame_el, frame_path, [])
        frame_ref = frame_raw['selector_hint'] or frame_raw['element_id']
        next_frame_path = [*frame_path, str(frame_ref)]
        try:
            found = await frame_el.query(
                selector,
                timeout=0 if strategy == 'css' else 1,
                find_all=True,
                raise_exc=False,
            )
            for element in ensure_web_elements(found):
                if len(matches) >= remaining:
                    return
                matches.append(await raw_from_pydoll_element(element, next_frame_path, []))
            await find_in_iframe_scopes(
                scope=frame_el,
                selector=selector,
                strategy=strategy,
                tab_info=tab_info,
                frame_path=next_frame_path,
                depth=depth + 1,
                max_depth=max_depth,
                remaining=remaining,
                matches=matches,
                errors=errors,
            )
        except (PydollException, TypeError, ValueError) as exc:
            if errors is not None:
                errors.append({'path': ' > '.join(next_frame_path), 'error': str(exc)})


async def query_frame_elements(scope: QueryScope) -> list[WebElement]:
    elements: list[WebElement] = []
    for selector in ('iframe', 'frame'):
        try:
            result = await scope.query(
                selector,
                timeout=0,
                find_all=True,
                raise_exc=False,
            )
            elements.extend(ensure_web_elements(result))
        except (PydollException, TypeError, ValueError):
            # A frame type may be unsupported by the current Chromium target.
            continue
    return elements


def _error_objects(values: JsonArray) -> list[JsonObject]:
    return [value for value in values if isinstance(value, dict)]
