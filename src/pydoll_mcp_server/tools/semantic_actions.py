"""Semantic click and mouse tools for visible page controls."""

from __future__ import annotations

import json
from contextlib import suppress
from typing import Annotated

from pydantic import Field
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.pydoll_compat import get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_script_array,
)
from pydoll_mcp_server.dom.element_cache import get_element_cache
from pydoll_mcp_server.dom.reference_scripts import ELEMENT_REFERENCE_HELPERS
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_float, get_string, require_json_object
from pydoll_mcp_server.security.site_signals import inspect_element_security, inspect_site_diagnostics
from pydoll_mcp_server.tools.choice_semantic_verification import wait_for_choice_state
from pydoll_mcp_server.tools.click_observation import missing_effects, observe_effects
from pydoll_mcp_server.tools.mouse_actions import element_click_center, mouse_click

__all__ = ['element_click_by_text', 'element_click_center', 'mouse_click']


async def element_click_by_text(
    client_id: str,
    tab_id: str,
    text: Annotated[str, Field(description='Visible text of the intended actionable control.')],
    match_index: Annotated[
        int | None,
        Field(
            description='Optional zero-based occurrence among filtered matches. Use only when identical text is intentional.'
        ),
    ] = None,
    exact: Annotated[bool, Field(description='Require exact normalized text when true.')] = True,
    timeout: float | None = None,
    role: Annotated[str, Field(description='Optional ARIA role filter such as button or link.')] = '',
    tag: Annotated[str, Field(description='Optional HTML tag filter.')] = '',
    within_element_id: Annotated[
        str,
        Field(description='Optional cached container element_id that limits the search scope.'),
    ] = '',
    nearest_heading: Annotated[str, Field(description='Optional nearby heading used to rank candidates.')] = '',
    section_label: Annotated[str, Field(description='Optional section label used to rank candidates.')] = '',
    aria_contains: Annotated[str, Field(description='Optional substring required in the accessible label.')] = '',
    prefer_modal: Annotated[bool, Field(description='Prefer visible controls inside a modal or dialog.')] = True,
    prefer_main_content: Annotated[bool, Field(description='Prefer controls in the main content region.')] = True,
    prefer_visible_center: Annotated[
        bool, Field(description='Prefer candidates near the visible viewport center.')
    ] = True,
    prefer_largest: Annotated[bool, Field(description='Prefer the candidate with the largest visible bounds.')] = False,
    ambiguity_threshold: Annotated[
        int,
        Field(description='Minimum score gap required to accept a close candidate match.'),
    ] = 25,
    actionable_only: Annotated[
        bool,
        Field(description='Reject non-actionable text containers unless an unambiguous activation control exists.'),
    ] = True,
    expect_url_change: Annotated[bool, Field(description='Require a URL change after the click.')] = False,
    expect_text: Annotated[str, Field(description='Optional text expected after the click.')] = '',
    expect_selector: Annotated[str, Field(description='Optional CSS selector expected after the click.')] = '',
    effect_timeout: Annotated[
        float | None, Field(description='Timeout used to observe the requested page effect.')
    ] = None,
) -> JsonObject:
    if match_index is not None and match_index < 0:
        return StructuredError(ErrorCode.INVALID_INPUT, 'match_index must be zero or greater').to_dict()
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
            'match_index': match_index,
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
            'actionable_only': actionable_only,
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
    pre_click_url = ''
    with suppress(StructuredError, PydollException):
        pre_click_url = await get_tab_url(get_registry().get_tab(client_id, tab_id).pydoll_tab)
    click = await _click_candidate(client_id, tab_id, chosen, timeout)
    if not click.get('success'):
        return click
    if get_string(chosen, 'role') in {'radio', 'checkbox'}:
        verified = await wait_for_choice_state(
            client_id,
            tab_id,
            text=text,
            role=get_string(chosen, 'role'),
            match_index=match_index,
            selector=get_string(chosen, 'selector_hint'),
            timeout=timeout,
        )
        if not verified:
            return StructuredError(
                ErrorCode.STALE_ELEMENT,
                f'Choice click was not verified after selecting: {text}',
                details={'chosen': chosen, 'click': click},
                retryable=True,
                recovery_hint='Re-resolve the choice group and retry after the page finishes rendering.',
            ).to_dict()
        click['verified'] = True
    has_effect = bool(expect_url_change or expect_text or expect_selector)
    matched_effects: JsonArray = []
    effect_observed = False
    if has_effect:
        try:
            tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
            effect_observed, matched = await observe_effects(
                tab_id,
                tab,
                pre_click_url,
                False,
                expect_url_change,
                expect_text,
                expect_selector,
                False,
                min(effect_timeout or 5.0, 30.0),
            )
            matched_effects = list(matched)
        except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
            effect_observed = False
    missing = missing_effects(False, expect_url_change, expect_text, expect_selector, False, matched_effects)
    diagnostics = await inspect_site_diagnostics(get_registry().get_tab(client_id, tab_id).pydoll_tab)
    mcp_action: JsonObject = {'event_sent': True, 'strategy': click.get('mode_used', 'mouse')}
    page_effect: JsonObject = {
        'expectation': {'url_change': expect_url_change, 'text': expect_text, 'selector': expect_selector},
        'observed': effect_observed,
        'matched': matched_effects,
        'missing': missing,
    }
    if has_effect and missing:
        response = StructuredError(
            ErrorCode.NO_EFFECT,
            'The click event was sent, but the requested page effect was not observed.',
            details={'mcp_action': mcp_action, 'page_effect': page_effect, 'site_diagnostics': diagnostics},
            retryable=True,
        ).to_dict()
        response.update(
            {
                'clicked': True,
                'chosen': chosen,
                'mcp_action': mcp_action,
                'page_effect': page_effect,
                'site_diagnostics': diagnostics,
                'failure_origin': 'page',
            }
        )
        return response
    return {
        'success': True,
        'clicked': True,
        'mode_used': click.get('mode_used', 'mouse'),
        'chosen': chosen,
        'rejected': _rejected(candidates, chosen),
        'mcp_action': mcp_action,
        'page_effect': page_effect,
        'site_diagnostics': diagnostics,
    }


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


async def _click_candidate(
    client_id: str,
    tab_id: str,
    chosen: JsonObject,
    timeout: float | None,
) -> JsonObject:
    selector = str(chosen.get('activation_selector_hint') or chosen.get('selector_hint', ''))
    if selector and selector not in {'button', 'a', 'input', 'textarea', 'select', 'label', 'div', 'span'}:
        try:
            async with tab_operation_lock(tab_id):
                tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
                element = await tab.query(selector, timeout=1, find_all=False, raise_exc=False)
                if element is not None:
                    security_control = await inspect_element_security(element)
                    if security_control:
                        response = StructuredError(
                            ErrorCode.SECURITY_CONTROL_PRESENT,
                            'The target is a security control that requires user action.',
                            details={'security_control': security_control},
                            recovery_hint='Ask the user to complete the security control, then re-observe the page.',
                        ).to_dict()
                        response['failure_origin'] = 'security'
                        return response
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
"""
        + ELEMENT_REFERENCE_HELPERS
        + """

function norm(v) { return (v || '').trim().replace(/\\s+/g, ' '); }
function fold(v) { return normalizeVisibleText(v).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase(); }
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
    const parts = [];
    let current = el;
    while (current && current.nodeType === 1 && current !== document.body) {
        const tag = current.tagName.toLowerCase();
        let position = 1;
        let sibling = current.previousElementSibling;
        while (sibling) {
            if (sibling.tagName === current.tagName) position += 1;
            sibling = sibling.previousElementSibling;
        }
        parts.unshift(tag + ':nth-of-type(' + position + ')');
        current = current.parentElement;
    }
    return parts.join(' > ');
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
function activationTarget(el) {
    if (isActionable(el)) return el;
    return el.closest('button,a,[role="button"],[role="link"],[tabindex]');
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
    const lower = fold(txt);
    const expectedFolded = fold(opts.text);
    const textMatch = opts.exact ? lower === expectedFolded : lower.includes(expectedFolded);
    if (!textMatch) continue;
    if (filters.role && (el.getAttribute('role')||'').toLowerCase() !== filters.role) continue;
    if (filters.tag && el.tagName.toLowerCase() !== filters.tag) continue;
    if (filters.heading && !nearestHeading(el).toLowerCase().includes(filters.heading)) continue;
    if (filters.section && !sectionLabel(el).toLowerCase().includes(filters.section)) continue;
    if (filters.aria && !(el.getAttribute('aria-label')||'').toLowerCase().includes(filters.aria)) continue;

    const role = el.getAttribute('role') || '';
    const actionable = isActionable(el);
    const activation = activationTarget(el);
    const activationActionable = Boolean(activation && isActionable(activation));
    if (opts.actionable_only && !actionable && !activationActionable) continue;
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
    if (activationActionable) score += 300;
    if (!actionable && activationActionable) score -= 40;
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
        selector_hint: structuralSelector(el),
        activation_selector_hint: activationActionable ? structuralSelector(activation) : structuralSelector(el),
        activation_tag: activationActionable ? activation.tagName.toLowerCase() : el.tagName.toLowerCase(),
        activation_role: activationActionable ? (activation.getAttribute('role') || '') : role,
        bounds: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
        score,
        contains_multiple_options: false
    });
}

if (Number.isInteger(opts.match_index)) {
    const indexed = results[opts.match_index];
    return indexed ? [indexed] : [];
}
results.sort((a, b) => b.score - a.score);
return results.slice(0, opts.max_candidates);
"""
    )
