"""LinkedIn Easy Apply resume upload helpers."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_array, get_bool, get_object, get_string
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


async def linkedin_easy_apply_upload_resume(
    client_id: str,
    tab_id: str,
    path: str,
    expected_filename: str | None = None,
    timeout_ms: int = 30000,
) -> JsonObject:
    """Upload a permitted resume path and verify the visible upload result."""
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_snapshot

    filename = expected_filename or Path(path).name
    input_resolution = await _execute_script(
        client_id,
        tab_id,
        resolve_action_script('file_input'),
        'LinkedIn resume input resolution failed',
    )
    target = get_object(input_resolution, 'target', {})
    selector = get_string(target, 'selector_hint')
    click_result: JsonObject = {
        'success': True,
        'action': 'upload',
        'skipped': bool(selector),
        'reason': 'file_input_already_mounted' if selector else 'file_input_not_mounted',
    }
    if not selector:
        if get_bool(input_resolution, 'native_picker_likely'):
            return StructuredError(
                ErrorCode.UNSUPPORTED,
                'LinkedIn uses a native File System Access picker instead of an input[type=file]',
                retryable=False,
                details={
                    'filename': filename,
                    'file_input_resolution': input_resolution,
                    'native_picker_opened': False,
                },
                recovery_hint=(
                    'Use a desktop automation boundary to select the allowed artifact in the Windows dialog, '
                    'then capture the upload toast with linkedin_easy_apply_snapshot.'
                ),
            ).to_dict()
        upload_resolution = await _execute_script(
            client_id,
            tab_id,
            resolve_action_script('upload'),
            'LinkedIn resume upload control resolution failed',
        )
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
            click_result = await _click_resolved_action(client_id, tab_id, 'upload', timeout_ms, require_effect=False)
        if not get_bool(click_result, 'success'):
            return click_result
        input_deadline = time.monotonic() + max(1, timeout_ms) / 1000
        while time.monotonic() < input_deadline:
            input_resolution = await _execute_script(
                client_id,
                tab_id,
                resolve_action_script('file_input'),
                'LinkedIn resume input resolution failed',
            )
            target = get_object(input_resolution, 'target', {})
            selector = get_string(target, 'selector_hint')
            if selector:
                break
            await asyncio.sleep(0.25)
    if not selector:
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            'LinkedIn Easy Apply file input was not resolved after opening the upload control',
            retryable=True,
            details={'resolution': input_resolution, 'click': click_result},
            recovery_hint=(
                'Use an artifact path or a desktop automation boundary when LinkedIn opens a native file chooser.'
            ),
        ).to_dict()
    file_input = await element_find(client_id, tab_id, selector=selector, timeout=max(1, timeout_ms / 1000))
    if not get_bool(file_input, 'success'):
        return file_input
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
        return upload_result

    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    latest: JsonObject = {}
    filename_visible = False
    toast_confirmed = False
    while time.monotonic() < deadline:
        latest = await linkedin_easy_apply_snapshot(client_id, tab_id, include_resume_entries=True)
        filename_visible = _filename_visible(latest, filename)
        toast_confirmed = _has_upload_success_toast(latest)
        if filename_visible and toast_confirmed:
            break
        await asyncio.sleep(0.5)
    uploads = get_object(latest, 'uploads', {})
    toast_messages = get_array(latest, 'toast_messages', [])
    result: JsonObject = {
        'success': filename_visible and toast_confirmed,
        'uploaded': True,
        'upload_verified': filename_visible and toast_confirmed,
        'filename': filename,
        'new_upload_visible': filename_visible,
        'toast_confirmed': toast_confirmed,
        'selected_or_latest_resume': get_string(uploads, 'selected_or_latest_resume', ''),
        'toast_messages': toast_messages,
        'inline_errors': latest.get('inline_errors', []),
        'snapshot': latest,
        'upload': upload_result,
        'click': click_result,
    }
    if not result['success']:
        result['error_code'] = ErrorCode.TIMEOUT.value
        result['message'] = 'LinkedIn did not confirm the resume filename and upload toast within the timeout'
        result['retryable'] = True
    return result
