"""Semantic selection of radio and checkbox options."""

from __future__ import annotations

import json
import uuid

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_bool, get_string

VALID_SCOPES = frozenset({'auto', 'modal', 'dialog', 'form', 'main', 'viewport'})


async def form_select_choice(
    client_id: str,
    tab_id: str,
    field_label: str,
    option_label: str,
    scope: str = 'auto',
) -> JsonObject:
    if not field_label.strip() or not option_label.strip() or scope not in VALID_SCOPES:
        return StructuredError(ErrorCode.INVALID_INPUT, 'field_label, option_label, and scope must be valid').to_dict()
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    payload = json.dumps({'field': field_label, 'option': option_label, 'scope': scope})
    try:
        async with tab_operation_lock(tab_id):
            raw = await tab_info.pydoll_tab.execute_script(_choice_script(payload), return_by_value=True)
        result = extract_script_object(raw)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Choice selection failed: {exc}', retryable=True).to_dict()
    error = get_string(result, 'error', '')
    if error:
        code = ErrorCode.AMBIGUOUS_ELEMENT if error.startswith('ambiguous') else ErrorCode.INVALID_INPUT
        return StructuredError(code, f'Choice selection failed: {error}', details=result).to_dict()
    element_id = _cache_choice(tab_info.tab_id, tab_info.document_generation, result)
    return {
        'success': True,
        'field_label': field_label,
        'option_label': option_label,
        'element_id': element_id,
        'selected': get_bool(result, 'checked'),
        'checked': get_bool(result, 'checked'),
        'verified': get_bool(result, 'verified'),
        'strategy_used': get_string(result, 'strategy_used'),
    }


def _cache_choice(tab_id: str, generation: int, result: JsonObject) -> str:
    element_id = f'el_{uuid.uuid4().hex[:12]}'
    get_element_cache().store(
        ElementCacheEntry(
            element_id=element_id,
            tab_id=tab_id,
            document_generation=generation,
            tag_name=get_string(result, 'tag'),
            text_summary=get_string(result, 'label')[:100],
            selector_hint=get_string(result, 'selector_hint'),
            xpath_hint=get_string(result, 'xpath_hint'),
        )
    )
    return element_id


def _choice_script(payload: str) -> str:
    return f"""
    const request = {payload};
    const norm = value => (value || '').trim().replace(/\\s+/g, ' ').toLowerCase();
    const visible = el => {{
        const rect = el.getBoundingClientRect(); const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }};
    const dialog = [...document.querySelectorAll('dialog,[role="dialog"],[aria-modal="true"]')].filter(visible).pop();
    let root = document.body;
    if (['auto','modal','dialog'].includes(request.scope) && dialog) root = dialog;
    else if (request.scope === 'form') root = [...document.querySelectorAll('form')].find(visible) || root;
    else if (request.scope === 'main') root = document.querySelector('main,[role="main"]') || root;
    const groupSelector = 'fieldset,[role="radiogroup"],[role="group"],' +
        '.form-group,.radio-group,.checkbox-group';
    const groups = [...root.querySelectorAll(groupSelector)].filter(visible);
    const groupLabel = group => {{
        const labelled = (group.getAttribute('aria-labelledby') || '').split(/\\s+/)
            .map(id => document.getElementById(id)?.innerText || '').join(' ');
        const headingSelector = ':scope > legend,:scope > label,:scope > h1,' +
            ':scope > h2,:scope > h3,:scope > h4';
        const parentSelector = ':scope > label,:scope > legend,:scope > h1,' +
            ':scope > h2,:scope > h3,:scope > h4';
        const heading = group.querySelector(headingSelector);
        const parent = group.parentElement?.querySelector(parentSelector);
        return heading?.innerText || labelled || group.getAttribute('aria-label') || parent?.innerText || '';
    }};
    const matchingGroups = groups.filter(group => norm(groupLabel(group)).includes(norm(request.field)));
    if (matchingGroups.length === 0) return {{error:'field_not_found'}};
    if (matchingGroups.length > 1) return {{error:'ambiguous_field', count:matchingGroups.length}};
    const group = matchingGroups[0];
    const choiceSelector = 'input[type="radio"],input[type="checkbox"],' +
        '[role="radio"],[role="checkbox"]';
    const choices = [...group.querySelectorAll(choiceSelector)];
    const labelFor = el => {{
        const explicit = el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]') : null;
        return explicit?.innerText || el.closest('label')?.innerText || el.getAttribute('aria-label') || el.value || '';
    }};
    const matches = choices.filter(el => norm(labelFor(el)) === norm(request.option));
    if (matches.length === 0) return {{error:'option_not_found'}};
    if (matches.length > 1) return {{error:'ambiguous_option', count:matches.length}};
    const target = matches[0];
    const state = () => target.tagName === 'INPUT' ? target.checked === true :
        target.getAttribute('aria-checked') === 'true';
    let strategy = 'already_selected';
    if (!state()) {{
        target.click(); strategy = 'input';
        if (!state()) {{
            const explicit = target.id ?
                document.querySelector('label[for="' + CSS.escape(target.id) + '"]') : null;
            const label = target.closest('label') || explicit;
            if (label && visible(label)) {{ label.click(); strategy = 'associated_label'; }}
        }}
    }}
    if (!state()) return {{error:'choice_state_not_verified'}};
    const esc = value => value.replace(/"/g, '\\"');
    const selector = target.id ? '#' + CSS.escape(target.id) :
        (target.name && target.value ? target.tagName.toLowerCase() +
            '[name="' + esc(target.name) + '"][value="' + esc(target.value) + '"]' : '');
    const xpath = target.id ? '//*[@id="' + esc(target.id) + '"]' :
        (target.name && target.value ? '//' + target.tagName.toLowerCase() +
            '[@name="' + esc(target.name) + '" and @value="' + esc(target.value) + '"]' : '');
    return {{checked:true,verified:true,strategy_used:strategy,tag:target.tagName.toLowerCase(),
        label:labelFor(target),selector_hint:selector,xpath_hint:xpath}};
    """
