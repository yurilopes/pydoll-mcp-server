"""Semantic selection of radio and checkbox options."""

from __future__ import annotations

import asyncio
import json
import uuid

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_object
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_bool, get_float, get_string
from pydoll_mcp_server.tools.choice_group_scripts import choice_group_helpers_script
from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens

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
    if _requires_candidate_confirmation(field_label):
        response = StructuredError(
            ErrorCode.CANDIDATE_CONFIRMATION_REQUIRED,
            'This choice is an attestation, legal declaration, or sensitive consent '
            'and requires candidate confirmation.',
            details={'field_label': field_label, 'option_label': option_label},
        ).to_dict()
        response.update(
            {
                'contract_version': 2,
                'operation_id': f'choice_{uuid.uuid4().hex[:16]}',
                'status': 'blocked',
                'requires_candidate_confirmation': True,
                'handoff': True,
            }
        )
        return response
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    invalidate_review_tokens(client_id, tab_id)
    payload = json.dumps({'field': field_label, 'option': option_label, 'scope': scope})
    result: JsonObject = {}
    pointer_fallback_used = False
    for attempt in range(3):
        try:
            async with tab_operation_lock(tab_id):
                raw = await tab_info.pydoll_tab.execute_script(_choice_script(payload), return_by_value=True)
            result = extract_normalized_object(raw, 'form_select_choice')
        except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
            return StructuredError(
                ErrorCode.EXECUTION_ERROR,
                f'Choice selection failed: {exc}',
                retryable=True,
            ).to_dict()
        error = get_string(result, 'error', '')
        if error:
            code = ErrorCode.AMBIGUOUS_ELEMENT if error.startswith('ambiguous') else ErrorCode.INVALID_INPUT
            return StructuredError(code, f'Choice selection failed: {error}', details=result).to_dict()
        if get_bool(result, 'verified'):
            break
        if (
            get_bool(result, 'pointer_fallback')
            and not pointer_fallback_used
            and await _click_choice_center(tab_info, result)
        ):
            pointer_fallback_used = True
            await asyncio.sleep(0.1)
            continue
        if attempt < 2:
            await asyncio.sleep(0.1)
    if not get_bool(result, 'verified'):
        return StructuredError(
            ErrorCode.STALE_ELEMENT,
            'Choice control was re-rendered before selection could be verified',
            retryable=True,
            details={'attempts': 3, 'last_result': result},
        ).to_dict()
    element_id = _cache_choice(tab_info.tab_id, tab_info.document_generation, result)
    return {
        'contract_version': 2,
        'operation_id': f'choice_{uuid.uuid4().hex[:16]}',
        'success': True,
        'status': 'verified',
        'field_label': field_label,
        'option_label': option_label,
        'selected_label': get_string(result, 'label', option_label),
        'selected_state': (
            'indeterminate'
            if get_bool(result, 'indeterminate')
            else 'selected'
            if get_bool(result, 'checked')
            else 'unselected'
        ),
        'element_id': element_id,
        'selected': get_bool(result, 'checked'),
        'checked': get_bool(result, 'checked'),
        'indeterminate': get_bool(result, 'indeterminate'),
        'verified': get_bool(result, 'verified'),
        'strategy_used': 'center_mouse' if pointer_fallback_used else get_string(result, 'strategy_used'),
    }


async def _click_choice_center(tab_info: TabInfo, result: JsonObject) -> bool:
    """Use one trusted center click for custom buttons whose DOM click is inert."""

    selector = get_string(result, 'selector_hint', '')
    if not selector:
        return False
    selector_literal = json.dumps(selector)
    script = f"""
    (() => {{
        let target = null;
        try {{ target = document.querySelector({selector_literal}); }} catch (error) {{ target = null; }}
        if (!target) return {{error: 'stale_element'}};
        target.scrollIntoView({{block: 'center'}});
        const rect = target.getBoundingClientRect();
        const style = getComputedStyle(target);
        if (rect.width <= 0 || rect.height <= 0 || style.display === 'none' || style.visibility === 'hidden')
            return {{error: 'not_visible'}};
        return {{x: rect.x + rect.width / 2, y: rect.y + rect.height / 2}};
    }})()
    """
    try:
        raw = await tab_info.pydoll_tab.execute_script(script, return_by_value=True)
        bounds = extract_normalized_object(raw, 'choice_pointer_bounds')
        if get_string(bounds, 'error', ''):
            return False
        await tab_info.pydoll_tab.mouse.click(get_float(bounds, 'x'), get_float(bounds, 'y'))
        return True
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        return False


def _requires_candidate_confirmation(label: str) -> bool:
    folded = label.casefold()
    return any(
        marker in folded
        for marker in (
            'attest',
            'certif',
            'consent',
            'legal declaration',
            'terms and conditions',
            'application terms',
            'accurate and complete',
        )
    )


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
    return (
        f"""
    const request = {payload};
    const dialog = [...document.querySelectorAll('dialog,[role="dialog"],[aria-modal="true"]')]
        .filter(choiceVisible).pop();
    let root = document.body;
    if (['auto','modal','dialog'].includes(request.scope) && dialog) root = dialog;
    else if (request.scope === 'form') root = [...document.querySelectorAll('form')].find(choiceVisible) || root;
    else if (request.scope === 'main') root = document.querySelector('main,[role="main"]') || root;
    const match = choiceFindGroup(root, request.field);
    if (!match.group) return {{error: match.reason === 'no_match' ? 'field_not_found' : 'ambiguous_field',
        count: match.candidates.length,
        candidates: match.candidates.map(item => ({{label:item.label, score:item.score,
            options:item.options.map(choiceOptionText).filter(Boolean)}}))}};
    const matches = choiceOptionMatches(match.group, request.option);
    if (matches.length === 0) return {{error:'option_not_found', field_label:match.group.label}};
    if (matches.length > 1) return {{error:'ambiguous_option', count:matches.length,
        field_label:match.group.label}};
    const target = matches[0];
    if (target.disabled || target.getAttribute('aria-disabled') === 'true')
        return {{error:'disabled_control', field_label:match.group.label}};
    const selector = choiceSelectorHint(target);
    const state = () => choiceChecked(target);
    const indeterminate = () => target.indeterminate === true || target.getAttribute('aria-checked') === 'mixed';
    let strategy = 'already_selected';
    if (!state()) {{
        target.click(); strategy = 'choice';
        if (!state()) {{
            const label = target.closest('label');
            if (label && choiceVisible(label)) {{ label.click(); strategy = 'associated_label'; }}
        }}
    }}
    if (!state()) return {{checked:false,indeterminate:indeterminate(),verified:false,
        clicked:true,strategy_used:strategy,
        tag:target.tagName.toLowerCase(),label:choiceOptionText(target),field_label:match.group.label,
        selector_hint:selector,
        pointer_fallback: target.tagName === 'BUTTON' && Boolean(choiceButtonGroup(target))}};
    return {{checked:true,indeterminate:indeterminate(),verified:true,strategy_used:strategy,
        tag:target.tagName.toLowerCase(),
        label:choiceOptionText(target),field_label:match.group.label,
        selector_hint:selector}};
"""
        + choice_group_helpers_script()
        + """
    ;
"""
    )
