"""LinkedIn Jobs search tools."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from typing import Literal
from urllib.parse import urlencode

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_bool,
    get_object,
    get_string,
    require_json_object,
)
from pydoll_mcp_server.tools.elements import element_click, element_find
from pydoll_mcp_server.tools.linkedin import linkedin_job_snapshot
from pydoll_mcp_server.tools.linkedin_search_scripts import (
    evidence_script,
    open_result_target_script,
    page_snapshot_script,
    search_results_script,
)
from pydoll_mcp_server.tools.page import page_goto

SortMode = Literal['relevance', 'recent']
DatePosted = Literal['any', 'past_24h', 'past_week', 'past_month']
ExperienceLevel = Literal['internship', 'entry', 'associate', 'mid_senior', 'director', 'executive']
JobType = Literal['full_time', 'part_time', 'contract', 'temporary', 'volunteer', 'internship', 'other']

DATE_POSTED_PARAMS: dict[str, str] = {
    'past_24h': 'r86400',
    'past_week': 'r604800',
    'past_month': 'r2592000',
}
EXPERIENCE_LEVEL_PARAMS: dict[str, str] = {
    'internship': '1',
    'entry': '2',
    'associate': '3',
    'mid_senior': '4',
    'director': '5',
    'executive': '6',
}
JOB_TYPE_PARAMS: dict[str, str] = {
    'full_time': 'F',
    'part_time': 'P',
    'contract': 'C',
    'temporary': 'T',
    'volunteer': 'V',
    'internship': 'I',
    'other': 'O',
}


async def linkedin_jobs_search(
    client_id: str,
    tab_id: str,
    keywords: str,
    location: str,
    remote: bool = True,
    easy_apply: bool = True,
    sort_by: SortMode = 'recent',
    date_posted: DatePosted = 'any',
    experience_levels: list[ExperienceLevel] | None = None,
    job_types: list[JobType] | None = None,
    geo_id: str = '',
    start: int | None = None,
    timeout_ms: int = 30000,
) -> JsonObject:
    try:
        url = linkedin_jobs_search_url(
            keywords=keywords,
            location=location,
            remote=remote,
            easy_apply=easy_apply,
            sort_by=sort_by,
            date_posted=date_posted,
            experience_levels=experience_levels,
            job_types=job_types,
            geo_id=geo_id,
            start=start,
        )
    except ValueError as exc:
        return StructuredError(ErrorCode.INVALID_INPUT, str(exc), retryable=False).to_dict()
    navigation = await page_goto(client_id, tab_id, url, timeout=max(1, timeout_ms / 1000))
    if navigation.get('success') is not True:
        return navigation
    results = await _wait_for_search_results(client_id, tab_id, timeout_ms)
    results['search_url'] = url
    results['navigation'] = navigation
    return results


async def linkedin_jobs_search_results(
    client_id: str,
    tab_id: str,
    max_results: int = 25,
) -> JsonObject:
    safe_max = max(1, min(max_results, 100))
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    try:
        result = await tab_info.pydoll_tab.execute_script(search_results_script(safe_max), return_by_value=True)
        return extract_script_object(result)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'LinkedIn jobs search results failed: {exc}',
            retryable=True,
        ).to_dict()


async def linkedin_jobs_page_snapshot(
    client_id: str,
    tab_id: str,
    max_results: int = 25,
) -> JsonObject:
    safe_max = max(1, min(max_results, 100))
    return await _execute_search_script(
        client_id,
        tab_id,
        page_snapshot_script(safe_max),
        'LinkedIn jobs page snapshot failed',
    )


async def linkedin_jobs_open_result(
    client_id: str,
    tab_id: str,
    linkedin_job_id: str | None = None,
    index: int | None = None,
    timeout_ms: int = 15000,
) -> JsonObject:
    if (linkedin_job_id is None) == (index is None):
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'Provide exactly one of linkedin_job_id or index',
            retryable=False,
        ).to_dict()

    results_response = await linkedin_jobs_search_results(client_id, tab_id, max_results=100)
    if not get_bool(results_response, 'success'):
        return results_response
    target = _resolve_search_target(get_array(results_response, 'results', []), linkedin_job_id, index)
    if not target:
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, 'LinkedIn search result not found').to_dict()
    target_id = get_string(target, 'linkedin_job_id')

    resolution = await _execute_search_script(
        client_id,
        tab_id,
        open_result_target_script(target_id, index),
        'LinkedIn result target resolution failed',
    )
    card = get_object(resolution, 'card', {})
    link = get_object(resolution, 'link', {})
    for candidate in (card, link):
        selector = get_string(candidate, 'selector_hint')
        if not selector:
            continue
        found = await element_find(client_id, tab_id, selector=selector, timeout=max(1, timeout_ms / 1000))
        if not get_bool(found, 'success'):
            continue
        clicked = await element_click(
            client_id,
            tab_id,
            get_string(found, 'element_id'),
            timeout=max(1, timeout_ms / 1000),
            click_strategy='native',
        )
        if not get_bool(clicked, 'success'):
            continue
        snapshot = await _wait_for_opened_job(client_id, tab_id, target_id, timeout_ms)
        if get_string(snapshot, 'linkedin_job_id') == target_id:
            snapshot['opened_from_result'] = True
            snapshot['target'] = target
            snapshot['open_mode'] = (
                'direct'
                if '/jobs/view/' in get_string(snapshot, 'url') and not get_bool(snapshot, 'detail_panel_present')
                else 'panel'
            )
            snapshot['search_context_preserved'] = get_string(snapshot, 'open_mode') == 'panel'
            return snapshot

    fallback_url = f'https://www.linkedin.com/jobs/view/{target_id}/'
    navigation = await page_goto(client_id, tab_id, fallback_url, timeout=max(1, timeout_ms / 1000))
    if navigation.get('success') is not True:
        return navigation
    snapshot = await linkedin_job_snapshot(client_id, tab_id)
    snapshot['opened_from_result'] = False
    snapshot['fallback_navigation'] = True
    snapshot['target'] = target
    snapshot['open_mode'] = 'fallback'
    snapshot['search_context_preserved'] = False
    return snapshot


async def linkedin_application_evidence(
    client_id: str,
    tab_id: str,
    include_review: bool = True,
) -> JsonObject:
    return await _execute_search_script(
        client_id,
        tab_id,
        evidence_script(include_review=include_review),
        'LinkedIn application evidence failed',
    )


def linkedin_jobs_search_url(
    keywords: str,
    location: str,
    remote: bool = True,
    easy_apply: bool = True,
    sort_by: SortMode = 'recent',
    date_posted: DatePosted = 'any',
    experience_levels: list[ExperienceLevel] | None = None,
    job_types: list[JobType] | None = None,
    geo_id: str = '',
    start: int | None = None,
) -> str:
    params: dict[str, str] = {
        'keywords': keywords.strip(),
        'location': location.strip(),
    }
    if remote:
        params['f_WT'] = '2'
    if easy_apply:
        params['f_AL'] = 'true'
    if sort_by == 'recent':
        params['sortBy'] = 'R'
    elif sort_by != 'relevance':
        raise ValueError('sort_by must be relevance or recent')
    if date_posted != 'any':
        date_value = DATE_POSTED_PARAMS.get(date_posted)
        if date_value is None:
            raise ValueError('date_posted must be any, past_24h, past_week, or past_month')
        params['f_TPR'] = date_value
    if experience_levels:
        params['f_E'] = ','.join(_map_values(experience_levels, EXPERIENCE_LEVEL_PARAMS, 'experience_levels'))
    if job_types:
        params['f_JT'] = ','.join(_map_values(job_types, JOB_TYPE_PARAMS, 'job_types'))
    if geo_id.strip():
        params['geoId'] = geo_id.strip()
    if start is not None:
        if start < 0:
            raise ValueError('start must be zero or greater')
        params['start'] = str(start)
    return f'https://www.linkedin.com/jobs/search/?{urlencode(params)}'


def _map_values(values: Sequence[str], mapping: dict[str, str], field_name: str) -> list[str]:
    mapped: list[str] = []
    for value in values:
        item = mapping.get(value)
        if item is None:
            raise ValueError(f'{field_name} contains unsupported value: {value}')
        mapped.append(item)
    return mapped


def _resolve_search_target(results: JsonArray, linkedin_job_id: str | None, index: int | None) -> JsonObject:
    if linkedin_job_id is not None:
        for item in results:
            obj = require_json_object(item, 'search result')
            if get_string(obj, 'linkedin_job_id') == linkedin_job_id:
                return obj
        return {}
    if index is None or index < 0 or index >= len(results):
        return {}
    return require_json_object(results[index], 'search result')


async def _wait_for_opened_job(client_id: str, tab_id: str, target_id: str, timeout_ms: int) -> JsonObject:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    snapshot: JsonObject = {}
    while time.monotonic() < deadline:
        page = await linkedin_jobs_page_snapshot(client_id, tab_id, max_results=25)
        detail = get_object(page, 'detail_job_snapshot', {})
        if get_string(detail, 'linkedin_job_id') == target_id:
            detail['detail_panel_present'] = get_bool(page, 'detail_panel_present')
            detail['detail_surface'] = get_string(page, 'detail_surface')
            detail['url'] = get_string(page, 'detail_url', get_string(detail, 'url'))
            return detail
        snapshot = await linkedin_job_snapshot(client_id, tab_id)
        if get_string(snapshot, 'linkedin_job_id') == target_id:
            return snapshot
        await asyncio.sleep(0.25)
    return snapshot


async def _wait_for_search_results(client_id: str, tab_id: str, timeout_ms: int) -> JsonObject:
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    latest: JsonObject = {}
    while time.monotonic() < deadline:
        latest = await linkedin_jobs_search_results(client_id, tab_id, max_results=25)
        if not get_bool(latest, 'success'):
            return latest
        if get_array(latest, 'results', []) or get_bool(latest, 'no_results'):
            return latest
        await asyncio.sleep(0.25)
    return latest


async def _execute_search_script(client_id: str, tab_id: str, script: str, message: str) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    try:
        result = await tab_info.pydoll_tab.execute_script(script, return_by_value=True)
        return extract_script_object(result)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'{message}: {exc}', retryable=True).to_dict()
