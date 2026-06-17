"""Text candidate ranking tool for observation-only text matching."""

from __future__ import annotations

import json

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_array
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_float, get_string, require_json_object


async def element_find_by_text_candidates(
    client_id: str,
    tab_id: str,
    text: str,
    exact: bool = True,
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
    max_candidates: int = 20,
) -> JsonObject:
    safe_max = max(1, min(max_candidates, 100))

    within_selector = ''
    if within_element_id:
        try:
            tab_info = get_registry().get_tab(client_id, tab_id)
            entry = get_element_cache().get_valid(within_element_id, tab_info.tab_id, tab_info.document_generation)
            if entry and entry.selector_hint:
                within_selector = entry.selector_hint
        except (StructuredError, Exception):
            pass

    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    payload = json.dumps(
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
            'max_candidates': safe_max,
        }
    )

    try:
        result = await tab_info.pydoll_tab.execute_script(_candidates_script(payload), return_by_value=True)
        raw = extract_script_array(result)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Text candidates failed: {exc}',
            retryable=True,
        ).to_dict()

    cache = get_element_cache()
    candidates: JsonArray = []
    for item in raw:
        candidate = require_json_object(item, 'text candidate')
        unstable_index = str(candidate.get('unstable_index', '0'))
        element_id = f'el_c{unstable_index}'
        cache.store(
            ElementCacheEntry(
                element_id=element_id,
                tab_id=tab_id,
                document_generation=tab_info.document_generation,
                tag_name=get_string(candidate, 'tag', ''),
                text_summary=get_string(candidate, 'text', '')[:100],
                selector_hint=get_string(candidate, 'selector_hint', ''),
                xpath_hint=get_string(candidate, 'xpath_hint', ''),
            )
        )
        candidate['element_id'] = element_id
        candidates.append(candidate)

    ambiguous = False
    if len(candidates) >= 2:
        top2 = candidates[:2]
        s0 = get_float(require_json_object(top2[0], 'c0'), 'score', 0.0)
        s1 = get_float(require_json_object(top2[1], 'c1'), 'score', 0.0)
        a0 = require_json_object(top2[0], 'c0a').get('actionable', False)
        a1 = require_json_object(top2[1], 'c1a').get('actionable', False)
        if a0 and a1 and abs(s0 - s1) < 25:
            ambiguous = True

    return {
        'success': True,
        'candidates': candidates,
        'ambiguous': ambiguous,
        'warnings': ['Ambiguous matches detected; use filters to narrow.'] if ambiguous else [],
    }


def _candidates_script(payload_json: str) -> str:
    return (
        'const opts = '
        + payload_json
        + """;
const expected = opts.text.trim().replace(/\\s+/g, ' ').toLowerCase();
const filters = {
    role: (opts.role || '').toLowerCase(),
    tag: (opts.tag || '').toLowerCase(),
    heading: (opts.nearest_heading || '').toLowerCase(),
    section: (opts.section_label || '').toLowerCase(),
    aria: (opts.aria_contains || '').toLowerCase(),
};
const ACTIONABLE_SET = new Set(['BUTTON','A','INPUT','TEXTAREA','SELECT','LABEL','OPTION']);
const ACTIVE_ROLES = new Set(['button','link','tab','menuitem','radio','checkbox','option','combobox','textbox','switch']);

function norm(v) { return (v || '').trim().replace(/\\s+/g, ' '); }
function visible(el) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity) > 0;
}
function textOf(el) {
    return norm(el.getAttribute('aria-label') || el.value || el.innerText || el.textContent || el.placeholder || '');
}
function selectorHint(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    if (el.getAttribute('data-testid')) return '[data-testid="' + el.getAttribute('data-testid') + '"]';
    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name.replace(/"/g, '\\\\"') + '"]';
    return el.tagName.toLowerCase();
}
function xpathHint(el) {
    if (el.id) return '//*[@id="' + el.id.replace(/"/g, '&quot;') + '"]';
    return '';
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
    const role = el.getAttribute('role') || '';
    if (ACTIVE_ROLES.has(role)) return true;
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
    const text = textOf(el);
    if (!text) continue;
    const lower = text.toLowerCase();
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
    if (opts.exact) {
        score += lower === expected ? 1000 : 600;
    } else {
        score += lower === expected ? 600 : 400;
    }
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
    if (!visible(el)) score -= 1500;

    results.push({
        unstable_index: index++,
        rank: 0,
        score,
        element_id: '',
        tag: el.tagName.toLowerCase(),
        role,
        name: norm(el.getAttribute('aria-label') || el.innerText || el.textContent || ''),
        text,
        actionable,
        enabled,
        visible: visible(el),
        in_modal: inModal,
        in_main: inMain,
        nearest_heading: nearestHeading(el),
        section_label: sectionLabel(el),
        selector_hint: selectorHint(el),
        xpath_hint: xpathHint(el),
        bounds: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
        reasons: [opts.exact ? 'exact_text' : 'contains_text',
                  actionable ? 'semantic_actionable' : '',
                  enabled ? 'enabled' : ''].filter(Boolean)
    });
}

results.sort((a, b) => b.score - a.score);
const limit = Math.min(results.length, opts.max_candidates);
for (let i = 0; i < limit; i++) {
    results[i].rank = i + 1;
}
return results.slice(0, limit);
"""
    )
