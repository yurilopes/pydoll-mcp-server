"""Primary action detection and step progression tool."""

from __future__ import annotations

import time

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_object, get_string, require_json_object
from pydoll_mcp_server.tools.active_surface import page_get_active_surface


async def page_click_primary_action(
    client_id: str,
    tab_id: str,
    scope: str = 'auto',
    button_text_any: list[str] | None = None,
    expected_next_text: str = '',
    expected_progress_change: bool = False,
    timeout: float | None = None,
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

    try:
        tab = tab_info.pydoll_tab
        element = await tab.query(
            str(target.get('selector_hint', '')),
            timeout=3,
            find_all=False,
            raise_exc=False,
        )

        async with tab_operation_lock(tab_id):
            if element is not None:
                await element.execute_script(
                    "this.scrollIntoView({block:'center'}); return true;", return_by_value=True
                )
                await element.click()
            else:
                return StructuredError(
                    ErrorCode.STALE_ELEMENT,
                    f'Primary action {target_el_id} is stale.',
                    retryable=False,
                    recovery_hint='Call page_get_active_surface again to get a fresh element_id.',
                ).to_dict()

        clicked = True
    except PydollException as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Primary action click failed: {exc}',
            retryable=True,
        ).to_dict()

    await _wait_stabilize(0.5)

    after_surface = await page_get_active_surface(client_id, tab_id, scope=scope)
    after_progress = get_object(after_surface, 'progress', {}) if after_surface.get('success') else {}
    after_errors = get_array(after_surface, 'errors', []) if after_surface.get('success') else []
    after_pending = get_array(after_surface, 'pending_required', []) if after_surface.get('success') else []

    effect_observed = _check_effect(
        expected_next_text, expected_progress_change, before_progress, after_progress, after_surface
    )

    before_step = get_object(before_surface, 'surface', {})
    after_step = get_object(after_surface, 'surface', {}) if after_surface.get('success') else {}

    evidence: JsonObject = {
        'timestamp': time.time(),
        'clicked': clicked,
        'effect_observed': effect_observed,
    }

    warnings: JsonArray = []
    if not effect_observed:
        warnings.append('Requested effect was not observed.')

    return {
        'success': True,
        'clicked': clicked,
        'effect_observed': effect_observed,
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


async def _wait_stabilize(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
