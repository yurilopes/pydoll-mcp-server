"""Framework-safe form and combobox tools."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_normalized_object,
)
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonObject,
    get_array,
    get_bool,
    get_string,
)
from pydoll_mcp_server.security.policy import is_sensitive_field
from pydoll_mcp_server.security.site_signals import inspect_element_security
from pydoll_mcp_server.tools.element_resolver import resolve_element
from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens
from pydoll_mcp_server.tools.form_element_references import (
    fill_via_page_reference,
    page_reference,
    read_filled_state_via_page_reference,
)
from pydoll_mcp_server.tools.form_input_modes import (
    keyboard_fill,
    read_filled_state,
    value_equivalent,
    verification_satisfied,
    wait_expected_enabled,
)
from pydoll_mcp_server.tools.form_keyboard import read_keyboard_state, safe_keyboard_target
from pydoll_mcp_server.tools.form_runtime import advance_mutation_epoch
from pydoll_mcp_server.tools.form_scripts import fill_script, select_options_script

DEFAULT_EVENTS = ['input', 'change', 'blur']
VALID_FILL_MODES = frozenset({'auto', 'framework_safe', 'keyboard', 'blur'})
VALID_STATE_VERIFICATIONS = frozenset({'dom', 'framework_event', 'blurred', 'submission_ready'})


async def fill_element_framework_safe(
    client_id: str,
    tab_id: str,
    element_id: str,
    value: str,
    expected_value: str | None = None,
    verify: bool = True,
    events: list[str] | None = None,
    mode: Annotated[str, 'Fill mode: auto, framework_safe, keyboard, or blur.'] = 'auto',
    validation_timeout: float = 3.0,
    expected_enabled_element_id: str = '',
    state_verification: Annotated[
        str,
        'Required observable verification level: dom, framework_event, blurred, or submission_ready.',
    ] = 'submission_ready',
) -> JsonObject:
    if mode not in VALID_FILL_MODES:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            f'Unsupported fill mode: {mode}. Use: {", ".join(sorted(VALID_FILL_MODES))}',
        ).to_dict()
    if state_verification not in VALID_STATE_VERIFICATIONS:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            f'Unsupported state_verification: {state_verification}. '
            f'Use: {", ".join(sorted(VALID_STATE_VERIFICATIONS))}',
        ).to_dict()
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    fallback_used = False
    mode_used = 'framework_safe'
    verified = False
    result: JsonObject = {}
    page_reference_used = False
    try:
        async with tab_operation_lock(tab_id):
            element = await resolve_element(tab_info, element_id)
            if element is None:
                return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
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
            invalidate_review_tokens(client_id, tab_id)
            advance_mutation_epoch(client_id, tab_id, 'fill', tab_info)
            try:
                await element.execute_script(
                    "this.scrollIntoView({block:'center'}); return true;", return_by_value=True
                )
            except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                if not page_reference(tab_info, element_id):
                    raise
            if mode == 'keyboard':
                keyboard_target, keyboard_reason = await safe_keyboard_target(tab_info, element_id, element)
                if keyboard_target is None:
                    if keyboard_reason != 'security_control':
                        return StructuredError(
                            ErrorCode.EXECUTION_ERROR,
                            'Keyboard fallback safety could not be verified.',
                            retryable=True,
                            details={'reason': keyboard_reason},
                            recovery_hint='Re-observe the field and retry with a fresh element reference.',
                        ).to_dict()
                    return StructuredError(
                        ErrorCode.SECURITY_CONTROL_PRESENT,
                        'Keyboard fallback is disabled for security-sensitive controls.',
                        retryable=False,
                        recovery_hint='Complete the security control manually and resume the workflow.',
                    ).to_dict()
                await keyboard_fill(tab_info.pydoll_tab, keyboard_target, value)
                result = await read_keyboard_state(tab_info, element_id, keyboard_target)
                result.update(
                    {
                        'framework_event': True,
                        'controlled_value_survived': True,
                        'blurred': True,
                    }
                )
                mode_used = 'keyboard'
            else:
                payload = json.dumps({'value': value, 'events': _safe_events(events, mode), 'mode': mode})
                try:
                    result = extract_normalized_object(
                        await element.execute_script(fill_script(payload), return_by_value=True), 'form_fill'
                    )
                    mode_used = 'blur' if mode == 'blur' else 'framework_safe'
                except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                    try:
                        reference_result = await fill_via_page_reference(tab_info, element_id, payload)
                    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                        reference_result = None
                    if reference_result is not None:
                        result = reference_result
                        mode_used = 'blur' if mode == 'blur' else 'framework_safe'
                        page_reference_used = True
                    else:
                        keyboard_target, _ = await safe_keyboard_target(tab_info, element_id, element)
                        if mode != 'auto' or keyboard_target is None:
                            raise
                        await keyboard_fill(tab_info.pydoll_tab, keyboard_target, value)
                        result = await read_keyboard_state(tab_info, element_id, keyboard_target)
                        result.update(
                            {
                                'framework_event': True,
                                'controlled_value_survived': True,
                                'blurred': True,
                            }
                        )
                        mode_used = 'keyboard'
                        fallback_used = True
                if mode != 'keyboard' and not fallback_used:
                    await asyncio.sleep(0.12)
                    if page_reference_used:
                        observed_state = await read_filled_state_via_page_reference(tab_info, element_id) or {}
                    else:
                        observed_element = await resolve_element(tab_info, element_id) or element
                        observed_state = await read_filled_state(observed_element)
                    expected = value if expected_value is None else expected_value
                    observed_selected = get_string(observed_state, 'selected_text', '')
                    result.update(
                        {
                            **observed_state,
                            'framework_event': get_bool(result, 'framework_event', False),
                            'event_names': get_array(result, 'event_names', []),
                            'blurred': get_bool(result, 'blurred', False),
                            'controlled_value_survived': value_equivalent(observed_state, expected)
                            or observed_selected == expected,
                        }
                    )
                    verified = verification_satisfied(result, expected, state_verification)
                if mode == 'auto' and not verified and not fallback_used:
                    keyboard_target, _ = await safe_keyboard_target(tab_info, element_id, element)
                    if keyboard_target is not None:
                        await keyboard_fill(tab_info.pydoll_tab, keyboard_target, value)
                        result = await read_keyboard_state(tab_info, element_id, keyboard_target)
                        result.update(
                            {
                                'framework_event': True,
                                'controlled_value_survived': True,
                                'blurred': True,
                            }
                        )
                        mode_used = 'keyboard'
                        fallback_used = True
            if expected_enabled_element_id:
                enabled = await wait_expected_enabled(
                    tab_info,
                    expected_enabled_element_id,
                    min(max(validation_timeout, 0.1), 30.0),
                )
                if mode == 'auto' and enabled is False and not fallback_used:
                    refreshed, _ = await safe_keyboard_target(tab_info, element_id, element)
                    if refreshed is not None:
                        await keyboard_fill(tab_info.pydoll_tab, refreshed, value)
                        result = await read_keyboard_state(tab_info, element_id, refreshed)
                        result.update(
                            {
                                'framework_event': True,
                                'controlled_value_survived': True,
                                'blurred': True,
                            }
                        )
                        mode_used = 'keyboard'
                        fallback_used = True
                        enabled = await wait_expected_enabled(
                            tab_info,
                            expected_enabled_element_id,
                            min(max(validation_timeout, 0.1), 30.0),
                        )
            else:
                enabled = None
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Fill failed: {exc}', retryable=True).to_dict()

    error = get_string(result, 'error', '')
    if error:
        return StructuredError(ErrorCode.INVALID_INPUT, error, details={'tag': get_string(result, 'tag')}).to_dict()

    expected = value if expected_value is None else expected_value
    actual = get_string(result, 'value', '')
    verified = verified or verification_satisfied(result, expected, state_verification)
    ready_for_submission = verified and state_verification == 'submission_ready'
    if verify and not verified:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            'Filled value did not match expected value.',
            details={'actual_length': len(actual), 'expected_length': len(expected), 'tag': get_string(result, 'tag')},
            retryable=True,
        ).to_dict()
    return {
        'contract_version': 2,
        'operation_id': f'fill_{int(time.time() * 1000)}',
        'success': True,
        'status': 'verified' if verified else 'inconclusive',
        'element_id': element_id,
        'value_length': len(value),
        'verified': verified,
        'field_valid': verified,
        'dependent_control_enabled': enabled,
        'mode_requested': mode,
        'mode_used': mode_used,
        'fallback_used': fallback_used,
        'validation_timeout': min(max(validation_timeout, 0.1), 30.0),
        'events': list(_safe_events(events, mode)),
        'state_verification': state_verification,
        'verification': 'verified' if verified else 'inconclusive',
        'ready_for_submission': ready_for_submission,
        'state': build_public_fill_state(result, ready_for_submission=ready_for_submission),
    }


async def element_fill_and_verify(
    client_id: str,
    tab_id: str,
    element_id: str,
    value: str,
    expected_value: str = '',
    events: list[str] | None = None,
    mode: str = 'auto',
    validation_timeout: float = 3.0,
    expected_enabled_element_id: str = '',
    state_verification: str = 'submission_ready',
) -> JsonObject:
    expected = expected_value or value
    return await fill_element_framework_safe(
        client_id,
        tab_id,
        element_id,
        value,
        expected,
        True,
        events,
        mode,
        validation_timeout,
        expected_enabled_element_id,
        state_verification,
    )


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


async def _read_element_value(client_id: str, tab_id: str, element_id: str) -> JsonObject:
    from pydoll_mcp_server.tools.combobox_controls import read_element_value as implementation

    return await implementation(client_id, tab_id, element_id)


async def form_snapshot(client_id: str, tab_id: str, max_fields: int = 100) -> JsonObject:
    from pydoll_mcp_server.tools.form_snapshot import form_snapshot as implementation

    return await implementation(client_id, tab_id, max_fields)


async def form_errors(client_id: str, tab_id: str, max_fields: int = 100) -> JsonObject:
    from pydoll_mcp_server.tools.form_snapshot import form_errors as implementation

    return await implementation(client_id, tab_id, max_fields)


def _safe_events(events: list[str] | None, mode: str = 'auto') -> list[str]:
    allowed = {'input', 'change', 'blur'}
    selected = events or DEFAULT_EVENTS
    if mode == 'blur' and 'blur' not in selected:
        selected = [*selected, 'blur']
    return [event for event in selected if event in allowed]


def build_public_fill_state(state: JsonObject, *, ready_for_submission: bool | None = None) -> JsonObject:
    """Expose verification metadata without returning entered candidate data."""

    public = dict(state)
    raw_value = get_string(state, 'value', '')
    descriptor = ' '.join(get_string(state, key, '') for key in ('type', 'name', 'autocomplete', 'aria_label'))
    public.pop('value', None)
    public['value_present'] = bool(raw_value)
    public['value_length'] = len(raw_value)
    public['dom_value'] = ('[REDACTED]' if is_sensitive_field(descriptor) else '[PRESENT]') if raw_value else ''
    public['framework_value'] = get_string(state, 'framework_value', 'present' if raw_value else 'absent')
    if ready_for_submission is not None:
        public['ready_for_submission'] = ready_for_submission
    return public


async def combobox_get_options(client_id: str, tab_id: str, element_id: str, max_options: int = 50) -> JsonObject:
    from pydoll_mcp_server.tools.combobox_controls import combobox_get_options as implementation

    return await implementation(client_id, tab_id, element_id, max_options)


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
    return {
        'contract_version': 2,
        'operation_id': f'select_options_{int(time.time() * 1000)}',
        'success': True,
        **data,
    }


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
    from pydoll_mcp_server.tools.combobox_controls import combobox_type_and_select as implementation

    return await implementation(client_id, tab_id, element_id, query, option_text, exact, timeout, allow_approximate)


async def combobox_select_option(
    client_id: str,
    tab_id: str,
    element_id: str,
    option_text: str,
    exact: bool = True,
    timeout: float | None = None,
    allow_approximate: bool = False,
) -> JsonObject:
    from pydoll_mcp_server.tools.combobox_controls import combobox_select_option as implementation

    return await implementation(client_id, tab_id, element_id, option_text, exact, timeout, allow_approximate)
