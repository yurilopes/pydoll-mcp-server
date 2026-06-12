"""Element interaction tools: find, click, type, fill, get text/attribute."""

from __future__ import annotations

import json
from typing import Any

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.pydoll_compat import (
    get_element_attribute,
    get_element_text,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_value
from pydoll_mcp_server.config import get_config, get_limits_config, get_timeout_config
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.logging import get_logger
from pydoll_mcp_server.security.paths import validate_artifact_path
from pydoll_mcp_server.security.policy import is_sensitive_field


async def element_find(
    client_id: str,
    tab_id: str,
    selector: str,
    strategy: str = 'css',
    timeout: float | None = None,
    find_all: bool = False,
) -> dict[str, Any]:
    config = get_timeout_config()
    timeout = timeout or config.wait_selector
    timeout = min(timeout, config.max_timeout)
    registry = get_registry()
    get_logger()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info._pydoll_tab

    try:
        if strategy == 'css' or strategy == 'xpath':
            elements = await pydoll_tab.query(
                selector, timeout=timeout, find_all=find_all, raise_exc=False,
            )
        else:
            return StructuredError(
                error_code=ErrorCode.INVALID_INPUT,
                message=f'Unknown strategy: {strategy}. Use css, xpath, or text.',
                retryable=False,
            ).to_dict()
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Element find error: {e}',
            retryable=True,
        ).to_dict()

    if elements is None:
        return StructuredError(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message=f'No element found for selector: {selector}',
            retryable=False,
            details={'selector': selector, 'strategy': strategy},
        ).to_dict()

    if find_all and isinstance(elements, list):
        cache = get_element_cache()
        results = []
        for el in elements:
            element_id = _cache_element(cache, tab_info, el)
            results.append({
                'element_id': element_id,
                'tag': el.tag_name if hasattr(el, 'tag_name') else '',
                'text': (await _safe_text(el))[:100],
                'visible': await _safe_is_visible(el),
            })
        return {
            'success': True,
            'found': len(results),
            'elements': results,
        }
    else:
        el = elements[0] if isinstance(elements, list) else elements
        cache = get_element_cache()
        element_id = _cache_element(cache, tab_info, el)
        return {
            'success': True,
            'element_id': element_id,
            'tag': el.tag_name if hasattr(el, 'tag_name') else '',
            'text': (await _safe_text(el))[:100],
            'visible': await _safe_is_visible(el),
        }


async def element_click(
    client_id: str,
    tab_id: str,
    element_id: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    config = get_timeout_config()
    timeout = timeout or config.click
    timeout = min(timeout, config.max_timeout)
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = await _resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale or not found',
            retryable=False,
            recovery_hint='Re-find the element using element_find or page_get_tree.',
        ).to_dict()

    try:
        async with tab_operation_lock(tab_id):
            await element.scroll_into_view()
            await element.click()
    except Exception:
        try:
            async with tab_operation_lock(tab_id):
                await element.click_using_js()
        except Exception as e2:
            return StructuredError(
                error_code=ErrorCode.EXECUTION_ERROR,
                message=f'Click failed: {e2}',
                retryable=True,
            ).to_dict()

    return {
        'success': True,
        'element_id': element_id,
        'clicked': True,
    }


async def element_type(
    client_id: str,
    tab_id: str,
    element_id: str,
    text: str,
    delay: float = 0.0,
) -> dict[str, Any]:
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = await _resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    try:
        async with tab_operation_lock(tab_id):
            await element.scroll_into_view()
            await element.type_text(text)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Type failed: {e}',
            retryable=True,
        ).to_dict()

    return {
        'success': True,
        'element_id': element_id,
        'chars_typed': len(text),
    }


async def element_fill(
    client_id: str,
    tab_id: str,
    element_id: str,
    value: str,
) -> dict[str, Any]:
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = await _resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    try:
        async with tab_operation_lock(tab_id):
            await element.scroll_into_view()
            await element.clear()
            await element.insert_text(value)
            current_value = await _read_element_value_via_js(element)
            if current_value != value:
                await _set_element_value_via_js(element, value)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Fill failed: {e}',
            retryable=True,
        ).to_dict()

    return {
        'success': True,
        'element_id': element_id,
        'value_length': len(value),
    }


async def element_get_text(
    client_id: str,
    tab_id: str,
    element_id: str,
    max_chars: int = 5000,
) -> dict[str, Any]:
    limits = get_limits_config()
    max_chars = min(max_chars, limits.max_text_chars)
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = await _resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    try:
        raw_text = await get_element_text(element)
        text = raw_text if isinstance(raw_text, str) else str(raw_text)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get element text: {e}',
            retryable=True,
        ).to_dict()

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    return {
        'success': True,
        'element_id': element_id,
        'text': text,
        'length': len(text),
        'truncated': truncated,
    }


async def element_get_attribute(
    client_id: str,
    tab_id: str,
    element_id: str,
    name: str,
) -> dict[str, Any]:
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = await _resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    try:
        value = get_element_attribute(element, name)
    except Exception:
        value = None

    redacted = is_sensitive_field(name)
    if redacted and value is not None:
        value = '[REDACTED]'

    return {
        'success': True,
        'element_id': element_id,
        'attribute': name,
        'value': value,
        'exists': value is not None,
        'redacted': redacted,
    }


async def element_screenshot(
    client_id: str,
    tab_id: str,
    element_id: str,
    path: str = '',
) -> dict[str, Any]:
    registry = get_registry()
    config = get_config()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = await _resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    safe_path: str | None = None
    if path:
        safe_path = validate_artifact_path(path, config)
        if safe_path is None:
            return StructuredError(
                error_code=ErrorCode.PERMISSION_DENIED,
                message=f'Screenshot path not allowed: {path}',
                retryable=False,
                recovery_hint='Use a relative path (stored in artifacts dir) or a path in an allowed directory.',
            ).to_dict()

    try:
        async with tab_operation_lock(tab_id):
            if safe_path:
                await element.take_screenshot(path=safe_path, as_base64=False)
                return {'success': True, 'path': safe_path}
            else:
                result = await element.take_screenshot(as_base64=True)
                return {'success': True, 'data': result if isinstance(result, str) else ''}
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Element screenshot failed: {e}',
            retryable=True,
        ).to_dict()


async def _resolve_element(tab_info: Any, element_id: str) -> Any:
    cache = get_element_cache()
    entry = cache.get_valid(element_id, tab_info.tab_id, tab_info.document_generation)
    if entry is None:
        return None

    if entry._pydoll_element is not None:
        return entry._pydoll_element

    pydoll_tab = tab_info._pydoll_tab
    if pydoll_tab is None:
        return None

    hints_to_try = []
    if entry.selector_hint:
        hints_to_try.append(('css', entry.selector_hint))
    if entry.xpath_hint:
        hints_to_try.append(('xpath', entry.xpath_hint))

    for _strategy, hint in hints_to_try:
        try:
            element = await pydoll_tab.query(
                hint, timeout=5, find_all=False, raise_exc=False,
            )
            if element is not None:
                entry._pydoll_element = element
                cache.store(entry)
                return element
        except Exception:
            continue

    return None


def _cache_element(cache: Any, tab_info: Any, element: Any) -> str:
    import uuid
    element_id = f'el_{uuid.uuid4().hex[:12]}'
    text_summary = ''
    tag = ''
    try:
        if hasattr(element, 'tag_name'):
            tag = element.tag_name or ''
    except Exception:
        pass
    entry = ElementCacheEntry(
        element_id=element_id,
        tab_id=tab_info.tab_id,
        document_generation=tab_info.document_generation,
        tag_name=tag,
        text_summary=text_summary,
        _pydoll_element=element,
    )
    cache.store(entry)
    return element_id


async def _safe_text(element: Any) -> str:
    return await get_element_text(element)


async def _safe_is_visible(element: Any) -> bool:
    try:
        result = await element.is_visible()
        return bool(result)
    except Exception:
        return False


async def _set_element_value_via_js(element: Any, value: str) -> None:
    value_literal = json.dumps(value)
    script = f"""
    const nextValue = {value_literal};
    if (this.tagName === 'INPUT' || this.tagName === 'TEXTAREA') {{
        this.value = nextValue;
        this.dispatchEvent(new Event('input', {{ bubbles: true }}));
        this.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return this.value;
    }}
    if (this.isContentEditable) {{
        this.textContent = nextValue;
        this.dispatchEvent(new Event('input', {{ bubbles: true }}));
        return this.textContent;
    }}
    return null;
    """
    result = await element.execute_script(script, return_by_value=True)
    actual = extract_script_value(result)
    if actual != value:
        raise ValueError('Element value could not be set through JavaScript fallback')


async def _read_element_value_via_js(element: Any) -> str | None:
    result = await element.execute_script(
        """
        if (this.tagName === 'INPUT' || this.tagName === 'TEXTAREA') return this.value;
        if (this.isContentEditable) return this.textContent;
        return null;
        """,
        return_by_value=True,
    )
    actual = extract_script_value(result)
    return actual if isinstance(actual, str) else None
