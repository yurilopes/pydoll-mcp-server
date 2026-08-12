"""Shared post-action effect observation for browser interaction tools."""

from __future__ import annotations

import asyncio
import json
import time

from pydoll.browser.tab import Tab
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.pydoll_compat import get_tab_url
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_normalized_bool,
    extract_normalized_object,
    extract_normalized_string,
)
from pydoll_mcp_server.errors import StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_string
from pydoll_mcp_server.tools.element_resolver import resolve_element


async def capture_effect_state(
    tab_info: TabInfo,
    attribute_selector: str,
    attribute_name: str,
    enabled_element_id: str,
    progress_change: bool,
    active_surface_change: bool,
) -> JsonObject:
    """Capture page state before a click so post-click effects are meaningful."""

    state: JsonObject = {}
    if attribute_selector and attribute_name:
        state.update(
            extract_normalized_object(
                await tab_info.pydoll_tab.execute_script(
                    _effect_state_script(attribute_selector, attribute_name),
                    return_by_value=True,
                ),
                'click_effect_state',
            )
        )
    if progress_change or active_surface_change:
        state.update(
            extract_normalized_object(
                await tab_info.pydoll_tab.execute_script(_surface_effect_script(), return_by_value=True),
                'click_surface_effect_state',
            )
        )
    if enabled_element_id:
        element = await resolve_element(tab_info, enabled_element_id)
        if element is not None:
            state['enabled'] = extract_normalized_bool(
                await element.execute_script(
                    "return !this.disabled && this.getAttribute('aria-disabled') !== 'true';",
                    return_by_value=True,
                ),
                'click_enabled_state',
            )
    return state


def _effect_state_script(selector: str, attribute: str) -> str:
    selector_literal = json.dumps(selector)
    attribute_literal = json.dumps(attribute)
    return (
        f'const element=document.querySelector({selector_literal});'
        f'const name={attribute_literal};'
        'return {attribute_present:Boolean(element && element.hasAttribute(name)),'
        "attribute:element ? element.getAttribute(name) || '' : ''};"
    )


def _surface_effect_script() -> str:
    return """
    function visible(node) {
        const rect=node.getBoundingClientRect();
        const style=getComputedStyle(node);
        return rect.width>0 && rect.height>0 && style.display!=='none' && style.visibility!=='hidden';
    }
    const progress=[...document.querySelectorAll('[role="progressbar"], progress, [aria-valuenow]')]
        .filter(visible).map(node => node.getAttribute('aria-valuenow') || node.textContent || '').join('|');
    const surface=[...document.querySelectorAll('[role="dialog"], dialog[open], form, [aria-modal="true"]')]
        .filter(visible).map(node => {
            const controls=[...node.querySelectorAll('input, textarea, select, [contenteditable="true"]')]
                .filter(visible).length;
            const buttons=[...node.querySelectorAll('button, [role="button"]')].filter(visible).length;
            const text=(node.innerText || '').replace(/\\s+/g, ' ').slice(0, 160);
            return [node.getAttribute('aria-label') || node.id || node.tagName, controls, buttons, text].join(':');
        }).join('|');
    return {progress, surface};
    """


async def observe_effects(
    tab_id: str,
    pydoll_tab: Tab,
    pre_click_url: str,
    expect_dialog: bool,
    expect_url_change: bool,
    expect_text: str,
    expect_selector: str,
    expect_network_idle: bool,
    timeout_val: float,
    *,
    tab_info: TabInfo | None = None,
    baseline: JsonObject | None = None,
    expect_attribute_selector: str = '',
    expect_attribute_name: str = '',
    expect_attribute_value: str = '',
    expect_enabled_element_id: str = '',
    expect_progress_change: bool = False,
    expect_active_surface_change: bool = False,
) -> tuple[bool, list[str]]:
    del tab_id
    deadline = time.monotonic() + timeout_val
    matched: list[str] = []

    while time.monotonic() < deadline:
        if expect_dialog and 'expect_dialog' not in matched:
            try:
                script = (
                    'const d=document.querySelector(\'[role="dialog"]:not([style*="display: none"])'
                    ', dialog[open], [aria-modal="true"]\');'
                    "return d ? d.getAttribute('aria-label') || d.tagName : '';"
                )
                result = await pydoll_tab.execute_script(script, return_by_value=True)
                dialog_text = extract_normalized_string(result, 'click_dialog_effect')
                if dialog_text:
                    matched.append('expect_dialog')
            except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                pass

        if expect_url_change and 'expect_url_change' not in matched:
            try:
                current_url = await get_tab_url(pydoll_tab) or ''
                if current_url and current_url != pre_click_url:
                    matched.append('expect_url_change')
            except (PydollException, TypeError, ValueError):
                pass

        if expect_text and 'expect_text' not in matched:
            try:
                script = f'return document.body.innerText.indexOf({expect_text!r}) >= 0;'
                result = await pydoll_tab.execute_script(script, return_by_value=True)
                if extract_normalized_bool(result, 'click_text_effect'):
                    matched.append('expect_text')
            except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                pass

        if expect_selector and 'expect_selector' not in matched:
            try:
                selector_state = await _selector_effect_state(pydoll_tab, expect_selector)
                if selector_state == 'visible':
                    matched.append('expect_selector')
                elif selector_state == 'hidden':
                    matched.append('expect_selector_hidden')
            except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                pass

        if expect_network_idle and 'expect_network_idle' not in matched:
            matched.append('expect_network_idle')

        current_state = baseline
        if tab_info is not None and any(
            (expect_attribute_selector, expect_enabled_element_id, expect_progress_change, expect_active_surface_change)
        ):
            try:
                current_state = await capture_effect_state(
                    tab_info,
                    expect_attribute_selector,
                    expect_attribute_name,
                    expect_enabled_element_id,
                    expect_progress_change,
                    expect_active_surface_change,
                )
            except (PydollException, StructuredError, InvalidScriptResponseError, TypeError, ValueError):
                current_state = None
        if expect_attribute_selector and expect_attribute_name and 'expect_attribute_change' not in matched:
            before_present = bool((baseline or {}).get('attribute_present', False))
            current_present = bool((current_state or {}).get('attribute_present', False))
            before_value = get_string(baseline or {}, 'attribute', '')
            current_value = get_string(current_state or {}, 'attribute', '')
            if (expect_attribute_value and current_value == expect_attribute_value) or (
                current_present != before_present or current_value != before_value
            ):
                matched.append('expect_attribute_change')
        if (
            expect_enabled_element_id
            and 'expect_enabled' not in matched
            and bool((current_state or {}).get('enabled', False))
        ):
            matched.append('expect_enabled')
        if (
            expect_progress_change
            and 'expect_progress_change' not in matched
            and get_string(current_state or {}, 'progress', '') != get_string(baseline or {}, 'progress', '')
        ):
            matched.append('expect_progress_change')
        if (
            expect_active_surface_change
            and 'expect_active_surface_change' not in matched
            and get_string(current_state or {}, 'surface', '') != get_string(baseline or {}, 'surface', '')
        ):
            matched.append('expect_active_surface_change')

        if all_effects_satisfied(
            expect_dialog,
            expect_url_change,
            expect_text,
            expect_selector,
            expect_network_idle,
            matched,
            expect_attribute_selector=expect_attribute_selector,
            expect_enabled_element_id=expect_enabled_element_id,
            expect_progress_change=expect_progress_change,
            expect_active_surface_change=expect_active_surface_change,
        ):
            return True, matched

        await asyncio.sleep(0.15)

    return len(matched) > 0, matched


async def _selector_effect_state(tab: Tab, selector: str) -> str:
    script = f"""
    const selector = {json.dumps(selector)};
    const nodes = [...document.querySelectorAll(selector)];
    function visible(node) {{
        for (let current = node; current; current = current.parentElement) {{
            const style = getComputedStyle(current);
            const rect = current.getBoundingClientRect();
            if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0)
                return false;
            if (rect.width <= 0 || rect.height <= 0) return false;
        }}
        return true;
    }}
    return {{visible:nodes.some(visible), present:nodes.length > 0}};
    """
    result = await tab.execute_script(script, return_by_value=True)
    state = extract_normalized_object(result, 'click_selector_effect')
    if bool(state.get('visible', False)):
        return 'visible'
    if bool(state.get('present', False)):
        return 'hidden'
    return 'absent'


def all_effects_satisfied(
    expect_dialog: bool,
    expect_url_change: bool,
    expect_text: str,
    expect_selector: str,
    expect_network_idle: bool,
    matched: list[str],
    *,
    expect_attribute_selector: str = '',
    expect_enabled_element_id: str = '',
    expect_progress_change: bool = False,
    expect_active_surface_change: bool = False,
) -> bool:
    if expect_dialog and 'expect_dialog' not in matched:
        return False
    if expect_url_change and 'expect_url_change' not in matched:
        return False
    if expect_text and 'expect_text' not in matched:
        return False
    if expect_attribute_selector and 'expect_attribute_change' not in matched:
        return False
    if expect_enabled_element_id and 'expect_enabled' not in matched:
        return False
    if expect_progress_change and 'expect_progress_change' not in matched:
        return False
    if expect_active_surface_change and 'expect_active_surface_change' not in matched:
        return False
    return not (
        (expect_selector and 'expect_selector' not in matched)
        or (expect_network_idle and 'expect_network_idle' not in matched)
    )


def effect_expectation(
    expect_dialog: bool,
    expect_url_change: bool,
    expect_text: str,
    expect_selector: str,
    expect_network_idle: bool,
    *,
    expect_attribute_selector: str = '',
    expect_attribute_name: str = '',
    expect_attribute_value: str = '',
    expect_enabled_element_id: str = '',
    expect_progress_change: bool = False,
    expect_active_surface_change: bool = False,
) -> JsonObject:
    return {
        'dialog': expect_dialog,
        'url_change': expect_url_change,
        'text': expect_text,
        'selector': expect_selector,
        'network_idle': expect_network_idle,
        'attribute_selector': expect_attribute_selector,
        'attribute_name': expect_attribute_name,
        'attribute_value': expect_attribute_value,
        'enabled_element_id': expect_enabled_element_id,
        'progress_change': expect_progress_change,
        'active_surface_change': expect_active_surface_change,
    }


def missing_effects(
    expect_dialog: bool,
    expect_url_change: bool,
    expect_text: str,
    expect_selector: str,
    expect_network_idle: bool,
    matched: JsonArray,
    *,
    expect_attribute_selector: str = '',
    expect_enabled_element_id: str = '',
    expect_progress_change: bool = False,
    expect_active_surface_change: bool = False,
) -> JsonArray:
    matched_names = {str(value) for value in matched}
    requested: list[str] = []
    if expect_dialog:
        requested.append('expect_dialog')
    if expect_url_change:
        requested.append('expect_url_change')
    if expect_text:
        requested.append('expect_text')
    if expect_selector:
        requested.append('expect_selector')
    if expect_network_idle:
        requested.append('expect_network_idle')
    if expect_attribute_selector:
        requested.append('expect_attribute_change')
    if expect_enabled_element_id:
        requested.append('expect_enabled')
    if expect_progress_change:
        requested.append('expect_progress_change')
    if expect_active_surface_change:
        requested.append('expect_active_surface_change')
    return [name for name in requested if name not in matched_names]
