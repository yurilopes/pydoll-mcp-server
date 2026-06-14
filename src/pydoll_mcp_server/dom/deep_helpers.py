"""Helpers for deep DOM traversal."""

from __future__ import annotations

import uuid
from typing import Any

from pydoll_mcp_server.browser.pydoll_compat import get_element_attribute, get_element_text
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache


async def _raw_from_pydoll_element(
    element: Any,
    frame_path: list[str],
    shadow_path: list[str],
) -> dict[str, Any]:
    tag = _safe_tag_name(element)
    attrs = _element_attrs(element)
    selector = _selector_from_attrs(tag, attrs)
    text = await get_element_text(element)
    return {
        'elementId': f'el_deep_{uuid.uuid4().hex[:12]}',
        'tag': tag,
        'text': text[:200],
        'attrs': attrs,
        'selector_hint': selector,
        'xpath_hint': _xpath_from_attrs(tag, attrs),
        'bounding_box': {},
        'visible': True,
        'enabled': attrs.get('disabled') is None,
        'clickable': tag in {'button', 'a', 'input', 'select', 'textarea', 'option'},
        'frame_path': list(frame_path),
        'shadow_path': list(shadow_path),
        '_pydoll_element': element,
    }


def _safe_tag_name(element: Any) -> str:
    try:
        tag = element.tag_name if hasattr(element, 'tag_name') else ''
        return str(tag or '').lower()
    except Exception:
        return ''


def _element_attrs(element: Any) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for name in (
        'id', 'class', 'name', 'type', 'placeholder', 'href', 'src',
        'alt', 'title', 'value', 'role', 'aria-label', 'data-testid',
    ):
        value = get_element_attribute(element, name)
        if value is not None:
            attrs[name] = value[:500]
    return attrs


def _selector_from_attrs(tag: str, attrs: dict[str, str]) -> str:
    if attrs.get('id'):
        return f'#{attrs["id"]}'
    if attrs.get('data-testid'):
        return f'[data-testid="{attrs["data-testid"]}"]'
    if attrs.get('name') and tag:
        return f'{tag}[name="{attrs["name"]}"]'
    if attrs.get('type') and tag:
        return f'{tag}[type="{attrs["type"]}"]'
    return tag


def _xpath_from_attrs(tag: str, attrs: dict[str, str]) -> str:
    if attrs.get('id'):
        return f'//*[@id="{attrs["id"]}"]'
    if attrs.get('name') and tag:
        return f'//{tag}[@name="{attrs["name"]}"]'
    return ''


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _cache_deep_nodes(tab_info: Any, raw_elements: list[Any]) -> list[dict[str, Any]]:
    cache = get_element_cache()
    elements: list[dict[str, Any]] = []
    for raw in raw_elements:
        if not isinstance(raw, dict):
            continue
        element_id = str(raw.get('elementId') or '')
        if not element_id:
            continue
        frame_path = _list_of_strings(raw.get('frame_path'))
        shadow_path = _list_of_strings(raw.get('shadow_path'))
        entry = ElementCacheEntry(
            element_id=element_id,
            tab_id=tab_info.tab_id,
            document_generation=tab_info.document_generation,
            frame_path=frame_path,
            shadow_path=shadow_path,
            selector_hint=str(raw.get('selector_hint') or ''),
            xpath_hint=str(raw.get('xpath_hint') or ''),
            text_summary=str(raw.get('text') or '')[:100],
            bounding_box=raw.get('bounding_box') or {},
            tag_name=str(raw.get('tag') or ''),
            _pydoll_element=raw.get('_pydoll_element'),
        )
        cache.store(entry)
        elements.append({
            'element_id': element_id,
            'tag': entry.tag_name,
            'text': entry.text_summary,
            'attrs': raw.get('attrs') or {},
            'selector_hint': entry.selector_hint,
            'xpath_hint': entry.xpath_hint,
            'frame_path': frame_path,
            'shadow_path': shadow_path,
            'bounding_box': entry.bounding_box,
            'visible': bool(raw.get('visible', False)),
            'enabled': bool(raw.get('enabled', True)),
            'clickable': bool(raw.get('clickable', False)),
        })
    return elements


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
