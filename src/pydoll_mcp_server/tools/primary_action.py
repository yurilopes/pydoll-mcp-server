"""Primary action detection and step progression tool."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated

from pydantic import Field
from pydoll.browser.tab import Tab
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.pydoll_compat import get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.tab_reconciliation import sync_browser_tabs
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_object, get_string, require_json_object
from pydoll_mcp_server.security.site_signals import inspect_element_security
from pydoll_mcp_server.tools.active_surface import page_get_active_surface
from pydoll_mcp_server.tools.element_resolver import resolve_element_for_action
from pydoll_mcp_server.tools.form_runtime import advance_mutation_epoch


async def page_click_primary_action(
    client_id: str,
    tab_id: str,
    scope: Annotated[
        str,
        Field(
            description='Surface scope hint: auto, modal, dialog, form, or main.',
            json_schema_extra={'enum': ['auto', 'modal', 'dialog', 'form', 'main']},
        ),
    ] = 'auto',
    button_text_any: Annotated[
        list[str] | None,
        Field(description='Optional ordered button text candidates for the primary action.'),
    ] = None,
    expected_next_text: Annotated[
        str,
        Field(description='Optional text expected after advancing the active surface.'),
    ] = '',
    expected_progress_change: Annotated[
        bool,
        Field(description='Require progress metadata to change after the click when true.'),
    ] = False,
    timeout: Annotated[float | None, Field(description='Optional action and verification timeout.')] = None,
) -> JsonObject:
    btn_texts = button_text_any or []

    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    before_surface = await page_get_active_surface(client_id, tab_id, scope=scope)
    if not before_surface.get('success'):
        return before_surface

    before_progress = get_object(before_surface, 'progress', {})
    primary = get_object(before_surface, 'primary_action', {})
    secondary = get_array(before_surface, 'secondary_actions', [])

    target = primary
    if btn_texts:
        target = _match_by_text(primary, secondary, btn_texts)

    if not target or not target.get('element_id'):
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            'No primary action found on the active surface.',
            retryable=False,
            recovery_hint='Use page_get_active_surface to inspect available controls.',
        ).to_dict()

    target_el_id = str(target['element_id'])
    before_target_ids = {
        tab.target_id for tab in get_registry().list_tabs(client_id, tab_info.browser_id) if tab.target_id
    }

    clicked = False
    before_url = ''
    try:
        tab = tab_info.pydoll_tab
        before_url = await _safe_tab_url(tab)
        async with tab_operation_lock(tab_id):
            resolution = await resolve_element_for_action(tab_info, target_el_id)
            element = resolution.element
            if resolution.error is not None:
                element = await tab.query(
                    str(target.get('selector_hint', '')),
                    timeout=2,
                    find_all=False,
                    raise_exc=False,
                )
                if element is None:
                    response = resolution.error.to_dict()
                    response['failure_origin'] = 'resolution'
                    return response
            if element is None:
                return StructuredError(ErrorCode.STALE_ELEMENT, f'Primary action {target_el_id} is stale.').to_dict()
            security_control = await inspect_element_security(element)
            if security_control:
                response = StructuredError(
                    ErrorCode.SECURITY_CONTROL_PRESENT,
                    'The primary action is a security control that requires user action.',
                    details={'security_control': security_control},
                    recovery_hint='Ask the user to complete the security control, then re-observe the surface.',
                ).to_dict()
                response['failure_origin'] = 'security'
                return response
            advance_mutation_epoch(client_id, tab_id, 'primary_action', tab_info)
            await element.execute_script("this.scrollIntoView({block:'center'}); return true;", return_by_value=True)
            await element.click()
            clicked = True
    except PydollException as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Primary action click failed: {exc}',
            retryable=True,
        ).to_dict()

    if expected_next_text or expected_progress_change:
        after_surface = await _wait_for_surface_effect(
            client_id,
            tab_id,
            scope,
            before_surface,
            before_url,
            min(timeout or 5.0, 30.0),
        )
    else:
        after_surface = await page_get_active_surface(client_id, tab_id, scope=scope)
    new_tabs: JsonArray = []
    try:
        await sync_browser_tabs(client_id, tab_info.browser_id)
        for candidate in get_registry().list_tabs(client_id, tab_info.browser_id):
            if candidate.target_id and candidate.target_id not in before_target_ids:
                new_tabs.append(
                    {
                        'target_id': candidate.target_id,
                        'tab_id': candidate.tab_id,
                        'url': candidate.url,
                        'title': candidate.title,
                        'opener_tab_id': tab_id,
                        'provenance': 'primary_action',
                    }
                )
    except (PydollException, StructuredError, RuntimeError, TimeoutError, OSError):
        new_tabs = []
    after_progress = get_object(after_surface, 'progress', {}) if after_surface.get('success') else {}
    after_errors = get_array(after_surface, 'errors', []) if after_surface.get('success') else []
    after_pending = get_array(after_surface, 'pending_required', []) if after_surface.get('success') else []

    before_step = get_object(before_surface, 'surface', {})
    after_step = get_object(after_surface, 'surface', {}) if after_surface.get('success') else {}

    effect_observed = _check_effect(
        expected_next_text, expected_progress_change, before_progress, after_progress, after_surface
    )
    evidence: JsonObject = {
        'timestamp': time.time(),
        'clicked': clicked,
        'effect_observed': effect_observed,
        'new_tabs': new_tabs,
    }

    warnings: JsonArray = []
    if not effect_observed and (expected_next_text or expected_progress_change):
        warnings.append('Requested effect was not observed.')

    diagnostics = get_object(after_surface, 'site_diagnostics', {}) if after_surface.get('success') else {}
    page_effect: JsonObject = {
        'expectation': {'next_text': expected_next_text, 'progress_change': expected_progress_change},
        'observed': effect_observed,
        'before_url': before_url,
        'after_url': await _safe_tab_url(tab),
        'evidence': evidence,
    }
    if (expected_next_text or expected_progress_change) and not effect_observed:
        response = StructuredError(
            ErrorCode.NO_EFFECT,
            'The primary action was sent, but the expected step effect was not observed.',
            details={'page_effect': page_effect, 'site_diagnostics': diagnostics},
            retryable=True,
        ).to_dict()
        response.update(
            {
                'clicked': clicked,
                'button': {'element_id': target_el_id, 'name': target.get('name', ''), 'tag': target.get('tag', '')},
                'new_tabs': new_tabs,
                'page_effect': page_effect,
                'site_diagnostics': diagnostics,
                'failure_origin': 'page',
            }
        )
        return response

    return {
        'success': True,
        'clicked': clicked,
        'effect_observed': effect_observed,
        'new_tabs': new_tabs,
        'button': {
            'element_id': target_el_id,
            'name': target.get('name', ''),
            'tag': target.get('tag', ''),
            'role': target.get('role', ''),
        },
        'previous_step': {
            'label': get_string(before_step, 'label', ''),
            'scope': get_string(before_step, 'scope', ''),
        },
        'new_step': {
            'label': get_string(after_step, 'label', ''),
            'scope': get_string(after_step, 'scope', ''),
        },
        'progress_before': before_progress,
        'progress_after': after_progress,
        'errors': after_errors,
        'pending_required': after_pending,
        'warnings': warnings,
        'evidence': evidence,
        'mcp_action': {'event_sent': clicked, 'element_id': target_el_id},
        'page_effect': page_effect,
        'site_diagnostics': diagnostics,
        'failure_origin': '',
    }


def _match_by_text(primary: JsonObject, secondary: JsonArray, texts: list[str]) -> JsonObject:
    primary_name = str(primary.get('name', '') or primary.get('text', '')).lower()
    for text in texts:
        if text.lower() in primary_name:
            return primary
    for item in secondary:
        item_obj = require_json_object(item, 'secondary')
        item_name = str(item_obj.get('name', '') or item_obj.get('text', '')).lower()
        for text in texts:
            if text.lower() in item_name:
                return item_obj
    return primary


def _check_effect(
    expected_next_text: str,
    expected_progress_change: bool,
    before_progress: JsonObject,
    after_progress: JsonObject,
    after_surface: JsonObject,
) -> bool:
    if expected_next_text:
        review_texts = get_array(after_surface, 'review_text', [])
        fields = get_array(after_surface, 'fields', [])
        all_text = (
            ' '.join(str(t) for t in review_texts)
            + ' '
            + ' '.join(str(f.get('label', '')) for f in fields if isinstance(f, dict))
        )
        if expected_next_text.lower() not in all_text.lower():
            return False

    if expected_progress_change:
        before_current = before_progress.get('current')
        after_current = after_progress.get('current')
        if before_current == after_current or after_current is None:
            return False

    return True


async def _wait_for_surface_effect(
    client_id: str,
    tab_id: str,
    scope: str,
    before_surface: JsonObject,
    before_url: str,
    timeout: float,
) -> JsonObject:
    deadline = time.monotonic() + timeout
    delay = 0.08
    while time.monotonic() < deadline:
        current = await page_get_active_surface(client_id, tab_id, scope=scope)
        if not current.get('success'):
            await asyncio.sleep(delay)
            delay = min(0.8, delay * 1.6)
            continue
        current_url = await _safe_tab_url(get_registry().get_tab(client_id, tab_id).pydoll_tab)
        if _surface_changed(before_surface, current, before_url, current_url):
            return current
        await asyncio.sleep(delay)
        delay = min(0.8, delay * 1.6)
    return await page_get_active_surface(client_id, tab_id, scope=scope)


async def _safe_tab_url(tab: Tab) -> str:
    try:
        return await get_tab_url(tab)
    except (PydollException, TypeError, ValueError):
        return ''


def _surface_changed(
    before: JsonObject,
    current: JsonObject,
    before_url: str,
    current_url: str,
) -> bool:
    if before_url != current_url:
        return True
    before_step = get_object(before, 'surface', {})
    current_step = get_object(current, 'surface', {})
    if before_step != current_step:
        return True
    if get_object(before, 'progress', {}) != get_object(current, 'progress', {}):
        return True
    before_primary = get_object(before, 'primary_action', {})
    current_primary = get_object(current, 'primary_action', {})
    return get_string(before_primary, 'name', '') != get_string(current_primary, 'name', '')
