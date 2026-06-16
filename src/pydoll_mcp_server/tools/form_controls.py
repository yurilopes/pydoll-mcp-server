"""Framework-safe form and combobox tools."""

from __future__ import annotations

import asyncio
import json
import time

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_script_array,
    extract_script_object,
)
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_float, get_string, require_json_object
from pydoll_mcp_server.tools.element_resolver import resolve_element
from pydoll_mcp_server.tools.form_scripts import combobox_options_script, fill_script, form_snapshot_script

DEFAULT_EVENTS = ['input', 'change', 'blur']


async def fill_element_framework_safe(
    client_id: str,
    tab_id: str,
    element_id: str,
    value: str,
    expected_value: str | None = None,
    verify: bool = True,
    events: list[str] | None = None,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()

    payload = json.dumps({'value': value, 'events': _safe_events(events)})
    script = fill_script(payload)
    try:
        async with tab_operation_lock(tab_id):
            await element.execute_script("this.scrollIntoView({block:'center'}); return true;", return_by_value=True)
            result = extract_script_object(await element.execute_script(script, return_by_value=True))
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Fill failed: {exc}', retryable=True).to_dict()

    error = get_string(result, 'error', '')
    if error:
        return StructuredError(ErrorCode.INVALID_INPUT, error, details={'tag': get_string(result, 'tag')}).to_dict()

    expected = value if expected_value is None else expected_value
    actual = get_string(result, 'value', '')
    selected_text = get_string(result, 'selected_text', '')
    verified = (actual == expected) or (selected_text == expected)
    if verify and not verified:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            'Filled value did not match expected value.',
            details={'actual_length': len(actual), 'expected_length': len(expected), 'tag': get_string(result, 'tag')},
            retryable=True,
        ).to_dict()
    return {
        'success': True,
        'element_id': element_id,
        'value_length': len(value),
        'verified': verified,
        'mode_used': 'native_setter_events',
        'events': list(_safe_events(events)),
        'state': result,
    }


async def element_fill_and_verify(
    client_id: str,
    tab_id: str,
    element_id: str,
    value: str,
    expected_value: str = '',
    events: list[str] | None = None,
) -> JsonObject:
    expected = expected_value or value
    return await fill_element_framework_safe(client_id, tab_id, element_id, value, expected, True, events)


async def element_wait_value(
    client_id: str,
    tab_id: str,
    element_id: str,
    expected_value: str,
    timeout: float | None = None,
    poll_interval: float = 0.1,
) -> JsonObject:
    limit = min(timeout or 15.0, 120.0)
    deadline = time.monotonic() + limit
    last_value = ''
    while time.monotonic() < deadline:
        result = await _read_element_value(client_id, tab_id, element_id)
        if not result.get('success'):
            return result
        last_value = get_string(result, 'value', '')
        if last_value == expected_value:
            return {'success': True, 'matched': True, 'element_id': element_id}
        await asyncio.sleep(max(0.02, min(poll_interval, 5.0)))
    return StructuredError(
        ErrorCode.TIMEOUT,
        f'Wait for element value timed out after {limit}s',
        details={'last_value_length': len(last_value), 'expected_length': len(expected_value)},
        retryable=True,
    ).to_dict()


async def form_snapshot(client_id: str, tab_id: str, max_fields: int = 100) -> JsonObject:
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        result = await tab.execute_script(form_snapshot_script(max_fields), return_by_value=True)
        fields = extract_script_array(result)
        return {'success': True, 'fields': fields, 'count': len(fields), 'partial': len(fields) >= max_fields}
    except StructuredError as exc:
        return exc.to_dict()
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Form snapshot failed: {exc}', retryable=True).to_dict()


async def form_errors(client_id: str, tab_id: str, max_fields: int = 100) -> JsonObject:
    snapshot = await form_snapshot(client_id, tab_id, max_fields)
    if not snapshot.get('success'):
        return snapshot
    errors: JsonArray = []
    for field_value in get_array(snapshot, 'fields', []):
        field = require_json_object(field_value, 'form field')
        field_errors = field.get('errors')
        if isinstance(field_errors, list) and field_errors:
            errors.append(field)
    return {'success': True, 'errors': errors, 'count': len(errors)}


async def combobox_get_options(client_id: str, tab_id: str, element_id: str, max_options: int = 50) -> JsonObject:
    result = await _combobox_options(client_id, tab_id, element_id, max_options)
    if not result.get('success'):
        return result
    return result


async def combobox_type_and_select(
    client_id: str,
    tab_id: str,
    element_id: str,
    query: str,
    option_text: str = '',
    exact: bool = False,
    timeout: float | None = None,
) -> JsonObject:
    set_result = await _set_combobox_query(client_id, tab_id, element_id, query)
    if not set_result.get('success'):
        return set_result
    return await combobox_select_option(client_id, tab_id, element_id, option_text or query, exact, timeout)


async def combobox_select_option(
    client_id: str,
    tab_id: str,
    element_id: str,
    option_text: str,
    exact: bool = False,
    timeout: float | None = None,
) -> JsonObject:
    limit = min(timeout or 10.0, 120.0)
    deadline = time.monotonic() + limit
    selected: JsonObject | None = None
    while time.monotonic() < deadline:
        options = await _combobox_options(client_id, tab_id, element_id)
        if not options.get('success'):
            return options
        selected = _select_option(get_array(options, 'options', []), option_text, exact)
        if selected is not None:
            break
        await asyncio.sleep(0.1)
    if selected is None:
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f'No combobox option matched: {option_text}',
            retryable=True,
        ).to_dict()
    bounds = require_json_object(selected.get('bounds'), 'option bounds')
    x = get_float(bounds, 'x') + get_float(bounds, 'width') / 2
    y = get_float(bounds, 'y') + get_float(bounds, 'height') / 2
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
    state = await _read_element_value(client_id, tab_id, element_id)
    if get_string(state, 'value', '') != selected_text:
        fallback = await _dispatch_option_click(client_id, tab_id, element_id, selected_text, exact=True)
        if not fallback.get('success'):
            return fallback
        return {'success': True, 'selected': selected, 'mode_used': 'scripted_option_click'}
    return {'success': True, 'selected': selected, 'mode_used': 'mouse'}


async def _read_element_value(client_id: str, tab_id: str, element_id: str) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
    try:
        result = await element.execute_script(
            "return {value:this.value??this.textContent??'', text:this.innerText??this.textContent??''};",
            return_by_value=True,
        )
        state = extract_script_object(result)
        return {'success': True, 'element_id': element_id, **state}
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Read value failed: {exc}', retryable=True).to_dict()


async def _set_combobox_query(client_id: str, tab_id: str, element_id: str, query: str) -> JsonObject:
    return await fill_element_framework_safe(client_id, tab_id, element_id, query, query, True, ['input', 'change'])


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
        options = extract_script_array(result)
        return {'success': True, 'options': options, 'count': len(options)}
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
    const expected = payload.text.trim().toLowerCase();
    function norm(value) {{ return (value || '').trim().replace(/\\s+/g, ' ').toLowerCase(); }}
    function visible(el) {{
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }}
    for (const option of document.querySelectorAll('[role="option"]')) {{
        const text = norm(option.innerText || option.textContent || '');
        const matched = payload.exact ? text === expected : text.includes(expected);
        if (matched && visible(option)) {{
            option.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true, view: window}}));
            option.dispatchEvent(new MouseEvent('mouseup', {{bubbles: true, view: window}}));
            option.dispatchEvent(new MouseEvent('click', {{bubbles: true, view: window}}));
            return {{clicked: true, text: option.innerText || option.textContent || ''}};
        }}
    }}
    return {{error: 'option_not_found'}};
    """
    try:
        result = extract_script_object(await element.execute_script(script, return_by_value=True))
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Combobox fallback failed: {exc}', retryable=True).to_dict()
    error = get_string(result, 'error', '')
    if error:
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, error, retryable=True).to_dict()
    return {'success': True, **result}


def _safe_events(events: list[str] | None) -> list[str]:
    allowed = {'input', 'change', 'blur'}
    return [event for event in events or DEFAULT_EVENTS if event in allowed]


def _select_option(options: JsonArray, text: str, exact: bool) -> JsonObject | None:
    normalized = _normalize(text)
    for option_value in options:
        option = require_json_object(option_value, 'combobox option')
        option_text = _normalize(get_string(option, 'text', ''))
        if (exact and option_text == normalized) or (not exact and normalized in option_text):
            return option
    return None


def _normalize(text: str) -> str:
    return ' '.join(text.lower().split())
