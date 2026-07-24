"""Semantic selection of radio and checkbox options."""

from __future__ import annotations

import asyncio
import json
import uuid

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_bool, get_string
from pydoll_mcp_server.tools.choice_group_scripts import choice_group_helpers_script

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
    result: JsonObject = {}
    for attempt in range(3):
        try:
            async with tab_operation_lock(tab_id):
                raw = await tab_info.pydoll_tab.execute_script(_choice_script(payload), return_by_value=True)
            result = extract_script_object(raw)
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
    const selector = choiceSelectorHint(target);
    const state = () => choiceChecked(target);
    let strategy = 'already_selected';
    if (!state()) {{
        target.click(); strategy = 'choice';
        if (!state()) {{
            const label = target.closest('label');
            if (label && choiceVisible(label)) {{ label.click(); strategy = 'associated_label'; }}
        }}
    }}
    if (!state()) return {{checked:false,verified:false,clicked:true,strategy_used:strategy,
        tag:target.tagName.toLowerCase(),label:choiceOptionText(target),field_label:match.group.label,
        selector_hint:selector}};
    return {{checked:true,verified:true,strategy_used:strategy,tag:target.tagName.toLowerCase(),
        label:choiceOptionText(target),field_label:match.group.label,
        selector_hint:selector}};
"""
        + choice_group_helpers_script()
        + """
    ;
"""
    )
