"""Semantic native and custom combobox operations."""

from __future__ import annotations

import asyncio
import json
import time
import unicodedata

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_normalized_array,
    extract_normalized_object,
)
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_bool,
    get_float,
    get_string,
    require_json_object,
)
from pydoll_mcp_server.tools.element_resolver import resolve_element
from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens
from pydoll_mcp_server.tools.form_controls import fill_element_framework_safe
from pydoll_mcp_server.tools.form_scripts import combobox_options_script, select_options_script


async def combobox_get_options(client_id: str, tab_id: str, element_id: str, max_options: int = 50) -> JsonObject:
    return await _combobox_options(client_id, tab_id, element_id, max_options)


async def select_get_options(client_id: str, tab_id: str, element_id: str, max_options: int = 50) -> JsonObject:
    safe_max_options = max(1, min(max_options, 200))
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
    try:
        result = await element.execute_script(select_options_script(safe_max_options), return_by_value=True)
        data = extract_normalized_object(result, 'select_options')
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Select options failed: {exc}', retryable=True).to_dict()

    error = get_string(data, 'error', '')
    if error:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'Element is not a native select.',
            details={'tag': get_string(data, 'tag', '')},
        ).to_dict()
    return {'contract_version': 2, 'operation_id': f'select_options_{int(time.time() * 1000)}', 'success': True, **data}


async def combobox_type_and_select(
    client_id: str,
    tab_id: str,
    element_id: str,
    query: str,
    option_text: str = '',
    exact: bool = True,
    timeout: float | None = None,
    allow_approximate: bool = False,
) -> JsonObject:
    invalidate_review_tokens(client_id, tab_id)
    set_result = await fill_element_framework_safe(
        client_id,
        tab_id,
        element_id,
        query,
        query,
        True,
        ['input', 'change'],
        state_verification='framework_event',
    )
    if not set_result.get('success'):
        return set_result
    return await combobox_select_option(
        client_id,
        tab_id,
        element_id,
        option_text or query,
        exact,
        timeout,
        allow_approximate,
    )


async def combobox_select_option(
    client_id: str,
    tab_id: str,
    element_id: str,
    option_text: str,
    exact: bool = True,
    timeout: float | None = None,
    allow_approximate: bool = False,
) -> JsonObject:
    limit = min(timeout or 10.0, 120.0)
    deadline = time.monotonic() + limit
    selected: JsonObject | None = None
    approximate_match = False
    while time.monotonic() < deadline:
        options = await _combobox_options(client_id, tab_id, element_id)
        if not options.get('success'):
            return options
        selected, approximate_match, ambiguous = _select_option_with_mode(
            get_array(options, 'options', []), option_text, exact, allow_approximate
        )
        if ambiguous:
            return StructuredError(
                ErrorCode.AMBIGUOUS_ELEMENT,
                f'Multiple combobox options matched: {option_text}',
                details={'candidates': ambiguous},
                retryable=False,
            ).to_dict()
        if selected is not None:
            break
        await asyncio.sleep(0.1)
    if selected is None:
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f'No combobox option matched: {option_text}',
            retryable=True,
        ).to_dict()

    invalidate_review_tokens(client_id, tab_id)
    bounds = require_json_object(selected.get('bounds'), 'option bounds')
    width = get_float(bounds, 'width')
    height = get_float(bounds, 'height')
    if width <= 0 or height <= 0:
        return StructuredError(
            ErrorCode.HIDDEN_EFFECT,
            'The matched combobox option is not visibly rendered.',
            details={'option_text': get_string(selected, 'text', '')},
            retryable=True,
        ).to_dict()
    x = get_float(bounds, 'x') + width / 2
    y = get_float(bounds, 'y') + height / 2
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        async with tab_operation_lock(tab_id):
            await tab.mouse.click(x, y)
    except (PydollException, StructuredError) as exc:
        if isinstance(exc, StructuredError):
            return exc.to_dict()
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Combobox option click failed: {exc}',
            retryable=True,
        ).to_dict()

    selected_text = get_string(selected, 'text', '')
    selected_value = get_string(selected, 'value', '')
    state = await read_element_value(client_id, tab_id, element_id)
    verified = _combobox_selection_verified(state, selected_text, selected.get('id', ''))
    mode_used = 'mouse'
    if not verified:
        fallback = await _dispatch_option_click(client_id, tab_id, element_id, selected_text, exact=True)
        if not fallback.get('success'):
            return fallback
        state = await read_element_value(client_id, tab_id, element_id)
        verified = _combobox_selection_verified(state, selected_text, selected.get('id', ''))
        mode_used = 'scripted_option_click'
    return {
        'contract_version': 2,
        'operation_id': f'combobox_{int(time.time() * 1000)}',
        'success': True,
        'status': 'verified' if verified else 'inconclusive',
        'selected': selected,
        'selected_label': selected_text,
        'selected_value': selected_value,
        'selected_state': 'selected' if verified else 'inconclusive',
        'verified': verified,
        'verification': 'verified' if verified else 'inconclusive',
        'approximate_match': approximate_match,
        'mode_used': mode_used,
        'new_element_id': element_id,
        'state': state,
    }


async def read_element_value(client_id: str, tab_id: str, element_id: str) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
    try:
        result = await element.execute_script(
            "return {value:this.value??this.textContent??'', text:this.innerText??this.textContent??'', "
            "active:this.getAttribute('aria-activedescendant')||'', "
            "popup_open:this.getAttribute('aria-expanded')==='true'};",
            return_by_value=True,
        )
        state = extract_normalized_object(result, 'combobox_read_value')
        return {'success': True, 'element_id': element_id, **state}
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Read value failed: {exc}', retryable=True).to_dict()


async def _combobox_options(
    client_id: str,
    tab_id: str,
    element_id: str,
    max_options: int = 50,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
    try:
        result = await element.execute_script(combobox_options_script(max_options), return_by_value=True)
        options = extract_normalized_array(result, 'combobox_options')
        return {
            'contract_version': 2,
            'operation_id': f'combobox_options_{int(time.time() * 1000)}',
            'success': True,
            'status': 'verified',
            'options': options,
            'count': len(options),
        }
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Combobox options failed: {exc}', retryable=True).to_dict()


async def _dispatch_option_click(
    client_id: str,
    tab_id: str,
    element_id: str,
    option_text: str,
    exact: bool,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
    payload = json.dumps({'text': option_text, 'exact': exact})
    script = f"""
    const payload = {payload};
    const expected = payload.text.normalize('NFC').trim().replace(/\\s+/g, ' ').toLocaleLowerCase();
    function norm(value) {{ return (value || '').normalize('NFC').trim().replace(/\\s+/g, ' ').toLocaleLowerCase(); }}
    function visible(el) {{
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }}
    for (const option of document.querySelectorAll('[role="option"]')) {{
        const text = norm(option.innerText || option.textContent || '');
        const matched = payload.exact ? text === expected : text.includes(expected);
        if (matched && visible(option) && option.getAttribute('aria-disabled') !== 'true') {{
            option.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true, view: window}}));
            option.dispatchEvent(new MouseEvent('mouseup', {{bubbles: true, view: window}}));
            option.dispatchEvent(new MouseEvent('click', {{bubbles: true, view: window}}));
            return {{clicked: true, text: option.innerText || option.textContent || '', id: option.id || ''}};
        }}
    }}
    return {{error: 'option_not_found'}};
    """
    try:
        result = extract_normalized_object(
            await element.execute_script(script, return_by_value=True), 'combobox_option_click'
        )
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Combobox fallback failed: {exc}', retryable=True).to_dict()
    error = get_string(result, 'error', '')
    if error:
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, error, retryable=True).to_dict()
    return {'success': True, **result}


def select_option(
    options: JsonArray,
    text: str,
    exact: bool,
    allow_approximate: bool,
) -> JsonObject | None:
    selected, _, _ = _select_option_with_mode(options, text, exact, allow_approximate)
    return selected


def _select_option_with_mode(
    options: JsonArray,
    text: str,
    exact: bool,
    allow_approximate: bool,
) -> tuple[JsonObject | None, bool, JsonArray]:
    normalized = _normalize(text)
    exact_matches: list[JsonObject] = []
    for option_value in options:
        option = require_json_object(option_value, 'combobox option')
        if get_bool(option, 'disabled', False):
            continue
        option_text = _normalize(get_string(option, 'text', ''))
        if (exact and option_text == normalized) or (not exact and normalized in option_text):
            exact_matches.append(option)
    if len(exact_matches) > 1:
        ambiguous_values: JsonArray = []
        ambiguous_values.extend(exact_matches)
        return None, False, ambiguous_values
    if exact_matches:
        return exact_matches[0], False, []
    if allow_approximate:
        approximate = _fold(text)
        matches: list[JsonObject] = []
        for option_value in options:
            option = require_json_object(option_value, 'combobox option')
            if get_bool(option, 'disabled', False):
                continue
            if _fold(get_string(option, 'text', '')) == approximate:
                matches.append(option)
        if len(matches) == 1:
            return matches[0], True, []
        if len(matches) > 1:
            ambiguous_values = []
            ambiguous_values.extend(matches)
            return None, False, ambiguous_values
    return None, False, []


def _combobox_selection_verified(state: JsonObject, selected_text: str, selected_id: object) -> bool:
    if not state.get('success'):
        return False
    value = get_string(state, 'value', '')
    text = get_string(state, 'text', '')
    active = get_string(state, 'active', '')
    return value == selected_text or text == selected_text or (selected_id != '' and active == str(selected_id))


def _normalize(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def _fold(text: str) -> str:
    normalized = unicodedata.normalize('NFD', unicodedata.normalize('NFC', text).casefold())
    return ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')


__all__ = [
    'combobox_get_options',
    'combobox_select_option',
    'combobox_type_and_select',
    'read_element_value',
    'select_get_options',
    'select_option',
]
