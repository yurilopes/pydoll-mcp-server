"""Intent-driven form filling tool."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Annotated, TypedDict

from pydantic import Field
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_normalized_array,
    extract_normalized_object,
)
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_bool,
    get_string,
    normalize_json_value,
)
from pydoll_mcp_server.tools.element_resolver import resolve_deep_scope
from pydoll_mcp_server.tools.form_fill_script import fill_script as _fill_script
from pydoll_mcp_server.tools.form_fill_script import read_states_script
from pydoll_mcp_server.tools.form_input_modes import (
    keyboard_fallback_decision,
    keyboard_fill,
    read_filled_state,
    value_equivalent,
    wait_expected_enabled,
)
from pydoll_mcp_server.tools.form_runtime import advance_mutation_epoch
from pydoll_mcp_server.tools.form_scripts import read_filled_state_reference_script


class FormFillField(TypedDict, total=False):
    field_key: str
    label_contains: str
    question_contains: str
    placeholder_contains: str
    selector: str
    role: str
    name: str
    type: str
    value: str | int | float | bool | None
    checked: bool
    option_text: str
    mode: str
    state_verification: str


async def form_fill_fields(
    client_id: str,
    tab_id: str,
    fields: Annotated[
        list[FormFillField],
        Field(
            description='Explicit field mappings. Use one or more label, question, placeholder, selector, role, or name hints per field.'
        ),
    ],
    scope: Annotated[
        str,
        Field(
            description='Form scope hint: auto, modal, dialog, form, or main.',
            json_schema_extra={'enum': ['auto', 'modal', 'dialog', 'form', 'main']},
        ),
    ] = 'auto',
    validate: Annotated[bool, Field(description='Run validation and return validation_errors after filling.')] = True,
    include_values: Annotated[bool, Field(description='Include values in field evidence when true.')] = False,
    mode: Annotated[
        str,
        Field(
            description='Default fill mode: auto, framework_safe, keyboard, or blur.',
            json_schema_extra={'enum': ['auto', 'framework_safe', 'keyboard', 'blur']},
        ),
    ] = 'auto',
    state_verification: Annotated[
        str,
        Field(
            description='Required verification: dom, framework_event, blurred, or submission_ready.',
            json_schema_extra={'enum': ['dom', 'framework_event', 'blurred', 'submission_ready']},
        ),
    ] = 'submission_ready',
    validation_timeout: Annotated[
        float,
        Field(description='Timeout for dependent validation and enabled controls.'),
    ] = 3.0,
    expected_enabled_element_id: Annotated[
        str,
        Field(description='Optional cached control expected to become enabled after filling.'),
    ] = '',
) -> JsonObject:
    if mode not in {'auto', 'framework_safe', 'keyboard', 'blur'}:
        return StructuredError(ErrorCode.INVALID_INPUT, f'Unsupported fill mode: {mode}').to_dict()
    if state_verification not in {'dom', 'framework_event', 'blurred', 'submission_ready'}:
        return StructuredError(
            ErrorCode.INVALID_INPUT, f'Unsupported state_verification: {state_verification}'
        ).to_dict()
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    try:
        normalized_fields = [_field_to_json(field) for field in fields]
    except (TypeError, ValueError, AttributeError) as exc:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            f'fields contains non-serializable values: {exc}',
        ).to_dict()

    payload = json.dumps(
        {
            'fields': normalized_fields,
            'scope': scope,
            'validate': validate,
            'include_values': include_values,
            'mode': mode,
            'state_verification': state_verification,
        }
    )

    fallback_used = False
    fallback_count = 0
    operation_started = time.monotonic()
    browser_calls = 0
    dependent_control_enabled: bool | None = None
    try:
        async with tab_operation_lock(tab_id):
            if normalized_fields:
                advance_mutation_epoch(client_id, tab_id, 'batch_fill', tab_info)
                browser_calls += 1
            result = await tab_info.pydoll_tab.execute_script(_fill_script(payload), return_by_value=True)
            data = extract_normalized_object(result, 'form_fill')
            filled_items = get_array(data, 'filled', [])
            if filled_items and state_verification != 'dom' and mode != 'keyboard':
                await asyncio.sleep(0.12)
                stabilization_requests = [
                    {
                        'selector_hint': get_string(item, 'selector_hint', ''),
                        'shadow_path': get_array(item, 'shadow_path', []),
                    }
                    for item in filled_items
                    if isinstance(item, dict)
                ]
                try:
                    browser_calls += 1
                    stabilized = extract_normalized_array(
                        await tab_info.pydoll_tab.execute_script(
                            read_states_script(json.dumps(stabilization_requests, ensure_ascii=False)),
                            return_by_value=True,
                        ),
                        'form_fill_stabilization',
                    )
                except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                    stabilized = []
                for index, item in enumerate(filled_items):
                    if not isinstance(item, dict):
                        continue
                    stabilized_state = stabilized[index] if index < len(stabilized) else {}
                    if not isinstance(stabilized_state, dict):
                        stabilized_state = {}
                    expected = get_string(item, 'requested_value', '')
                    survived = value_equivalent(stabilized_state, expected)
                    item['controlled_value_survived'] = survived
                    item['framework_event'] = get_bool(item, 'framework_event', False)
                    item['blurred'] = get_bool(stabilized_state, 'blurred', get_bool(item, 'blurred', False))
                    item['validity'] = get_string(stabilized_state, 'validity', 'not_yet_validated')
                    item['errors'] = get_array(stabilized_state, 'errors', [])
                    item['framework_value'] = 'present' if survived else 'absent'
                    item['verified'] = survived
                    item['field_valid'] = survived and item['validity'] != 'invalid' and not item['errors']
            if expected_enabled_element_id:
                browser_calls += 1
                dependent_control_enabled = await wait_expected_enabled(
                    tab_info,
                    expected_enabled_element_id,
                    min(max(validation_timeout, 0.1), 30.0),
                )
            keyboard_requests: list[JsonObject] = []
            for item in filled_items:
                if isinstance(item, dict) and (
                    str(item.get('mode_requested', mode)) == 'keyboard' or mode == 'keyboard'
                ):
                    keyboard_requests.append(item)
            if mode == 'auto':
                keyboard_requests = []
                if dependent_control_enabled is False:
                    for item in filled_items[:1]:
                        if isinstance(item, dict):
                            keyboard_requests.append(item)
                elif state_verification != 'dom':
                    for item in filled_items:
                        if isinstance(item, dict) and keyboard_verification_needed(item, state_verification):
                            keyboard_requests.append(item)
            for item_value in keyboard_requests:
                selector = str(item_value.get('selector_hint', ''))
                if not selector:
                    continue
                element = await _resolve_fill_target(tab_info, item_value, selector)
                if element is None:
                    item_value['fallback_error'] = 'target_not_found'
                    continue
                decision = await keyboard_fallback_decision(element)
                if not get_bool(decision, 'allowed', False):
                    item_value['fallback_blocked'] = get_string(decision, 'reason', 'inspection_unavailable')
                    continue
                request_value = str(item_value.get('requested_value', ''))
                await keyboard_fill(tab_info.pydoll_tab, element, request_value)
                browser_calls += 4
                await asyncio.sleep(0.12)
                state: JsonObject | None = None
                try:
                    response = await tab_info.pydoll_tab.execute_script(
                        read_filled_state_reference_script(selector),
                        return_by_value=True,
                    )
                    referenced = extract_normalized_object(response, 'read_filled_state')
                    if not get_string(referenced, 'error', ''):
                        state = referenced
                except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                    state = None
                if state is None:
                    refreshed = await tab_info.pydoll_tab.query(
                        selector,
                        timeout=1,
                        find_all=False,
                        raise_exc=False,
                    )
                    state = await read_filled_state(refreshed or element)
                item_value['mode_used'] = 'keyboard'
                item_value['fallback_used'] = True
                item_value['framework_event'] = True
                item_value['controlled_value_survived'] = value_equivalent(state, request_value)
                item_value['blurred'] = True
                item_value['verified'] = item_value['controlled_value_survived']
                item_value['field_valid'] = item_value['verified']
                fallback_used = True
                fallback_count += 1
            if expected_enabled_element_id and fallback_used:
                dependent_control_enabled = await wait_expected_enabled(
                    tab_info,
                    expected_enabled_element_id,
                    min(max(validation_timeout, 0.1), 30.0),
                )
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Form fill failed: {exc}',
            retryable=True,
        ).to_dict()

    filled: JsonArray = []
    unfilled: JsonArray = []
    ambiguous: JsonArray = []
    validation_errors: JsonArray = []

    for item in filled_items:
        if isinstance(item, dict):
            if 'field_valid' not in item:
                item['field_valid'] = bool(item.get('verified', item.get('selected', item.get('checked', True))))
            filled.append(item)
    for item in get_array(data, 'unfilled', []):
        if isinstance(item, dict):
            unfilled.append(item)
    for item in get_array(data, 'ambiguous', []):
        if isinstance(item, dict):
            ambiguous.append(item)
    for item in get_array(data, 'validation_errors', []):
        if isinstance(item, dict):
            validation_errors.append(item)

    evidence: JsonObject = {
        'timestamp': time.time(),
        'filled_count': len(filled),
        'unfilled_count': len(unfilled),
        'ambiguous_count': len(ambiguous),
    }

    warnings: list[str] = []
    if ambiguous:
        warnings.append(f'{len(ambiguous)} field(s) had ambiguous matches.')
    if unfilled:
        warnings.append(f'{len(unfilled)} field(s) could not be filled.')
    if dependent_control_enabled is False:
        warnings.append('The expected dependent control remained disabled after validation.')

    used_modes = {str(item.get('mode_used', mode)) for item in filled if isinstance(item, dict)}
    mode_used = next(iter(used_modes)) if len(used_modes) == 1 else ('mixed' if used_modes else mode)
    for item in filled:
        if not isinstance(item, dict):
            continue
        dom_verified = bool(item.get('verified', False))
        framework_verified = bool(item.get('framework_event', False)) and dom_verified
        blurred_verified = bool(item.get('blurred', False)) and dom_verified
        compatible = {
            'dom': dom_verified,
            'framework_event': framework_verified,
            'blurred': blurred_verified,
            'submission_ready': framework_verified and blurred_verified,
        }[state_verification]
        item['verification'] = 'verified' if compatible else 'inconclusive'
        item['ready_for_submission'] = compatible and not item.get('validation_errors', [])
        if not include_values:
            item.pop('requested_value', None)
    ready_for_submission = (
        bool(filled)
        and len(filled) == len(normalized_fields)
        and all(bool(item.get('ready_for_submission', False)) for item in filled if isinstance(item, dict))
    )

    return {
        'contract_version': 2,
        'operation_id': f'form_fill_{uuid.uuid4().hex[:16]}',
        'success': len(unfilled) == 0 and len(ambiguous) == 0,
        'status': 'verified' if ready_for_submission else 'inconclusive',
        'filled': filled,
        'unfilled': unfilled,
        'ambiguous': ambiguous,
        'validation_errors': validation_errors,
        'security_controls': get_array(data, 'security_controls', []),
        'pending_required': data.get('pending_required', []),
        'mode_requested': mode,
        'mode_used': mode_used,
        'state_verification': state_verification,
        'verification': 'verified' if ready_for_submission else 'inconclusive',
        'ready_for_submission': ready_for_submission,
        'fallback_used': fallback_used,
        'field_valid': len(validation_errors) == 0 and not data.get('pending_required', []),
        'dependent_control_enabled': dependent_control_enabled,
        'validation_timeout': min(max(validation_timeout, 0.1), 30.0),
        'warnings': list(warnings),
        'evidence': evidence,
        'performance': {
            'total_ms': round(max(0.0, (time.monotonic() - operation_started) * 1000), 1),
            'discovery_ms': 0.0,
            'mutation_ms': 0.0,
            'verification_ms': 0.0,
            'wait_ms': 0.0,
            'browser_calls': browser_calls,
            'full_scans': 0,
            'deep_scans': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'fallbacks': fallback_count,
            'round_trips_saved': max(0, len(filled) - 1),
        },
    }


def _field_to_json(field: FormFillField) -> JsonObject:
    return {str(key): normalize_json_value(value, f'fields.{key}') for key, value in field.items()}


def keyboard_verification_needed(item: JsonObject, level: str) -> bool:
    """Request keyboard fallback when the requested observable signals are absent."""

    if level == 'dom':
        return False
    if not get_bool(item, 'framework_event', False) or not get_bool(item, 'controlled_value_survived', False):
        return True
    return level in {'blurred', 'submission_ready'} and not get_bool(item, 'blurred', False)


async def _resolve_fill_target(tab_info: TabInfo, item: JsonObject, selector: str) -> WebElement | None:
    shadow_path = [value for value in get_array(item, 'shadow_path', []) if isinstance(value, str)]
    frame_path = [value for value in get_array(item, 'frame_path', []) if isinstance(value, str)]
    if shadow_path or frame_path:
        entry = ElementCacheEntry(
            element_id='',
            tab_id=tab_info.tab_id,
            document_generation=tab_info.document_generation,
            selector_hint=selector,
            frame_path=frame_path,
            shadow_path=shadow_path,
        )
        return await resolve_deep_scope(tab_info.pydoll_tab, entry)
    result = await tab_info.pydoll_tab.query(selector, timeout=1, find_all=False, raise_exc=False)
    return result if isinstance(result, WebElement) else None
