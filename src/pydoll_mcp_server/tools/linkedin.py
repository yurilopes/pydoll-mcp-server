"""LinkedIn Easy Apply browser helpers."""

from __future__ import annotations

import asyncio
import time
from typing import TypedDict

from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonObject,
    get_array,
    get_bool,
    get_object,
    get_string,
    normalize_json_value,
    require_json_object,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    click_linkedin_choice as _click_linkedin_choice,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    click_resolved_action as _click_resolved_action,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    execute_mutating_script as _execute_mutating_script,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    execute_script as _execute_script,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    snapshot_ready as _snapshot_ready,
)
from pydoll_mcp_server.tools.linkedin_scripts import (
    fill_questions_script,
    job_snapshot_script,
    snapshot_script,
)
from pydoll_mcp_server.tools.linkedin_upload import (
    linkedin_easy_apply_upload_resume as _linkedin_easy_apply_upload_resume,
)


class LinkedInQuestionAnswer(TypedDict, total=False):
    question_contains: str
    value: str | int | float | bool | None
    option_text: str


async def linkedin_job_snapshot(client_id: str, tab_id: str) -> JsonObject:
    """Capture the active LinkedIn job detail and application state."""
    return await _execute_script(client_id, tab_id, job_snapshot_script(), 'LinkedIn job snapshot failed')


async def linkedin_easy_apply_upload_resume(
    client_id: str,
    tab_id: str,
    path: str,
    expected_filename: str | None = None,
    timeout_ms: int = 30000,
) -> JsonObject:
    return await _linkedin_easy_apply_upload_resume(client_id, tab_id, path, expected_filename, timeout_ms)


async def linkedin_easy_apply_open(
    client_id: str,
    tab_id: str,
    timeout_ms: int = 15000,
) -> JsonObject:
    """Open Easy Apply from the active job detail and return its first snapshot."""
    current = await linkedin_easy_apply_snapshot(client_id, tab_id)
    if get_bool(current, 'form_present') or get_bool(current, 'submitted'):
        return current
    click_result = await _click_resolved_action(client_id, tab_id, 'apply', timeout_ms)
    if not get_bool(click_result, 'success'):
        return click_result
    ready = await linkedin_easy_apply_wait_ready(client_id, tab_id, timeout_ms=timeout_ms)
    ready['open'] = click_result
    return ready


async def linkedin_easy_apply_snapshot(
    client_id: str,
    tab_id: str,
    include_resume_entries: bool = False,
    max_resume_entries: int = 5,
) -> JsonObject:
    """Capture the visible Easy Apply dialog or inline form only."""
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
    """Wait for an Easy Apply surface, blocking prompt, error, or confirmation."""
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    last_snapshot: JsonObject = {}
    title_signature = ''
    stable_title_reads = 0
    while time.monotonic() < deadline:
        snapshot = await linkedin_easy_apply_snapshot(client_id, tab_id)
        last_snapshot = snapshot
        if not get_bool(snapshot, 'success'):
            return snapshot
        if _snapshot_ready(snapshot):
            has_rich_state = bool(
                snapshot.get('step_index')
                or snapshot.get('step_count')
                or get_object(snapshot, 'primary_action', {})
                or snapshot.get('fields')
                or snapshot.get('questions')
                or snapshot.get('inline_errors')
                or snapshot.get('pending_required')
            )
            if has_rich_state:
                return snapshot
            current_signature = f'{get_string(snapshot, "surface")}:{get_string(snapshot, "step_title")}'
            if current_signature and current_signature == title_signature:
                stable_title_reads += 1
            else:
                title_signature = current_signature
                stable_title_reads = 1
            if stable_title_reads >= 2:
                return snapshot
        await asyncio.sleep(0.25)
    return {
        'success': False,
        'error_code': ErrorCode.TIMEOUT.value,
        'message': f'LinkedIn Easy Apply did not become ready within {timeout_ms}ms',
        'retryable': True,
        'last_snapshot': last_snapshot,
    }


async def linkedin_easy_apply_click_next(
    client_id: str,
    tab_id: str,
    expected_current_step: int | None = None,
) -> JsonObject:
    """Click only the forward action of the active Easy Apply surface."""
    if expected_current_step is not None:
        current = await linkedin_easy_apply_snapshot(client_id, tab_id)
        raw_step_index = current.get('step_index')
        step_index = (
            raw_step_index if isinstance(raw_step_index, int) and not isinstance(raw_step_index, bool) else None
        )
        if step_index != expected_current_step:
            return StructuredError(
                ErrorCode.INVALID_INPUT,
                f'Expected LinkedIn Easy Apply step {expected_current_step}, found {step_index}',
                retryable=False,
            ).to_dict()
    click_result = await _click_resolved_action(client_id, tab_id, 'forward', 10000)
    if not get_bool(click_result, 'success'):
        return click_result
    snapshot = await linkedin_easy_apply_wait_ready(client_id, tab_id, timeout_ms=10000)
    snapshot['click'] = click_result
    return snapshot


async def linkedin_easy_apply_fill_questions(
    client_id: str,
    tab_id: str,
    answers: list[LinkedInQuestionAnswer],
) -> JsonObject:
    """Fill explicitly provided Easy Apply answers and report unresolved questions."""
    normalized_answers = [_answer_to_json(answer) for answer in answers]
    result = await _execute_mutating_script(
        client_id,
        tab_id,
        fill_questions_script(normalized_answers),
        'LinkedIn Easy Apply question fill failed',
    )
    filled = get_array(result, 'filled', [])
    unfilled = get_array(result, 'unfilled', [])
    for action_value in get_array(result, 'radio_actions', []):
        action = require_json_object(action_value, 'radio action')
        question_contains = get_string(action, 'question_contains')
        option_text = get_string(action, 'option_text')
        click = await _click_linkedin_choice(
            client_id,
            tab_id,
            question_contains,
            option_text,
            timeout_ms=10000,
        )
        if get_bool(click, 'success'):
            filled.append(
                {
                    'question_contains': question_contains,
                    'matched_label': get_string(action, 'matched_label', get_string(click, 'matched_label')),
                    'option_text': option_text,
                    'verified': True,
                    'attempts': len(get_array(click, 'attempts', [])),
                }
            )
        else:
            unfilled.append(
                {
                    'question_contains': question_contains,
                    'matched_label': get_string(action, 'matched_label'),
                    'option_text': option_text,
                    'reason': get_string(click, 'reason', 'click_failed'),
                    'click_error': click,
                }
            )
    result['filled'] = filled
    result['unfilled'] = unfilled
    result['radio_actions'] = []
    result['success'] = len(unfilled) == 0 and len(get_array(result, 'ambiguous', [])) == 0
    snapshot = await linkedin_easy_apply_snapshot(client_id, tab_id)
    result['snapshot'] = snapshot
    result['authorization_risk'] = get_bool(snapshot, 'authorization_risk') or bool(get_array(result, 'blockers', []))
    result['risk_text'] = get_string(snapshot, 'risk_text', get_string(result, 'risk_text', ''))
    return result


async def linkedin_easy_apply_handle_save_prompt(
    client_id: str,
    tab_id: str,
    action: str,
) -> JsonObject:
    """Act on a visible LinkedIn save prompt without choosing an answer."""
    if action not in {'save', 'discard'}:
        return StructuredError(ErrorCode.INVALID_INPUT, 'action must be save or discard').to_dict()
    snapshot = await linkedin_easy_apply_snapshot(client_id, tab_id)
    if not get_object(snapshot, 'blocking_prompt', {}):
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, 'No LinkedIn save prompt is visible').to_dict()
    click_result = await _click_resolved_action(client_id, tab_id, action, 10000)
    if not get_bool(click_result, 'success'):
        return click_result
    await asyncio.sleep(0.5)
    job_snapshot = await linkedin_job_snapshot(client_id, tab_id)
    job_snapshot['prompt_action'] = action
    job_snapshot['click'] = click_result
    return job_snapshot


async def linkedin_easy_apply_close(client_id: str, tab_id: str) -> JsonObject:
    """Close Easy Apply and report whether LinkedIn opened a save prompt."""
    current = await linkedin_easy_apply_snapshot(client_id, tab_id)
    if not get_bool(current, 'form_present') and not get_bool(current, 'dialog_present'):
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, 'No LinkedIn Easy Apply surface is visible').to_dict()
    click_result = await _click_resolved_action(client_id, tab_id, 'close', 10000)
    if not get_bool(click_result, 'success'):
        return click_result
    await asyncio.sleep(0.5)
    after = await linkedin_easy_apply_snapshot(client_id, tab_id)
    return {
        'success': True,
        'closed': not get_bool(after, 'form_present') and not get_bool(after, 'dialog_present'),
        'save_prompt_visible': bool(get_object(after, 'blocking_prompt', {})),
        'snapshot': after,
        'click': click_result,
    }


async def linkedin_easy_apply_submit(
    client_id: str,
    tab_id: str,
    confirm_submit: bool = False,
    timeout_ms: int = 20000,
) -> JsonObject:
    """Submit only a verified final step when explicitly confirmed."""
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
    click_result = await _click_resolved_action(client_id, tab_id, 'submit', timeout_ms)
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
                'dialog_closed': not get_bool(post, 'dialog_present') and not get_bool(post, 'form_present'),
                'surface': get_string(post, 'surface', ''),
                'click': click_result,
            }
        await asyncio.sleep(0.5)
    return StructuredError(
        ErrorCode.TIMEOUT,
        f'LinkedIn submit confirmation did not appear within {timeout_ms}ms',
        retryable=True,
        details={'last_snapshot': last_snapshot, 'click': click_result},
    ).to_dict()


def _answer_to_json(answer: LinkedInQuestionAnswer) -> JsonObject:
    return require_json_object(
        {str(key): normalize_json_value(value, f'answers.{key}') for key, value in answer.items()},
        'answer',
    )
