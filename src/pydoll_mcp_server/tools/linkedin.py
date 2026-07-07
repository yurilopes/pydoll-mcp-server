"""LinkedIn Easy Apply tools."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TypedDict

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonObject,
    get_bool,
    get_string,
    normalize_json_value,
    require_json_object,
)
from pydoll_mcp_server.tools.elements import element_click, element_find
from pydoll_mcp_server.tools.files import upload_files
from pydoll_mcp_server.tools.linkedin_scripts import (
    click_dialog_button_script,
    click_forward_script,
    fill_questions_script,
    job_snapshot_script,
    snapshot_script,
)


class LinkedInQuestionAnswer(TypedDict, total=False):
    question_contains: str
    value: str | int | float | bool | None
    option_text: str


async def linkedin_job_snapshot(client_id: str, tab_id: str) -> JsonObject:
    return await _execute_script(client_id, tab_id, job_snapshot_script(), 'LinkedIn job snapshot failed')


async def linkedin_easy_apply_open(
    client_id: str,
    tab_id: str,
    timeout_ms: int = 15000,
) -> JsonObject:
    selector = (
        'button[aria-label*="candidatura simplificada"],'
        'button[aria-label*="Easy Apply"],'
        'button[aria-label*="easy apply"],'
        'button[aria-label*="Continuar"],'
        'button[aria-label*="Continue"]'
    )
    find_result = await element_find(client_id, tab_id, selector=selector, timeout=max(1, timeout_ms / 1000))
    if not get_bool(find_result, 'success'):
        return find_result
    element_id = get_string(find_result, 'element_id')
    click_result = await element_click(
        client_id,
        tab_id,
        element_id,
        timeout=max(1, timeout_ms / 1000),
        expect_dialog=True,
        effect_timeout=max(1, timeout_ms / 1000),
    )
    if not get_bool(click_result, 'success'):
        return click_result
    return await linkedin_easy_apply_wait_ready(client_id, tab_id, timeout_ms=timeout_ms)


async def linkedin_easy_apply_snapshot(
    client_id: str,
    tab_id: str,
    include_resume_entries: bool = False,
    max_resume_entries: int = 5,
) -> JsonObject:
    safe_max = max(1, min(max_resume_entries, 50))
    return await _execute_script(
        client_id,
        tab_id,
        snapshot_script(include_resume_entries=include_resume_entries, max_resume_entries=safe_max),
        'LinkedIn Easy Apply snapshot failed',
    )


async def linkedin_easy_apply_wait_ready(
    client_id: str,
    tab_id: str,
    timeout_ms: int = 15000,
) -> JsonObject:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    last_snapshot: JsonObject = {}
    while time.monotonic() < deadline:
        snapshot = await linkedin_easy_apply_snapshot(client_id, tab_id)
        last_snapshot = snapshot
        if not get_bool(snapshot, 'success'):
            return snapshot
        if _snapshot_ready(snapshot):
            return snapshot
        await asyncio.sleep(0.25)
    return {
        'success': False,
        'error_code': ErrorCode.TIMEOUT.value,
        'message': f'LinkedIn Easy Apply did not become ready within {timeout_ms}ms',
        'retryable': True,
        'last_snapshot': last_snapshot,
    }


async def linkedin_easy_apply_upload_resume(
    client_id: str,
    tab_id: str,
    path: str,
    expected_filename: str | None = None,
    timeout_ms: int = 30000,
) -> JsonObject:
    filename = expected_filename or Path(path).name
    click_result = await _click_dialog_button(client_id, tab_id, r'Carregar curr|Upload resume')
    if not get_bool(click_result, 'success'):
        return click_result

    file_input = await element_find(
        client_id,
        tab_id,
        selector='input[type="file"]',
        timeout=max(1, timeout_ms / 1000),
    )
    if not get_bool(file_input, 'success'):
        return file_input
    element_id = get_string(file_input, 'element_id')
    upload_result = await upload_files(
        client_id,
        tab_id,
        element_id=element_id,
        paths=[path],
        expect_filename_visible=False,
    )
    if not get_bool(upload_result, 'success'):
        return upload_result

    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    snapshot: JsonObject = {}
    while time.monotonic() < deadline:
        snapshot = await linkedin_easy_apply_snapshot(client_id, tab_id, include_resume_entries=True)
        if filename and filename in str(snapshot):
            break
        await asyncio.sleep(0.5)
    latest = require_json_object(snapshot.get('uploads', {}), 'uploads') if snapshot else {}
    return {
        'success': True,
        'uploaded': True,
        'filename': filename,
        'new_upload_visible': filename in str(snapshot),
        'selected_or_latest_resume': get_string(latest, 'selected_or_latest_resume', ''),
        'toast_messages': snapshot.get('toast_messages', []),
        'upload': upload_result,
    }


async def linkedin_easy_apply_click_next(
    client_id: str,
    tab_id: str,
    expected_current_step: int | None = None,
) -> JsonObject:
    if expected_current_step is not None:
        current = await linkedin_easy_apply_snapshot(client_id, tab_id)
        step_index = current.get('step_index')
        if step_index != expected_current_step:
            return StructuredError(
                ErrorCode.INVALID_INPUT,
                f'Expected LinkedIn Easy Apply step {expected_current_step}, found {step_index}',
                retryable=False,
            ).to_dict()
    click_result = await _execute_mutating_script(
        client_id,
        tab_id,
        click_forward_script(),
        'LinkedIn next click failed',
    )
    if not get_bool(click_result, 'success') or not get_bool(click_result, 'clicked'):
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f'LinkedIn forward action not found: {get_string(click_result, "reason", "unknown")}',
            retryable=True,
            details=click_result,
        ).to_dict()
    await asyncio.sleep(0.5)
    snapshot = await linkedin_easy_apply_wait_ready(client_id, tab_id, timeout_ms=10000)
    snapshot['click'] = click_result
    return snapshot


async def linkedin_easy_apply_fill_questions(
    client_id: str,
    tab_id: str,
    answers: list[LinkedInQuestionAnswer],
) -> JsonObject:
    normalized_answers = [_answer_to_json(answer) for answer in answers]
    result = await _execute_mutating_script(
        client_id,
        tab_id,
        fill_questions_script(normalized_answers),
        'LinkedIn Easy Apply question fill failed',
    )
    snapshot = await linkedin_easy_apply_snapshot(client_id, tab_id)
    result['snapshot'] = snapshot
    result['authorization_risk'] = get_bool(snapshot, 'authorization_risk') or bool(result.get('blockers'))
    result['risk_text'] = get_string(snapshot, 'risk_text', '')
    return result


async def linkedin_easy_apply_handle_save_prompt(
    client_id: str,
    tab_id: str,
    action: str,
) -> JsonObject:
    if action not in {'save', 'discard'}:
        return StructuredError(ErrorCode.INVALID_INPUT, 'action must be save or discard').to_dict()
    pattern = r'^Salvar$|^Save$' if action == 'save' else r'^Descartar$|^Discard$'
    snapshot = await linkedin_easy_apply_snapshot(client_id, tab_id)
    prompt = require_json_object(snapshot.get('blocking_prompt', {}), 'blocking_prompt')
    if not prompt:
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, 'No LinkedIn save prompt is visible').to_dict()
    click_result = await _click_dialog_button(client_id, tab_id, pattern)
    if not get_bool(click_result, 'success'):
        return click_result
    await asyncio.sleep(0.5)
    job_snapshot = await linkedin_job_snapshot(client_id, tab_id)
    job_snapshot['prompt_action'] = action
    job_snapshot['click'] = click_result
    return job_snapshot


async def linkedin_easy_apply_submit(
    client_id: str,
    tab_id: str,
    confirm_submit: bool = False,
    timeout_ms: int = 20000,
) -> JsonObject:
    if not confirm_submit:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'confirm_submit=true is required to submit a LinkedIn Easy Apply application',
            retryable=False,
        ).to_dict()
    snapshot = await linkedin_easy_apply_snapshot(client_id, tab_id)
    if not get_bool(snapshot, 'is_final_submit_step'):
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'LinkedIn Easy Apply is not on the final submit step',
            retryable=False,
            details=snapshot,
        ).to_dict()
    click_result = await _click_dialog_button(client_id, tab_id, r'Enviar candidatura|Submit application')
    if not get_bool(click_result, 'success'):
        return click_result

    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    last_snapshot: JsonObject = {}
    while time.monotonic() < deadline:
        post = await linkedin_easy_apply_snapshot(client_id, tab_id)
        last_snapshot = post
        if get_bool(post, 'submitted') or get_string(post, 'application_status') == 'submitted':
            return {
                'success': True,
                'submitted': True,
                'confirmation_text': get_string(post, 'confirmation_text', ''),
                'application_status': get_string(post, 'application_status', ''),
                'timestamp_text': get_string(post, 'timestamp_text', ''),
                'dialog_closed': not get_bool(post, 'dialog_present'),
                'click': click_result,
            }
        await asyncio.sleep(0.5)
    return StructuredError(
        ErrorCode.TIMEOUT,
        f'LinkedIn submit confirmation did not appear within {timeout_ms}ms',
        retryable=True,
        details=last_snapshot,
    ).to_dict()


async def _click_dialog_button(client_id: str, tab_id: str, pattern: str) -> JsonObject:
    result = await _execute_mutating_script(
        client_id,
        tab_id,
        click_dialog_button_script(pattern),
        'LinkedIn dialog button click failed',
    )
    if not get_bool(result, 'clicked'):
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f'LinkedIn dialog button not found for pattern: {pattern}',
            retryable=True,
            details=result,
        ).to_dict()
    result['success'] = True
    return result


async def _execute_script(client_id: str, tab_id: str, script: str, message: str) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    try:
        result = await tab_info.pydoll_tab.execute_script(script, return_by_value=True)
        return extract_script_object(result)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'{message}: {exc}', retryable=True).to_dict()


async def _execute_mutating_script(client_id: str, tab_id: str, script: str, message: str) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    try:
        async with tab_operation_lock(tab_id):
            result = await tab_info.pydoll_tab.execute_script(script, return_by_value=True)
        data = extract_script_object(result)
        data.setdefault('success', True)
        return data
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'{message}: {exc}', retryable=True).to_dict()


def _snapshot_ready(snapshot: JsonObject) -> bool:
    if get_bool(snapshot, 'submitted'):
        return True
    if not get_bool(snapshot, 'dialog_present'):
        return False
    if snapshot.get('blocking_prompt'):
        return True
    if snapshot.get('step_index') or snapshot.get('step_title'):
        return True
    return bool(snapshot.get('inline_errors'))


def _answer_to_json(answer: LinkedInQuestionAnswer) -> JsonObject:
    return require_json_object(
        {str(key): normalize_json_value(value, f'answers.{key}') for key, value in answer.items()},
        'answer',
    )
