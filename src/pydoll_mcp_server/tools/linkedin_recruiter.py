"""LinkedIn recruiter messaging orchestration."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urljoin

from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_bool, get_string
from pydoll_mcp_server.tools.elements import element_fill, element_find
from pydoll_mcp_server.tools.linkedin import linkedin_job_snapshot
from pydoll_mcp_server.tools.linkedin_recruiter_scripts import (
    recruiter_confirmation_script,
    recruiter_surface_script,
)
from pydoll_mcp_server.tools.linkedin_runtime import (
    click_selector,
    execute_script,
)
from pydoll_mcp_server.tools.page import page_goto
from pydoll_mcp_server.tools.page_advanced import page_scroll


async def linkedin_message_recruiter(
    client_id: str,
    tab_id: str,
    message: str,
    timeout_ms: int = 20000,
) -> JsonObject:
    """Message the single recruiter listed on the current submitted LinkedIn job.

    The message is supplied by the caller. This tool resolves the recruiter,
    opens the existing LinkedIn message surface, fills and verifies the
    composer, sends once, and waits for visible confirmation.
    """
    started = time.monotonic()
    if not message.strip():
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'message must contain the text to send to the recruiter',
        ).to_dict()
    if len(message) > 2000:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'message must not exceed 2000 characters',
        ).to_dict()

    application = await linkedin_job_snapshot(client_id, tab_id)
    application_state = get_string(application, 'application_state')
    if application_state != 'submitted':
        return _failure(
            ErrorCode.APPLICATION_NOT_CONFIRMED,
            'The current LinkedIn job does not have a confirmed submitted application',
            started,
            application_state=application_state,
            last_snapshot=application,
            failure_origin='validation',
            message_length=len(message),
        )

    # LinkedIn commonly lazy-loads the hiring-team card below the initial viewport.
    await page_scroll(client_id, tab_id, delta_y=650)
    recruiter = await execute_script(
        client_id,
        tab_id,
        recruiter_surface_script(),
        'LinkedIn recruiter resolution failed',
    )
    recruiter = await _wait_for_recruiter(client_id, tab_id, recruiter, timeout_ms)
    if not get_bool(recruiter, 'success'):
        return _failure(
            ErrorCode.EXECUTION_ERROR,
            'LinkedIn recruiter resolution failed',
            started,
            application_state=application_state,
            recruiter=recruiter,
            failure_origin='resolution',
            last_snapshot=application,
            message_length=len(message),
        )
    message_href = get_string(recruiter, 'message_href')
    if message_href.startswith('/'):
        recruiter['message_href'] = urljoin(get_string(application, 'canonical_url'), message_href)
    if get_string(recruiter, 'resolution') == 'ambiguous':
        return _failure(
            ErrorCode.AMBIGUOUS_RECRUITER,
            'More than one recruiter is clearly associated with the current job',
            started,
            application_state=application_state,
            recruiter=recruiter,
            failure_origin='resolution',
            last_snapshot=application,
            message_length=len(message),
        )
    if not get_bool(recruiter, 'recruiter_found'):
        return _failure(
            ErrorCode.MESSAGE_UNAVAILABLE,
            'No uniquely associated recruiter with a direct Message action was found',
            started,
            application_state=application_state,
            recruiter=recruiter,
            failure_origin='resolution',
            last_snapshot=application,
            message_length=len(message),
        )

    message_selector = get_string(recruiter, 'message_button_selector')
    opened = await _click_selector(client_id, tab_id, message_selector, timeout_ms)
    if not get_bool(opened, 'success'):
        return _failure(
            ErrorCode.NO_EFFECT,
            'The recruiter message action could not be opened',
            started,
            application_state=application_state,
            recruiter=recruiter,
            click_sent=get_bool(opened, 'clicked'),
            failure_origin='page',
            last_snapshot=application,
            details={'open_action': opened},
            message_length=len(message),
        )

    composer = await _wait_for_surface(client_id, tab_id, timeout_ms)
    if not get_bool(composer, 'composer_present'):
        fallback_url = get_string(recruiter, 'message_href')
        if _is_message_compose_url(fallback_url):
            navigation = await page_goto(
                client_id,
                tab_id,
                fallback_url,
                timeout=max(1, timeout_ms / 1000),
            )
            if get_bool(navigation, 'success'):
                composer = await _wait_for_surface(client_id, tab_id, timeout_ms)
    if not get_bool(composer, 'composer_present'):
        return _failure(
            ErrorCode.TIMEOUT,
            'LinkedIn did not render a recruiter message composer',
            started,
            application_state=application_state,
            recruiter=recruiter,
            click_sent=True,
            failure_origin='timeout',
            last_snapshot=composer,
            message_length=len(message),
        )

    compose_selector = get_string(composer, 'composer_selector')
    compose_element = await element_find(client_id, tab_id, selector=compose_selector, timeout=5)
    if not get_bool(compose_element, 'success'):
        return _failure(
            ErrorCode.RESOURCE_NOT_FOUND,
            'LinkedIn recruiter message composer could not be resolved',
            started,
            application_state=application_state,
            recruiter=recruiter,
            click_sent=True,
            failure_origin='resolution',
            last_snapshot=composer,
        )
    filled = await element_fill(
        client_id,
        tab_id,
        get_string(compose_element, 'element_id'),
        message,
        verify=True,
        mode='auto',
        validation_timeout=min(max(timeout_ms / 1000, 1), 10),
    )
    if not get_bool(filled, 'success') or not get_bool(filled, 'verified', True):
        return _failure(
            ErrorCode.EXECUTION_ERROR,
            'LinkedIn recruiter message composer did not verify the requested text',
            started,
            application_state=application_state,
            recruiter=recruiter,
            click_sent=True,
            send_target_resolved=False,
            failure_origin='page',
            last_snapshot=composer,
            details={'fill': filled},
            message_length=len(message),
        )

    send_surface = await execute_script(
        client_id,
        tab_id,
        recruiter_surface_script(),
        'LinkedIn send action resolution failed',
    )
    send_selector = get_string(send_surface, 'send_button_selector')
    if not send_selector:
        return _failure(
            ErrorCode.MESSAGE_UNAVAILABLE,
            'LinkedIn did not expose an enabled Send action for the composed message',
            started,
            application_state=application_state,
            recruiter=recruiter,
            click_sent=True,
            failure_origin='resolution',
            last_snapshot=send_surface,
            details={'fill': filled},
            message_length=len(message),
        )

    sent = await _click_selector(client_id, tab_id, send_selector, timeout_ms)
    if not get_bool(sent, 'success'):
        return _failure(
            ErrorCode.NO_EFFECT,
            'The LinkedIn Send action was not completed',
            started,
            application_state=application_state,
            recruiter=recruiter,
            click_sent=get_bool(sent, 'clicked'),
            send_target_resolved=True,
            failure_origin='page',
            last_snapshot=send_surface,
            details={'fill': filled, 'send_action': sent},
            message_length=len(message),
        )

    confirmation = await _wait_for_confirmation(client_id, tab_id, message, timeout_ms)
    if not get_bool(confirmation, 'confirmation_observed'):
        return _failure(
            ErrorCode.NO_EFFECT,
            'The message click was sent but LinkedIn did not confirm delivery',
            started,
            application_state=application_state,
            recruiter=recruiter,
            click_sent=True,
            send_target_resolved=True,
            confirmation_observed=False,
            failure_origin='timeout',
            last_snapshot=confirmation,
            details={'fill': filled, 'send_action': sent},
            message_length=len(message),
        )
    return {
        'success': True,
        'sent': True,
        'recruiter': recruiter,
        'application_state': application_state,
        'message_length': len(message),
        'click_sent': True,
        'send_target_resolved': True,
        'confirmation_observed': True,
        'confirmation_text': get_string(confirmation, 'confirmation_text'),
        'elapsed_ms': int((time.monotonic() - started) * 1000),
        'failure_origin': '',
        'last_snapshot': confirmation,
    }


async def _click_selector(client_id: str, tab_id: str, selector: str, timeout_ms: int) -> JsonObject:
    if not selector:
        return StructuredError(ErrorCode.MESSAGE_UNAVAILABLE, 'Required LinkedIn action was not resolved').to_dict()
    found = await element_find(client_id, tab_id, selector=selector, timeout=max(1, timeout_ms / 1000))
    if not get_bool(found, 'success'):
        return found
    return await click_selector(
        client_id,
        tab_id,
        selector,
        timeout_ms,
        click_strategy='native',
    )


async def _wait_for_surface(client_id: str, tab_id: str, timeout_ms: int) -> JsonObject:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    last: JsonObject = {}
    while time.monotonic() < deadline:
        last = await execute_script(
            client_id,
            tab_id,
            recruiter_surface_script(),
            'LinkedIn message surface scan failed',
        )
        if get_bool(last, 'composer_present'):
            return last
        await asyncio.sleep(0.2)
    return last


async def _wait_for_recruiter(
    client_id: str,
    tab_id: str,
    initial: JsonObject,
    timeout_ms: int,
) -> JsonObject:
    if get_bool(initial, 'recruiter_found') or get_string(initial, 'resolution') == 'ambiguous':
        return initial
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    last = initial
    while time.monotonic() < deadline:
        await asyncio.sleep(0.25)
        last = await execute_script(
            client_id,
            tab_id,
            recruiter_surface_script(),
            'LinkedIn recruiter resolution failed',
        )
        if get_bool(last, 'recruiter_found') or get_string(last, 'resolution') == 'ambiguous':
            return last
    return last


async def _wait_for_confirmation(client_id: str, tab_id: str, message: str, timeout_ms: int) -> JsonObject:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    last: JsonObject = {}
    while time.monotonic() < deadline:
        last = await execute_script(
            client_id,
            tab_id,
            recruiter_confirmation_script(message),
            'LinkedIn message confirmation scan failed',
        )
        if get_bool(last, 'confirmation_observed'):
            return last
        await asyncio.sleep(0.25)
    return last


def _failure(
    code: ErrorCode,
    message: str,
    started: float,
    *,
    application_state: str = '',
    recruiter: JsonObject | None = None,
    click_sent: bool = False,
    send_target_resolved: bool = False,
    confirmation_observed: bool = False,
    failure_origin: str,
    last_snapshot: JsonObject | None = None,
    details: JsonObject | None = None,
    message_length: int = 0,
) -> JsonObject:
    payload: JsonObject = {
        'application_state': application_state,
        'message_length': message_length,
        'click_sent': click_sent,
        'send_target_resolved': send_target_resolved,
        'confirmation_observed': confirmation_observed,
        'confirmation_text': '',
        'elapsed_ms': int((time.monotonic() - started) * 1000),
        'failure_origin': failure_origin,
    }
    if recruiter is not None:
        payload['recruiter'] = recruiter
    if last_snapshot is not None:
        payload['last_snapshot'] = last_snapshot
    if details is not None:
        payload.update(details)
    return StructuredError(
        code,
        message,
        details=payload,
        retryable=code in {ErrorCode.NO_EFFECT, ErrorCode.TIMEOUT},
    ).to_dict()


def _is_message_compose_url(value: str) -> bool:
    return value.startswith('https://www.linkedin.com/messaging/compose/') and 'recipient=' in value
