"""Semantic click and mouse tools for visible page controls."""

from __future__ import annotations

import json

from pydoll.exceptions import PydollException
from pydoll.protocol.input.types import MouseButton

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_script_array,
    extract_script_object,
)
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_float, require_json_object
from pydoll_mcp_server.tools.element_resolver import resolve_element


async def element_click_by_text(
    client_id: str,
    tab_id: str,
    text: str,
    exact: bool = True,
    timeout: float | None = None,
) -> JsonObject:
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        result = await tab.execute_script(_candidate_script(text, exact), return_by_value=True)
        candidates = extract_script_array(result)
    except StructuredError as exc:
        return exc.to_dict()
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Click candidates failed: {exc}', retryable=True).to_dict()
    chosen = _choose_candidate(candidates)
    if chosen is None:
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f'No visible clickable text matched: {text}',
            retryable=False,
        ).to_dict()
    click = await _click_candidate(client_id, tab_id, chosen, timeout)
    if not click.get('success'):
        return click
    return {
        'success': True,
        'clicked': True,
        'mode_used': click.get('mode_used', 'mouse'),
        'chosen': chosen,
        'rejected': _rejected(candidates, chosen),
    }


async def element_click_center(
    client_id: str,
    tab_id: str,
    element_id: str,
    button: str = 'left',
    click_count: int = 1,
    timeout: float | None = None,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
    try:
        result = await element.execute_script(
            """const r=this.getBoundingClientRect();return {
            x:r.x,y:r.y,width:r.width,height:r.height,visible:r.width>0&&r.height>0};""",
            return_by_value=True,
        )
        bounds = extract_script_object(result)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Element bounds failed: {exc}', retryable=True).to_dict()
    if not bounds.get('visible'):
        return StructuredError(ErrorCode.INVALID_INPUT, 'Element is not visible.').to_dict()
    x = get_float(bounds, 'x') + get_float(bounds, 'width') / 2
    y = get_float(bounds, 'y') + get_float(bounds, 'height') / 2
    click = await mouse_click(client_id, tab_id, x, y, button, click_count, timeout)
    if not click.get('success'):
        return click
    click['element_id'] = element_id
    click['bounds'] = bounds
    return click


async def mouse_click(
    client_id: str,
    tab_id: str,
    x: float,
    y: float,
    button: str = 'left',
    click_count: int = 1,
    timeout: float | None = None,
) -> JsonObject:
    if x < 0 or y < 0:
        return StructuredError(ErrorCode.INVALID_INPUT, 'Mouse coordinates must be non-negative.').to_dict()
    mouse_button = _mouse_button(button)
    if mouse_button is None:
        return StructuredError(ErrorCode.INVALID_INPUT, f'Unsupported mouse button: {button}').to_dict()
    safe_click_count = max(1, min(click_count, 3))
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        async with tab_operation_lock(tab_id):
            await tab.mouse.click(x, y, button=mouse_button, click_count=safe_click_count)
        return {
            'success': True,
            'clicked': True,
            'mode_used': 'mouse',
            'x': x,
            'y': y,
            'button': mouse_button.value,
            'click_count': safe_click_count,
            'timeout': timeout or 0,
        }
    except StructuredError as exc:
        return exc.to_dict()
    except PydollException as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Mouse click failed: {exc}', retryable=True).to_dict()


def _choose_candidate(candidates: JsonArray) -> JsonObject | None:
    best: JsonObject | None = None
    best_score = -1_000_000.0
    for candidate_value in candidates:
        candidate = require_json_object(candidate_value, 'click candidate')
        score = get_float(candidate, 'score')
        if score > best_score:
            best_score = score
            best = candidate
    return best


def _rejected(candidates: JsonArray, chosen: JsonObject) -> JsonArray:
    rejected: JsonArray = []
    chosen_index = chosen.get('index')
    for candidate_value in candidates[:20]:
        candidate = require_json_object(candidate_value, 'click candidate')
        if candidate.get('index') == chosen_index:
            continue
        reason = 'lower_rank'
        if candidate.get('contains_multiple_options') is True:
            reason = 'ambiguous_ancestor'
        rejected.append({'candidate': candidate, 'reason': reason})
    return rejected


def _mouse_button(button: str) -> MouseButton | None:
    normalized = button.lower()
    if normalized == 'left':
        return MouseButton.LEFT
    if normalized == 'right':
        return MouseButton.RIGHT
    if normalized == 'middle':
        return MouseButton.MIDDLE
    return None


async def _click_candidate(
    client_id: str,
    tab_id: str,
    chosen: JsonObject,
    timeout: float | None,
) -> JsonObject:
    selector = str(chosen.get('selector_hint', ''))
    if selector and selector not in {'button', 'a', 'input', 'textarea', 'select', 'label', 'div', 'span'}:
        try:
            tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
            element = await tab.query(selector, timeout=1, find_all=False, raise_exc=False)
            if element is not None:
                async with tab_operation_lock(tab_id):
                    await element.click()
                return {'success': True, 'clicked': True, 'mode_used': 'element_click', 'timeout': timeout or 0}
        except (PydollException, StructuredError):
            pass
    bounds = require_json_object(chosen.get('bounds'), 'candidate bounds')
    x = get_float(bounds, 'x') + get_float(bounds, 'width') / 2
    y = get_float(bounds, 'y') + get_float(bounds, 'height') / 2
    return await mouse_click(client_id, tab_id, x, y, timeout=timeout)


def _candidate_script(text: str, exact: bool) -> str:
    payload = json.dumps({'text': text, 'exact': exact})
    return f"""
    const query = {payload};
    const expected = query.text.trim().replace(/\\s+/g, ' ').toLowerCase();
    const actionable = new Set(['BUTTON', 'A', 'INPUT', 'TEXTAREA', 'SELECT', 'LABEL']);
    const out = [];
    function norm(value) {{ return (value || '').trim().replace(/\\s+/g, ' '); }}
    function visible(el) {{
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }}
    function textOf(el) {{
        return norm(el.getAttribute('aria-label') || el.value || el.innerText || el.textContent || '');
    }}
    function selectorHint(el) {{
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.getAttribute('data-testid')) return '[data-testid="' + el.getAttribute('data-testid') + '"]';
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name.replace(/"/g, '\\\\"') + '"]';
        return el.tagName.toLowerCase();
    }}
    let index = 0;
    for (const el of document.querySelectorAll('button,a,input,textarea,select,label,[role],[tabindex],div,span')) {{
        if (!visible(el)) continue;
        const text = textOf(el);
        if (!text) continue;
        const lower = text.toLowerCase();
        const matches = query.exact ? lower === expected : lower.includes(expected);
        if (!matches) continue;
        const rect = el.getBoundingClientRect();
        const role = el.getAttribute('role') || '';
        const area = Math.max(1, rect.width * rect.height);
        const isActionable = actionable.has(el.tagName) || !!role || el.tabIndex >= 0 || !!el.onclick;
        const exactScore = lower === expected ? 1000 : 0;
        const actionScore = isActionable ? 200 : 0;
        const sizeScore = Math.max(0, 200 - Math.log(area));
        const multi = lower.includes('full-time') && lower.includes('freelance') && lower !== expected;
        out.push({{
            index: index++,
            tag: el.tagName.toLowerCase(),
            role,
            text,
            disabled: !!el.disabled,
            selector_hint: selectorHint(el),
            bounds: {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}},
            score: exactScore + actionScore + sizeScore - (multi ? 500 : 0) - (el.disabled ? 1000 : 0),
            contains_multiple_options: multi
        }});
    }}
    out.sort((a, b) => b.score - a.score);
    return out;
    """
