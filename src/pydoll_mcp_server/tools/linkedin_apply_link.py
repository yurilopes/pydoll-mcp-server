"""Verified link fallback for LinkedIn Easy Apply surfaces."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_array, get_bool, get_string
from pydoll_mcp_server.tools.element_advanced import element_find_by_text
from pydoll_mcp_server.tools.elements import element_get_attribute
from pydoll_mcp_server.tools.page import page_goto

WaitReady = Callable[[str, str, int], Awaitable[JsonObject]]
SurfaceValidator = Callable[[JsonObject], bool]


def job_id_from_snapshot(snapshot: JsonObject) -> str:
    job_id = get_string(snapshot, 'linkedin_job_id')
    if job_id:
        return job_id
    for key in ('canonical_url', 'url'):
        value = get_string(snapshot, key)
        match = re.search(r'(?:/jobs/view/|[?&]currentJobId=)(\d+)', value)
        if match:
            return match.group(1)
    return ''


def job_identity_error(
    expected_job_id: str,
    snapshot: JsonObject,
    click_result: JsonObject,
) -> JsonObject | None:
    actual_job_id = job_id_from_snapshot(snapshot)
    if not expected_job_id or not actual_job_id or expected_job_id == actual_job_id:
        return None
    return StructuredError(
        ErrorCode.STALE_ELEMENT,
        'LinkedIn Easy Apply opened a different job than the active detail',
        retryable=True,
        details={
            'expected_job_id': expected_job_id,
            'actual_job_id': actual_job_id,
            'surface': get_string(snapshot, 'surface'),
            'url': get_string(snapshot, 'url'),
            'click_sent': get_bool(click_result, 'click_sent'),
        },
        recovery_hint='Navigate to the canonical job URL, re-read its detail, and retry only after the job ID matches.',
    ).to_dict()


async def open_verified_apply_link(
    client_id: str,
    tab_id: str,
    expected_job_id: str,
    timeout_ms: int,
    wait_ready: WaitReady,
    is_surface: SurfaceValidator,
) -> JsonObject | None:
    """Navigate only through one Easy Apply anchor tied to the active job."""
    candidates = await element_find_by_text(
        client_id,
        tab_id,
        'Candidatura simplificada',
        exact=False,
        find_all=True,
    )
    if not get_bool(candidates, 'success'):
        return None

    matching_links: list[tuple[str, str, JsonObject]] = []
    for item in get_array(candidates, 'elements', []):
        if not isinstance(item, dict) or get_string(item, 'tag').lower() != 'a':
            continue
        element_id = get_string(item, 'element_id')
        if not element_id:
            continue
        href_result = await element_get_attribute(client_id, tab_id, element_id, 'href')
        href = get_string(href_result, 'value')
        href_job_id = job_id_from_snapshot({'url': href})
        if not href or not href_job_id or (expected_job_id and href_job_id != expected_job_id):
            continue
        matching_links.append((element_id, href, item))

    if len(matching_links) != 1:
        return None

    element_id, href, target = matching_links[0]
    navigation = await page_goto(client_id, tab_id, href, timeout=max(1, timeout_ms / 1000))
    if not get_bool(navigation, 'success'):
        return navigation
    ready = await wait_ready(client_id, tab_id, timeout_ms)
    mismatch = job_identity_error(expected_job_id, ready, {'click_sent': False})
    if mismatch is not None:
        return mismatch
    if not is_surface(ready):
        return StructuredError(
            ErrorCode.NO_EFFECT,
            'LinkedIn Easy Apply link navigation did not expose a confirmed application surface',
            retryable=True,
            details={'target': target, 'navigation': navigation, 'snapshot': ready},
            recovery_hint='Re-read the active job and retry after the Easy Apply link finishes rendering.',
        ).to_dict()
    ready['open_mode'] = 'direct_apply_link'
    ready['navigation_fallback'] = True
    ready['navigation'] = navigation
    ready['target'] = {'element_id': element_id, 'href': href, **target}
    ready['click_sent'] = False
    ready['effect_observed'] = True
    ready['effect_type'] = 'easy_apply_surface'
    ready['recovery_attempted'] = True
    return ready
