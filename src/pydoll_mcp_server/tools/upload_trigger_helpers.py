"""Shared validation and result helpers for generic upload triggers."""

from __future__ import annotations

from typing import Literal

from pydoll_mcp_server.errors import ErrorCode
from pydoll_mcp_server.json_types import JsonObject, get_bool, get_int, get_object, get_string
from pydoll_mcp_server.security.upload_policy import validate_upload_path
from pydoll_mcp_server.tools.elements import element_find
from pydoll_mcp_server.tools.files import upload_files
from pydoll_mcp_server.tools.upload_trigger_scripts import UploadTriggerElement, wait_for_upload_verification

PickerStrategy = Literal['auto', 'intercept', 'desktop']


def validate_upload_paths(paths: list[str]) -> JsonObject | None:
    """Reject disallowed or missing files before any page interaction."""

    for path in paths:
        validation_error = validate_upload_path(path)
        if validation_error is not None:
            return validation_error
    return None


def direct_input_available(surface: JsonObject) -> bool:
    """Return whether the trigger can resolve one relevant file input."""

    if get_bool(surface, 'trigger_is_file_input'):
        return True
    return get_int(surface, 'local_file_input_count') == 1 or get_int(surface, 'file_input_count') == 1


async def upload_direct_input(
    client_id: str,
    tab_id: str,
    trigger_element_id: str,
    surface: JsonObject,
    paths: list[str],
    timeout_ms: int,
    strategy_requested: PickerStrategy,
) -> JsonObject:
    """Upload through a relevant input without opening a native picker."""

    element_id = trigger_element_id
    if not get_bool(surface, 'trigger_is_file_input'):
        selector = get_string(surface, 'related_input_selector') or 'input[type="file"]'
        found = await element_find(client_id, tab_id, selector=selector, timeout=timeout_ms / 1000)
        if not get_bool(found, 'success'):
            return found
        element_id = get_string(found, 'element_id')
    upload = await upload_files(client_id, tab_id, element_id, paths)
    upload['strategy_requested'] = strategy_requested
    upload['strategy_used'] = 'direct_input'
    upload['file_input_detected'] = True
    upload['native_dialog_used'] = False
    return upload


def set_strategy_requested(result: JsonObject, strategy_requested: PickerStrategy) -> None:
    result.setdefault('strategy_requested', strategy_requested)


def set_surface_diagnostics(result: JsonObject, surface: JsonObject) -> None:
    result.setdefault('file_system_access_api_available', get_bool(surface, 'file_system_access_api_available'))
    result.setdefault('file_input_count', get_int(surface, 'file_input_count'))


def should_try_desktop_fallback(result: JsonObject) -> bool:
    details = get_object(result, 'details', {})
    return get_string(details, 'reason') == 'file_system_access_picker'


async def finish_upload_result(
    trigger: UploadTriggerElement,
    result: JsonObject,
    expected_filenames: list[str],
    timeout_ms: int,
) -> JsonObject:
    """Report success only after the page exposes upload evidence."""

    if not get_bool(result, 'success'):
        return result
    verification = await wait_for_upload_verification(trigger, expected_filenames, timeout_ms)
    result['verification'] = verification
    result['filename'] = expected_filenames[0] if expected_filenames else ''
    if get_bool(verification, 'failure_detected'):
        failure_text = get_string(verification, 'failure_text') or get_string(verification, 'status_text')
        details = get_object(result, 'details', {})
        details['reason'] = (
            'native_file_rejected_by_page'
            if get_string(result, 'strategy_used') == 'desktop_picker'
            else 'upload_rejected_by_page'
        )
        if failure_text:
            details['page_message'] = failure_text
        result['details'] = details
        result['success'] = False
        result['uploaded'] = False
        result['error_code'] = ErrorCode.EXECUTION_ERROR.value
        result['message'] = failure_text or 'The page rejected the selected file'
        result['retryable'] = False
    elif not get_bool(verification, 'upload_confirmed'):
        result['success'] = False
        result['uploaded'] = False
        result['error_code'] = ErrorCode.TIMEOUT.value
        result['message'] = 'The page did not confirm the uploaded filename or upload state'
        result['retryable'] = True
    else:
        result['uploaded'] = True
    return result


__all__ = [
    'PickerStrategy',
    'direct_input_available',
    'finish_upload_result',
    'set_strategy_requested',
    'set_surface_diagnostics',
    'should_try_desktop_fallback',
    'upload_direct_input',
    'validate_upload_paths',
]
