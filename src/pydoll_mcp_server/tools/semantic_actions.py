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
from pydoll_mcp_server.dom.element_cache import get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_float, require_json_object
from pydoll_mcp_server.tools.element_resolver import resolve_element


async def element_click_by_text(
    client_id: str,
    tab_id: str,
    text: str,
    exact: bool = True,
    timeout: float | None = None,
    role: str = '',
    tag: str = '',
    within_element_id: str = '',
    nearest_heading: str = '',
    section_label: str = '',
    aria_contains: str = '',
    prefer_modal: bool = True,
    prefer_main_content: bool = True,
    prefer_visible_center: bool = True,
    prefer_largest: bool = False,
    ambiguity_threshold: int = 25,
) -> JsonObject:
    safe_threshold = max(1, min(ambiguity_threshold, 1000))
    within_selector = ''
    if within_element_id:
        try:
            tab_info = get_registry().get_tab(client_id, tab_id)
            entry = get_element_cache().get_valid(within_element_id, tab_info.tab_id, tab_info.document_generation)
            if entry and entry.selector_hint:
                within_selector = entry.selector_hint
        except (StructuredError, Exception):
            pass

    candidates_payload = json.dumps(
        {
            'text': text,
            'exact': exact,
            'role': role,
            'tag': tag,
            'within_selector_hint': within_selector,
            'nearest_heading': nearest_heading,
            'section_label': section_label,
            'aria_contains': aria_contains,
            'prefer_modal': prefer_modal,
            'prefer_main_content': prefer_main_content,
            'prefer_visible_center': prefer_visible_center,
            'prefer_largest': prefer_largest,
            'max_candidates': 10,
        }
    )
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        result = await tab.execute_script(_enhanced_candidate_script(candidates_payload), return_by_value=True)
        candidates = extract_script_array(result)
    except StructuredError as exc:
        return exc.to_dict()
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Click candidates failed: {exc}', retryable=True).to_dict()

    if len(candidates) >= 2:
        top = require_json_object(candidates[0], 'top candidate')
        runner_up = require_json_object(candidates[1], 'second candidate')
        s0 = get_float(top, 'score', 0.0)
        s1 = get_float(runner_up, 'score', 0.0)
        a0 = top.get('actionable', False)
        a1 = runner_up.get('actionable', False)
        if a0 and a1 and abs(s0 - s1) < safe_threshold:
            recovery_parts = ['text', text]
            if tag:
                recovery_parts.append(f'tag={tag}')
            if role:
                recovery_parts.append(f'role={role}')
            if within_element_id:
                recovery_parts.append(f'within={within_element_id}')
            return StructuredError(
                ErrorCode.AMBIGUOUS_ELEMENT,
                f'Ambiguous click target: "{text}" matches multiple candidates.',
                details={'candidates': candidates[:5], 'threshold': safe_threshold},
                retryable=True,
                recovery_hint=f'Use filters to narrow. Try: {", ".join(recovery_parts)}',
            ).to_dict()

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


def _enhanced_candidate_script(payload_json: str) -> str:
    return (
        'const opts = '
        + payload_json
        + """;
const expected = opts.text.trim().replace(/\\s+/g, ' ').toLowerCase();
const ACTIONABLE_SET = new Set(['BUTTON','A','INPUT','TEXTAREA','SELECT','LABEL','OPTION']);
const ACTIVE_ROLES = new Set(['button','link','tab','menuitem','radio','checkbox','option','combobox','textbox','switch']);
const filters = {
    role: (opts.role || '').toLowerCase(),
    tag: (opts.tag || '').toLowerCase(),
    heading: (opts.nearest_heading || '').toLowerCase(),
    section: (opts.section_label || '').toLowerCase(),
    aria: (opts.aria_contains || '').toLowerCase(),
};

function norm(v) { return (v || '').trim().replace(/\\s+/g, ' '); }
function visible(el) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none'
        && style.visibility !== 'hidden' && parseFloat(style.opacity) > 0;
}
function textOf(el) {
    return norm(el.getAttribute('aria-label') || el.value || el.innerText || el.textContent || '');
}
function selectorHint(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    if (el.getAttribute('data-testid')) return '[data-testid="' + el.getAttribute('data-testid') + '"]';
    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name.replace(/"/g, '\\\\"') + '"]';
    return el.tagName.toLowerCase();
}
function nearestHeading(el) {
    const section = el.closest('section, form, article, main, aside, nav');
    const heading = section ? section.querySelector('h1,h2,h3,h4,h5,h6,[role="heading"]') : null;
    return heading ? norm(heading.innerText) : '';
}
function sectionLabel(el) {
    const section = el.closest('section, form, article');
    return section ? section.getAttribute('aria-label') || '' : '';
}
function isActionable(el) {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    if (ACTIONABLE_SET.has(el.tagName)) return true;
    const rol = el.getAttribute('role') || '';
    if (ACTIVE_ROLES.has(rol)) return true;
    if (el.tabIndex >= 0) return true;
    return false;
}

const results = [];
let index = 0;
let scope = document;
if (opts.within_selector_hint) {
    const parent = document.querySelector(opts.within_selector_hint);
    if (parent) scope = parent;
}
const allEls = scope.querySelectorAll('button,a,input,textarea,select,label,[role],[tabindex],div,span,li,p,td,th,h1,h2,h3,h4,h5,h6');
for (const el of allEls) {
    if (!visible(el)) continue;
    const txt = textOf(el);
    if (!txt) continue;
    const lower = txt.toLowerCase();
    const textMatch = opts.exact ? lower === expected : lower.includes(expected);
    if (!textMatch) continue;
    if (filters.role && (el.getAttribute('role')||'').toLowerCase() !== filters.role) continue;
    if (filters.tag && el.tagName.toLowerCase() !== filters.tag) continue;
    if (filters.heading && !nearestHeading(el).toLowerCase().includes(filters.heading)) continue;
    if (filters.section && !sectionLabel(el).toLowerCase().includes(filters.section)) continue;
    if (filters.aria && !(el.getAttribute('aria-label')||'').toLowerCase().includes(filters.aria)) continue;

    const role = el.getAttribute('role') || '';
    const actionable = isActionable(el);
    const enabled = !el.disabled && el.getAttribute('aria-disabled') !== 'true';
    const inModal = !!el.closest('[role="dialog"], dialog, [aria-modal="true"], .modal-overlay');
    const inMain = !!el.closest('main, [role="main"]');

    const rect = el.getBoundingClientRect();
    const area = Math.max(1, rect.width * rect.height);
    const cx = Math.abs(rect.x + rect.width / 2 - innerWidth / 2);
    const cy = Math.abs(rect.y + rect.height / 2 - innerHeight / 2);

    let score = 0.0;
    score += lower === expected ? 1000 : 600;
    if (actionable) score += 250;
    if (enabled && visible(el)) score += 150;
    if (opts.prefer_modal && inModal) score += 120;
    if (opts.prefer_main_content && inMain) score += 80;
    if (filters.heading) score += 50;
    if (filters.section) score += 50;
    if (filters.aria) score += 50;
    if (filters.role) score += 50;

    const centerDist = Math.max(0, 1 - (cx + cy) / (innerWidth + innerHeight));
    if (opts.prefer_visible_center && !opts.prefer_largest) score += centerDist * 60;
    if (opts.prefer_largest) score += Math.log(area) * 15;
    if (!opts.prefer_largest) score -= Math.max(0, Math.log(area) * 10);

    if (el.disabled || el.getAttribute('aria-disabled') === 'true') score -= 2000;

    results.push({
        index: index++,
        tag: el.tagName.toLowerCase(),
        role,
        text: txt,
        disabled: el.disabled,
        actionable: actionable,
        enabled: enabled,
        visible: visible(el),
        in_modal: inModal,
        in_main: inMain,
        selector_hint: selectorHint(el),
        bounds: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
        score,
        contains_multiple_options: false
    });
}

results.sort((a, b) => b.score - a.score);
return results.slice(0, opts.max_candidates);
"""
    )
