"""Runtime helpers for LinkedIn surface actions and script execution."""

from __future__ import annotations

import asyncio
import time
import unicodedata

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_bool, get_object, get_string
from pydoll_mcp_server.tools.elements import element_click, element_find
from pydoll_mcp_server.tools.linkedin_choice_scripts import resolve_choice_script
from pydoll_mcp_server.tools.linkedin_scripts import action_state_script, resolve_action_script, set_choice_state_script
from pydoll_mcp_server.tools.upload_trigger import upload_files_from_trigger


async def click_resolved_action(
    client_id: str,
    tab_id: str,
    action: str,
    timeout_ms: int,
    require_effect: bool = True,
) -> JsonObject:
    before = await execute_script(
        client_id,
        tab_id,
        action_state_script(action),
        f'LinkedIn {action} pre-click state failed',
    )
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    last_resolution: JsonObject = {}
    last_after: JsonObject = {}
    last_target: JsonObject = {}
    attempts: JsonArray = []
    while time.monotonic() < deadline:
        resolution = await execute_script(
            client_id,
            tab_id,
            resolve_action_script(action),
            f'LinkedIn {action} action resolution failed',
        )
        last_resolution = resolution
        target = get_object(resolution, 'target', {})
        selector = get_string(target, 'selector_hint')
        if selector:
            last_target = target
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            click = await click_selector(client_id, tab_id, selector, remaining_ms, click_strategy='native')
            attempts.append({'strategy': 'native', 'target': target, 'result': click})
            if get_bool(click, 'success'):
                if not require_effect:
                    return _click_result(action, target, click, resolution, before, {}, False)
                after = await _wait_for_action_state(
                    client_id,
                    tab_id,
                    action,
                    before,
                    min(1500, max(1, int((deadline - time.monotonic()) * 1000))),
                )
                last_after = after
                if _action_effect_observed(action, before, after):
                    return _click_result(action, target, click, resolution, before, after, True)

                fallback_resolution = await execute_script(
                    client_id,
                    tab_id,
                    resolve_action_script(action),
                    f'LinkedIn {action} fallback resolution failed',
                )
                fallback_target = get_object(fallback_resolution, 'target', {})
                fallback_selector = get_string(fallback_target, 'selector_hint')
                if fallback_selector:
                    fallback_click = await click_selector(
                        client_id,
                        tab_id,
                        fallback_selector,
                        max(1, int((deadline - time.monotonic()) * 1000)),
                        click_strategy='dispatch_pointer_sequence',
                    )
                    attempts.append(
                        {'strategy': 'dispatch_pointer_sequence', 'target': fallback_target, 'result': fallback_click}
                    )
                    if get_bool(fallback_click, 'success'):
                        after = await _wait_for_action_state(
                            client_id,
                            tab_id,
                            action,
                            before,
                            min(2500, max(1, int((deadline - time.monotonic()) * 1000))),
                        )
                        last_after = after
                        if _action_effect_observed(action, before, after):
                            return _click_result(
                                action,
                                fallback_target,
                                fallback_click,
                                fallback_resolution,
                                before,
                                after,
                                True,
                                fallback_of=click,
                            )
                if require_effect:
                    return StructuredError(
                        ErrorCode.NO_EFFECT,
                        f'LinkedIn {action} click produced no observable state transition',
                        retryable=True,
                        details={
                            'action': action,
                            'resolved': last_target,
                            'before': before,
                            'after': last_after,
                            'resolution': resolution,
                            'attempts': attempts,
                        },
                        recovery_hint='Re-read the active surface and retry after LinkedIn finishes rendering.',
                    ).to_dict()
        await asyncio.sleep(0.2)
    return StructuredError(
        ErrorCode.RESOURCE_NOT_FOUND,
        f'LinkedIn {action} action was not resolved in the active surface',
        retryable=True,
        details=last_resolution,
    ).to_dict()


async def click_selector(
    client_id: str,
    tab_id: str,
    selector: str,
    timeout_ms: int,
    allow_hidden_choice_fallback: bool = False,
    click_strategy: str = 'native',
) -> JsonObject:
    if not selector:
        return StructuredError(ErrorCode.INVALID_INPUT, 'A non-empty selector is required').to_dict()
    found = await element_find(client_id, tab_id, selector=selector, timeout=max(1, timeout_ms / 1000))
    if not get_bool(found, 'success'):
        return found
    click = await element_click(
        client_id,
        tab_id,
        get_string(found, 'element_id'),
        timeout=max(1, timeout_ms / 1000),
        click_strategy=click_strategy,
    )
    if get_bool(click, 'success') or not allow_hidden_choice_fallback:
        return click
    return await execute_mutating_script(
        client_id,
        tab_id,
        set_choice_state_script(selector),
        'LinkedIn hidden choice fallback failed',
    )


async def click_linkedin_choice(
    client_id: str,
    tab_id: str,
    question_contains: str,
    option_text: str,
    timeout_ms: int = 10000,
) -> JsonObject:
    """Resolve and click a LinkedIn choice again after each React re-render."""
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    attempts: JsonArray = []
    while time.monotonic() < deadline and len(attempts) < 3:
        resolution = await execute_script(
            client_id,
            tab_id,
            resolve_choice_script(question_contains, option_text),
            'LinkedIn radio resolution failed',
        )
        if not get_bool(resolution, 'success'):
            reason = get_string(resolution, 'reason')
            attempts.append({'resolution': resolution})
            if reason in {'no_match', 'ambiguous_question', 'ambiguous_option', 'option_not_found'}:
                return {
                    'success': False,
                    'reason': reason,
                    'attempts': attempts,
                    'candidates': get_array(resolution, 'candidates', []),
                }
            await asyncio.sleep(0.1)
            continue
        if get_bool(resolution, 'selected'):
            return {
                'success': True,
                'selected': True,
                'verified': True,
                'status': 'already_filled',
                'strategy_used': 'already_selected',
                'attempts': attempts,
                'resolution': resolution,
            }
        selector = get_string(resolution, 'selector')
        click = await click_selector(
            client_id,
            tab_id,
            selector,
            max(1, int((deadline - time.monotonic()) * 1000)),
            allow_hidden_choice_fallback=True,
        )
        verify = await execute_script(
            client_id,
            tab_id,
            resolve_choice_script(question_contains, option_text),
            'LinkedIn radio verification failed',
        )
        attempt: JsonObject = {'resolution': resolution, 'click': click, 'verification': verify}
        attempts.append(attempt)
        if get_bool(click, 'success') and get_bool(verify, 'success') and get_bool(verify, 'selected'):
            return {
                'success': True,
                'clicked': True,
                'selected': True,
                'verified': True,
                'status': 'filled',
                'strategy_used': get_string(click, 'strategy_used', 'native'),
                'attempts': attempts,
                'resolution': verify,
            }
        await asyncio.sleep(0.1)
    return StructuredError(
        ErrorCode.STALE_ELEMENT,
        'LinkedIn radio control was replaced before selection could be verified',
        retryable=True,
        details={
            'question_contains': question_contains,
            'option_text': option_text,
            'attempts': attempts,
        },
        recovery_hint='Re-read the Easy Apply snapshot and retry the question after LinkedIn finishes rendering.',
    ).to_dict()


async def upload_with_file_chooser(
    client_id: str,
    tab_id: str,
    selector: str,
    path: str,
    timeout_ms: int,
) -> JsonObject:
    found = await element_find(client_id, tab_id, selector=selector, timeout=max(1, timeout_ms / 1000))
    if not get_bool(found, 'success'):
        return found
    element_id = get_string(found, 'element_id')
    if not element_id:
        return StructuredError(ErrorCode.STALE_ELEMENT, 'LinkedIn upload control was not resolved').to_dict()
    return await upload_files_from_trigger(
        client_id=client_id,
        tab_id=tab_id,
        trigger_element_id=element_id,
        paths=[path],
        picker_strategy='auto',
        expected_filenames=[path.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]],
        timeout_ms=timeout_ms,
    )


async def _wait_for_action_state(
    client_id: str,
    tab_id: str,
    action: str,
    before: JsonObject,
    timeout_ms: int,
) -> JsonObject:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    latest: JsonObject = {}
    while time.monotonic() < deadline:
        latest = await execute_script(
            client_id,
            tab_id,
            action_state_script(action),
            f'LinkedIn {action} post-click state failed',
        )
        if _action_effect_observed(action, before, latest):
            return latest
        await asyncio.sleep(0.1)
    return latest


def _action_effect_observed(action: str, before: JsonObject, after: JsonObject) -> bool:
    if not get_bool(after, 'success'):
        return False
    if action == 'apply':
        return get_bool(after, 'form_present') or get_bool(after, 'submitted') or get_bool(after, 'prompt_present')
    if action == 'forward':
        return (
            _state_value_changed(before, after, 'step_index')
            or _state_value_changed(before, after, 'step_count')
            or _state_value_changed(before, after, 'step_title')
            or _state_value_changed(before, after, 'primary_label')
            or _state_value_changed(before, after, 'content_signature')
        )
    if action == 'submit':
        return get_bool(after, 'submitted')
    if action == 'close':
        return get_bool(after, 'prompt_present') or not get_bool(after, 'form_present')
    if action in {'save', 'discard'}:
        return get_bool(before, 'prompt_present') and not get_bool(after, 'prompt_present')
    return False


def _state_value_changed(before: JsonObject, after: JsonObject, key: str) -> bool:
    return before.get(key) != after.get(key)


def _click_result(
    action: str,
    target: JsonObject,
    click: JsonObject,
    resolution: JsonObject,
    before: JsonObject,
    after: JsonObject,
    effect_observed: bool,
    fallback_of: JsonObject | None = None,
) -> JsonObject:
    result: JsonObject = {
        'success': True,
        'action': action,
        'click_sent': True,
        'target_resolved': True,
        'resolved': target,
        'click': click,
        'surface': resolution.get('surface', ''),
        'effect_observed': effect_observed,
        'effect_type': action if effect_observed else '',
        'before': before,
        'after': after,
    }
    if fallback_of:
        result['fallback_of'] = fallback_of
    return result


async def execute_script(client_id: str, tab_id: str, script: str, message: str) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    try:
        result = await tab_info.pydoll_tab.execute_script(script, return_by_value=True)
        return extract_script_object(result)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'{message}: {exc}', retryable=True).to_dict()


async def execute_mutating_script(client_id: str, tab_id: str, script: str, message: str) -> JsonObject:
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


def filename_visible(snapshot: JsonObject, filename: str) -> bool:
    uploads = get_object(snapshot, 'uploads', {})
    selected = get_string(uploads, 'selected_or_latest_resume', '')
    entries = get_array(uploads, 'resume_entries', [])
    return filename in selected or any(isinstance(entry, str) and filename in entry for entry in entries)


def has_upload_success_toast(snapshot: JsonObject) -> bool:
    for message in get_array(snapshot, 'toast_messages', []):
        if not isinstance(message, str):
            continue
        normalized = unicodedata.normalize('NFD', message.casefold())
        normalized = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
        if any(token in normalized for token in ('curriculo foi carregado', 'resume uploaded', 'file uploaded')):
            return True
    return False


def snapshot_ready(snapshot: JsonObject) -> bool:
    if get_bool(snapshot, 'submitted'):
        return True
    if get_object(snapshot, 'blocking_prompt', {}):
        return True
    if get_bool(snapshot, 'form_present'):
        return bool(
            snapshot.get('step_index')
            or snapshot.get('step_count')
            or get_object(snapshot, 'primary_action', {})
            or snapshot.get('fields')
            or snapshot.get('questions')
            or snapshot.get('inline_errors')
        )
    return bool(snapshot.get('inline_errors')) or get_string(snapshot, 'surface') == 'confirmation'
