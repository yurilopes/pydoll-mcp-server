"""LinkedIn Easy Apply resume upload helpers."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from pydoll.exceptions import PydollException

from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_bool, get_object, get_string
from pydoll_mcp_server.tools.elements import element_find
from pydoll_mcp_server.tools.files import upload_files
from pydoll_mcp_server.tools.linkedin_runtime import (
    click_resolved_action as _click_resolved_action,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    execute_script as _execute_script,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    filename_visible as _filename_visible,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    has_upload_success_toast as _has_upload_success_toast,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    upload_with_file_chooser as _upload_with_file_chooser,
)
from pydoll_mcp_server.tools.linkedin_scripts import resolve_action_script
from pydoll_mcp_server.tools.text_ranking import element_find_by_text_candidates
from pydoll_mcp_server.tools.upload_trigger import upload_files_from_trigger

logger = logging.getLogger(__name__)


async def _linkedin_easy_apply_upload_resume(
    client_id: str,
    tab_id: str,
    path: str,
    expected_filename: str | None = None,
    timeout_ms: int = 30000,
) -> JsonObject:
    """Upload a permitted resume path and verify the visible upload result."""
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_snapshot

    filename = expected_filename or Path(path).name
    input_resolution: JsonObject
    try:
        input_resolution = await _execute_script(
            client_id,
            tab_id,
            resolve_action_script('file_input'),
            'LinkedIn resume input resolution failed',
        )
    except (KeyError, PydollException, OSError, TypeError, ValueError) as exc:
        input_resolution = {
            'success': False,
            'reason': 'file_input_resolution_error',
            'error': str(exc),
        }
    target = get_object(input_resolution, 'target', {})
    selector = get_string(target, 'selector_hint')
    click_result: JsonObject = {
        'success': True,
        'action': 'upload',
        'skipped': bool(selector),
        'reason': 'file_input_already_mounted' if selector else 'file_input_not_mounted',
    }
    if not selector:
        upload_resolution: JsonObject
        try:
            upload_resolution = await _execute_script(
                client_id,
                tab_id,
                resolve_action_script('upload'),
                'LinkedIn resume upload control resolution failed',
            )
        except (KeyError, PydollException, OSError, TypeError, ValueError) as exc:
            upload_resolution = {
                'success': False,
                'reason': 'upload_control_resolution_error',
                'error': str(exc),
            }
        upload_target = get_object(upload_resolution, 'target', {})
        upload_selector = get_string(upload_target, 'selector_hint')
        if upload_selector:
            click_result = await _upload_with_file_chooser(
                client_id,
                tab_id,
                upload_selector,
                path,
                timeout_ms,
            )
        else:
            localized_result = await upload_from_localized_trigger(client_id, tab_id, path, filename, timeout_ms)
            if localized_result is None:
                click_result = await _click_resolved_action(
                    client_id,
                    tab_id,
                    'upload',
                    timeout_ms,
                    require_effect=False,
                )
            else:
                click_result = localized_result
        if not get_bool(click_result, 'success'):
            return click_result
        input_deadline = time.monotonic() + max(1, timeout_ms) / 1000
        while time.monotonic() < input_deadline:
            try:
                input_resolution = await _execute_script(
                    client_id,
                    tab_id,
                    resolve_action_script('file_input'),
                    'LinkedIn resume input resolution failed',
                )
            except (KeyError, PydollException, OSError, TypeError, ValueError) as exc:
                input_resolution = {
                    'success': False,
                    'reason': 'file_input_resolution_error',
                    'error': str(exc),
                }
            target = get_object(input_resolution, 'target', {})
            selector = get_string(target, 'selector_hint')
            if selector:
                break
            await asyncio.sleep(0.25)
    strategy_used = get_string(click_result, 'strategy_used')
    if not selector and strategy_used not in {'direct_input', 'chooser_intercept', 'desktop_picker'}:
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            'LinkedIn Easy Apply file input was not resolved after opening the upload control',
            retryable=True,
            details={'resolution': input_resolution, 'click': click_result},
            recovery_hint=(
                'Use an artifact path or a desktop automation boundary when LinkedIn opens a native file chooser.'
            ),
        ).to_dict()
    if strategy_used in {'direct_input', 'chooser_intercept', 'desktop_picker'}:
        upload_result = click_result
    else:
        file_input = await element_find(client_id, tab_id, selector=selector, timeout=max(1, timeout_ms / 1000))
        upload_result = file_input
        if get_bool(file_input, 'success'):
            element_id = get_string(file_input, 'element_id')
            upload_result = await upload_files(
                client_id,
                tab_id,
                element_id=element_id,
                paths=[path],
                expect_filename_visible=True,
                verify_timeout=max(1, timeout_ms / 1000),
            )
        if not get_bool(upload_result, 'success'):
            # Some LinkedIn React surfaces expose a stale or non-file wrapper
            # for input[type=file]. Retry through the visible upload trigger.
            upload_resolution = await _execute_script(
                client_id,
                tab_id,
                resolve_action_script('upload'),
                'LinkedIn resume upload control resolution failed',
            )
            upload_target = get_object(upload_resolution, 'target', {})
            upload_selector = get_string(upload_target, 'selector_hint')
            if not upload_selector:
                localized_result = await upload_from_localized_trigger(client_id, tab_id, path, filename, timeout_ms)
                if localized_result is None:
                    return upload_result
                click_result = localized_result
            else:
                click_result = await _upload_with_file_chooser(
                    client_id,
                    tab_id,
                    upload_selector,
                    path,
                    timeout_ms,
                )
            if not get_bool(click_result, 'success'):
                return click_result
            strategy_used = get_string(click_result, 'strategy_used')
            upload_result = click_result

    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    latest: JsonObject = {}
    filename_visible = False
    toast_confirmed = False
    verification_basis: JsonArray = []
    inline_errors: JsonArray = []
    while time.monotonic() < deadline:
        latest = await linkedin_easy_apply_snapshot(client_id, tab_id, include_resume_entries=True)
        filename_visible = _filename_visible(latest, filename)
        toast_confirmed = _has_upload_success_toast(latest)
        inline_errors = get_array(latest, 'inline_errors', [])
        verification_basis = _upload_verification_basis(latest, filename, filename_visible, toast_confirmed)
        if verification_basis and not inline_errors:
            break
        await asyncio.sleep(0.5)
    uploads = get_object(latest, 'uploads', {})
    toast_messages = get_array(latest, 'toast_messages', [])
    upload_verified = bool(verification_basis) and not inline_errors
    result: JsonObject = {
        'success': upload_verified,
        'uploaded': upload_verified,
        'upload_verified': upload_verified,
        'filename': filename,
        'new_upload_visible': filename_visible,
        'toast_confirmed': toast_confirmed,
        'verification_basis': verification_basis,
        'selected_resume': get_string(uploads, 'selected_resume', get_string(uploads, 'selected_or_latest_resume', '')),
        'uploaded_resume': filename if filename_visible else '',
        'selected_or_latest_resume': get_string(uploads, 'selected_or_latest_resume', ''),
        'resume_entries_returned': len(get_array(uploads, 'resume_entries', [])),
        'toast_messages': toast_messages,
        'inline_errors': inline_errors,
        'snapshot': latest,
        'upload': upload_result,
        'click': click_result,
    }
    if not result['success']:
        result['error_code'] = ErrorCode.TIMEOUT.value
        result['message'] = 'LinkedIn did not provide upload confirmation within the timeout'
        result['retryable'] = True
    return result


async def upload_from_localized_trigger(
    client_id: str,
    tab_id: str,
    path: str,
    filename: str,
    timeout_ms: int,
) -> JsonObject | None:
    """Use the visible upload label when a portal hides or replaces its file input."""
    labels = ('Upload resume', 'Cargar currículum', 'Carregar currículo', 'Carregar curriculo')
    for label in labels:
        candidates = await element_find_by_text_candidates(
            client_id,
            tab_id,
            label,
            exact=False,
            tag='label',
            prefer_modal=True,
            prefer_visible_center=True,
            max_candidates=5,
        )
        for candidate in get_array(candidates, 'candidates', []):
            if not isinstance(candidate, dict):
                continue
            trigger_element_id = get_string(candidate, 'element_id')
            if not trigger_element_id or not get_bool(candidate, 'enabled', True):
                continue
            return await upload_files_from_trigger(
                client_id=client_id,
                tab_id=tab_id,
                trigger_element_id=trigger_element_id,
                paths=[path],
                picker_strategy='auto',
                expected_filenames=[filename],
                timeout_ms=timeout_ms,
            )
    return None


async def linkedin_easy_apply_upload_resume(
    client_id: str,
    tab_id: str,
    path: str,
    expected_filename: str | None = None,
    timeout_ms: int = 30000,
) -> JsonObject:
    """Upload a resume and convert unexpected adapter failures to MCP errors."""
    try:
        return await _linkedin_easy_apply_upload_resume(
            client_id,
            tab_id,
            path,
            expected_filename,
            timeout_ms,
        )
    except (KeyError, PydollException, OSError, TypeError, ValueError) as exc:
        logger.exception('LinkedIn resume upload adapter error')
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'LinkedIn resume upload failed: {exc}',
            retryable=True,
            details={'reason': 'upload_adapter_error'},
        ).to_dict()


def _upload_verification_basis(
    snapshot: JsonObject,
    filename: str,
    filename_visible: bool,
    toast_confirmed: bool,
) -> JsonArray:
    uploads = get_object(snapshot, 'uploads', {})
    selected = get_string(uploads, 'selected_resume', get_string(uploads, 'selected_or_latest_resume', ''))
    basis: JsonArray = []
    if filename_visible and filename in selected:
        basis.append('selected_resume')
    elif filename_visible:
        basis.append('visible_filename')
    input_names = get_array(uploads, 'input_file_names', [])
    if any(isinstance(value, str) and filename in value for value in input_names):
        basis.append('file_input')
    if toast_confirmed:
        basis.append('success_toast')
    return basis
