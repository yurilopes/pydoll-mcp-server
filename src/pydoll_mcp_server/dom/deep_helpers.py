"""Helpers for deep DOM traversal."""

from __future__ import annotations

import uuid

from pydoll.elements.web_element import WebElement

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.pydoll_compat import get_element_attribute, get_element_text
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.dom.models import DeepRawElement
from pydoll_mcp_server.json_types import JsonArray, JsonObject


async def raw_from_pydoll_element(
    element: WebElement,
    frame_path: list[str],
    shadow_path: list[str],
) -> DeepRawElement:
    tag = str(element.tag_name or '').lower()
    attrs = element_attributes(element)
    selector = _selector_from_attrs(tag, attrs)
    text = await get_element_text(element)
    return {
        'element_id': f'el_deep_{uuid.uuid4().hex[:12]}',
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
        'pydoll_element': element,
    }


def element_attributes(element: WebElement) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for name in (
        'id',
        'class',
        'name',
        'type',
        'placeholder',
        'href',
        'src',
        'alt',
        'title',
        'value',
        'role',
        'aria-label',
        'data-testid',
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


def ensure_web_elements(value: WebElement | list[WebElement] | None) -> list[WebElement]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def cache_deep_nodes(tab_info: TabInfo, raw_elements: list[DeepRawElement]) -> list[JsonObject]:
    cache = get_element_cache()
    elements: list[JsonObject] = []
    for raw in raw_elements:
        element_id = raw['element_id']
        if not element_id:
            continue
        frame_path = raw['frame_path']
        shadow_path = raw['shadow_path']
        entry = ElementCacheEntry(
            element_id=element_id,
            tab_id=tab_info.tab_id,
            document_generation=tab_info.document_generation,
            frame_path=frame_path,
            shadow_path=shadow_path,
            selector_hint=raw['selector_hint'],
            xpath_hint=raw['xpath_hint'],
            text_summary=raw['text'][:100],
            bounding_box=raw['bounding_box'],
            tag_name=raw['tag'],
            pydoll_element=raw.get('pydoll_element'),
        )
        cache.store(entry)
        attrs: JsonObject = dict(raw['attrs'])
        bounds: JsonObject = dict(entry.bounding_box)
        frame_values: JsonArray = list(frame_path)
        shadow_values: JsonArray = list(shadow_path)
        elements.append(
            {
                'element_id': element_id,
                'tag': entry.tag_name,
                'text': entry.text_summary,
                'attrs': attrs,
                'selector_hint': entry.selector_hint,
                'xpath_hint': entry.xpath_hint,
                'frame_path': frame_values,
                'shadow_path': shadow_values,
                'bounding_box': bounds,
                'visible': raw['visible'],
                'enabled': raw['enabled'],
                'clickable': raw['clickable'],
            }
        )
    return elements
