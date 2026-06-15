"""Element resolution and low-level interaction helpers."""

from __future__ import annotations

import json
import uuid

from pydoll.browser.tab import Tab
from pydoll.elements.shadow_root import ShadowRoot
from pydoll.elements.web_element import WebElement

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.pydoll_compat import get_element_attribute, get_element_text, is_element_visible
from pydoll_mcp_server.browser.script_utils import extract_script_value
from pydoll_mcp_server.dom.element_cache import ElementCache, ElementCacheEntry, get_element_cache

QueryScope = Tab | WebElement | ShadowRoot


async def resolve_element(tab_info: TabInfo, element_id: str) -> WebElement | None:
    cache = get_element_cache()
    entry = cache.get_valid(element_id, tab_info.tab_id, tab_info.document_generation)
    if entry is None:
        return None

    if entry.pydoll_element is not None:
        return entry.pydoll_element

    pydoll_tab = tab_info.pydoll_tab
    scoped = await resolve_deep_scope(pydoll_tab, entry)
    if scoped is not None:
        entry.pydoll_element = scoped
        cache.store(entry)
        return scoped

    hints_to_try: list[str] = []
    if entry.selector_hint:
        hints_to_try.append(entry.selector_hint)
    if entry.xpath_hint:
        hints_to_try.append(entry.xpath_hint)

    for hint in hints_to_try:
        element = await pydoll_tab.query(
            hint,
            timeout=5,
            find_all=False,
            raise_exc=False,
        )
        if element is not None:
            entry.pydoll_element = element
            cache.store(entry)
            return element

    return None


async def resolve_deep_scope(tab: Tab, entry: ElementCacheEntry) -> WebElement | None:
    if not entry.frame_path and not entry.shadow_path:
        return None
    scope: QueryScope = tab
    for frame_selector in entry.frame_path:
        frame = await scope.query(frame_selector, timeout=2, find_all=False, raise_exc=False)
        if frame is None:
            return None
        scope = frame
    for shadow_selector in entry.shadow_path:
        host = await scope.query(shadow_selector, timeout=2, find_all=False, raise_exc=False)
        if host is None:
            return None
        scope = await host.get_shadow_root()
    for hint in (entry.selector_hint, entry.xpath_hint):
        if not hint:
            continue
        element = await scope.query(hint, timeout=2, find_all=False, raise_exc=False)
        if element is not None:
            return element
    return None


def cache_element(cache: ElementCache, tab_info: TabInfo, element: WebElement) -> str:
    element_id = f'el_{uuid.uuid4().hex[:12]}'
    text_summary = ''
    tag = ''
    tag = element.tag_name or ''
    attrs = {name: get_element_attribute(element, name) for name in ('id', 'data-testid', 'name')}
    selector_hint = ''
    xpath_hint = ''
    if attrs.get('id'):
        selector_hint = f'#{attrs["id"]}'
        xpath_hint = f'//*[@id="{attrs["id"]}"]'
    elif attrs.get('data-testid'):
        selector_hint = f'[data-testid="{attrs["data-testid"]}"]'
        xpath_hint = f'//*[@data-testid="{attrs["data-testid"]}"]'
    elif attrs.get('name') and tag:
        selector_hint = f'{tag}[name="{attrs["name"]}"]'
        xpath_hint = f'//{tag}[@name="{attrs["name"]}"]'
    entry = ElementCacheEntry(
        element_id=element_id,
        tab_id=tab_info.tab_id,
        document_generation=tab_info.document_generation,
        tag_name=tag,
        text_summary=text_summary,
        selector_hint=selector_hint,
        xpath_hint=xpath_hint,
        pydoll_element=element,
    )
    cache.store(entry)
    return element_id


async def safe_text(element: WebElement) -> str:
    return await get_element_text(element)


async def safe_is_visible(element: WebElement) -> bool:
    return await is_element_visible(element)


async def set_element_value_via_js(element: WebElement, value: str) -> None:
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


async def read_element_value_via_js(element: WebElement) -> str | None:
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
