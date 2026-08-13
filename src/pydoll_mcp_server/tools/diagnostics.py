"""Health, diagnostics, tracing, and safe attach tools."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from pydoll_mcp_server.browser.locks import browser_operation_lock
from pydoll_mcp_server.browser.models import ProfileInfo, ProfileMode
from pydoll_mcp_server.browser.profile_index import get_profile_index
from pydoll_mcp_server.browser.profile_leases import get_profile_lease_manager
from pydoll_mcp_server.browser.pydoll_compat import (
    create_chromium_options,
    get_browser_ws_address,
    get_tab_target_id,
    get_tab_title,
    get_tab_url,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.tab_reconciliation import TabSyncResult, sync_browser_tabs
from pydoll_mcp_server.config import get_config, get_limits_config
from pydoll_mcp_server.diagnostics.trace import TraceEvent, get_trace_manager
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject
from pydoll_mcp_server.server_state import SCHEMA_VERSION, get_server_state
from pydoll_mcp_server.tool_metadata import PUBLIC_TOOL_NAMES, tool_names_for_profile
from pydoll_mcp_server.tool_runtime import get_active_tool_count, get_active_tool_profile
from pydoll_mcp_server.version import get_version


def health_check(include_runtime: bool = False) -> JsonObject:
    config = get_config()
    state = get_server_state()
    result: JsonObject = {
        'status': 'ok',
        'version': get_version(),
        'schema_version': SCHEMA_VERSION,
        'uptime_seconds': round(state.uptime_seconds, 1),
        'auth_mode': 'token' if config.auth_enabled else 'none',
    }
    if include_runtime:
        result['runtime'] = state.summary()
    return result


async def server_status(
    client_id: str = 'anonymous',
    include_clients: bool = False,
    include_tool_names: bool = False,
) -> JsonObject:
    registry = get_registry()
    config = get_config()
    state = get_server_state()
    result: JsonObject = {
        'status': 'ok',
        'version': get_version(),
        'schema_version': SCHEMA_VERSION,
        'uptime_seconds': round(state.uptime_seconds, 1),
        'auth_mode': 'token' if config.auth_enabled else 'none',
        'tool_profile': get_active_tool_profile().value,
        'exposed_tool_count': get_active_tool_count(),
        'upload_policy': config.upload_policy,
        'native_picker_staging': 'automatic',
        'capabilities': _dynamic_capabilities(),
    }
    if include_tool_names:
        tool_names: JsonArray = []
        for name in sorted(tool_names_for_profile(get_active_tool_profile(), PUBLIC_TOOL_NAMES)):
            tool_names.append(name)
        result['tool_names'] = tool_names
    try:
        browser_values: JsonArray = []
        sync_results: list[TabSyncResult] = []
        for browser in registry.list_browsers(client_id):
            async with browser_operation_lock(browser.browser_id):
                sync = await sync_browser_tabs(client_id, browser.browser_id)
            sync_results.append(sync)
            browser_summary = browser.summary()
            browser_summary.update(sync.summary(get_limits_config().max_tabs_per_browser))
            browser_values.append(browser_summary)
        result['browsers'] = browser_values
        result['tabs'] = len(registry.list_tabs(client_id))
        result['actual_tabs'] = sum(sync.actual_count for sync in sync_results)
        result['managed_tabs'] = len(registry.list_tabs(client_id))
        result['max_tabs_per_browser'] = get_limits_config().max_tabs_per_browser
    except Exception as exc:
        result['browsers_error'] = str(exc)
    if include_clients:
        client_values: JsonArray = []
        client_values.extend(registry.list_clients())
        result['clients'] = client_values
    result['resources'] = state.summary()
    return result


def _dynamic_capabilities() -> JsonObject:
    exposed = tool_names_for_profile(get_active_tool_profile(), PUBLIC_TOOL_NAMES)

    def has(name: str) -> bool:
        return name in exposed

    def names(values: dict[str, str]) -> JsonArray:
        return [label for name, label in values.items() if has(name)]

    return {
        'transports': ['http', 'sse', 'stdio'],
        'browser': names({'browser_launch': 'launch', 'browser_close': 'close', 'browser_list': 'list'}),
        'page': names(
            {
                'page_goto': 'navigation',
                'page_snapshot': 'snapshot',
                'page_get_tree': 'tree',
                'page_get_tree_deep': 'deep_tree',
                'page_get_interactive_summary': 'interactive_summary',
                'page_screenshot': 'screenshot',
                'page_get_active_surface': 'active_surface',
            }
        ),
        'elements': names(
            {
                'element_find': 'find',
                'element_find_deep': 'find_deep',
                'element_click_by_text': 'click_by_text',
                'mouse_click': 'mouse_click',
                'element_click': 'interact',
                'element_get_state': 'state',
                'element_resolve_again': 'stale_resolution',
            }
        ),
        'forms': names(
            {
                'element_fill': 'framework_safe_fill',
                'form_snapshot': 'form_snapshot',
                'form_errors': 'form_errors',
                'form_fill_fields': 'form_fill_fields',
                'form_preflight': 'preflight',
                'form_review': 'review',
                'form_prepare': 'prepare',
                'form_submit_after_review': 'authorized_submit',
                'application_domain_status': 'domain_restrictions',
                'page_click_primary_action': 'primary_action',
            }
        ),
        'waits': names(
            {
                'page_wait_for_url': 'url',
                'page_wait_for_function': 'function',
                'page_wait_for_text': 'text',
                'page_wait_for_selector': 'selector',
                'page_wait_for_network_idle': 'network_idle',
                'element_wait_value': 'element_value',
                'submission_wait_for_confirmation': 'submission_confirmation',
            }
        ),
        'artifacts': names(
            {
                'upload_files': 'upload',
                'file_upload_state': 'upload_state',
                'artifact_get_paths': 'artifact_paths',
                'artifact_export': 'artifact_export',
                'artifact_import': 'artifact_import',
                'artifact_prepare_upload': 'artifact_prepare_upload',
            }
        ),
        'diagnostics': names(
            {'health_check': 'health', 'server_status': 'status', 'diagnostics_snapshot': 'diagnostics'}
        ),
        'inspection': names({'network_list': 'network', 'console_list': 'console'}),
        'security': ['auth', 'redaction', 'path_allowlist', 'no_free_cdp'],
    }


async def diagnostics_snapshot(client_id: str = 'anonymous', include_clients: bool = False) -> JsonObject:
    registry = get_registry()
    config = get_config()
    browsers = registry.list_browsers(client_id)
    sync_results: list[TabSyncResult] = []
    for browser in browsers:
        async with browser_operation_lock(browser.browser_id):
            sync_results.append(await sync_browser_tabs(client_id, browser.browser_id))
    tabs = registry.list_tabs(client_id)
    get_trace_manager().add_event_to_active(
        client_id,
        TraceEvent(
            timestamp=time.time(),
            tool='diagnostics_snapshot',
            status='success',
            summary=f'Browsers: {len(browsers)}, tabs: {len(tabs)}',
        ),
    )
    return {
        'success': True,
        'schema_version': SCHEMA_VERSION,
        'uptime_seconds': round(get_server_state().uptime_seconds, 1),
        'auth_mode': 'token' if config.auth_enabled else 'none',
        'browsers': [
            {
                'browser_id': b.browser_id,
                'headless': b.headless,
                'health': b.health.value,
                'tabs': len(b.tabs),
                **sync.summary(get_limits_config().max_tabs_per_browser),
            }
            for b, sync in zip(browsers, sync_results, strict=True)
        ],
        'tabs': [{'tab_id': t.tab_id, 'url': t.url, 'health': t.health.value} for t in tabs],
        'actual_tabs': sum(item.actual_count for item in sync_results),
        'managed_tabs': len(tabs),
        'max_tabs_per_browser': get_limits_config().max_tabs_per_browser,
        'resources': get_server_state().summary(),
        'clients': list(registry.list_clients()) if include_clients else [],
    }


async def trace_start(client_id: str, name: str = '', include_screenshots: bool = False) -> JsonObject:
    trace = get_trace_manager().create(client_id, name=name, include_screenshots=include_screenshots)
    trace.add_event(TraceEvent(time.time(), 'trace_start', 'started', summary=f'Trace started: {trace.trace_id}'))
    return {
        'success': True,
        'trace_id': trace.trace_id,
        'name': trace.name,
        'include_screenshots': include_screenshots,
        'events_count': len(trace.events),
    }


async def trace_stop(client_id: str, trace_id: str) -> JsonObject:
    trace = get_trace_manager().stop(client_id, trace_id)
    if trace is None:
        return _not_found('Trace', trace_id, client_id)
    trace.add_event(TraceEvent(time.time(), 'trace_stop', 'stopped', summary=f'Trace stopped: {trace_id}'))
    return {'success': True, 'trace_id': trace_id, 'stopped': True, 'events_count': len(trace.events)}


async def trace_get(client_id: str, trace_id: str, max_events: int = 200) -> JsonObject:
    trace = get_trace_manager().get(client_id, trace_id)
    if trace is None:
        return _not_found('Trace', trace_id, client_id)
    events = trace.events[-max_events:] if max_events > 0 else trace.events
    event_values: JsonArray = []
    for event in events:
        event_values.append(event.to_dict())
    return {
        'success': True,
        'trace_id': trace_id,
        'status': trace.status,
        'events': event_values,
        'count': len(events),
        'total': len(trace.events),
    }


async def trace_cleanup(client_id: str, older_than_seconds: int = 86400) -> JsonObject:
    return {'success': True, 'cleaned': get_trace_manager().cleanup(client_id, older_than_seconds)}


async def browser_attach(client_id: str, browser_id: str = '', profile_id: str = '') -> JsonObject:
    registry = get_registry()
    if browser_id:
        try:
            info = registry.get_browser(client_id, browser_id)
        except StructuredError:
            info = None
        if info is not None:
            return {
                'success': True,
                'browser_id': info.browser_id,
                'profile_id': info.profile.profile_id if info.profile else '',
                'reconnected': False,
                'new_instance': False,
                'status': 'already_attached',
            }
        if not profile_id:
            profile_id = browser_id
    if not profile_id:
        return StructuredError(ErrorCode.INVALID_INPUT, 'profile_id is required for restart-safe attach.').to_dict()

    index_entry = get_profile_index().get(profile_id)
    if index_entry is not None and index_entry.owner_client_id != client_id:
        return StructuredError(ErrorCode.PERMISSION_DENIED, 'Profile belongs to another client.').to_dict()
    metadata = get_profile_lease_manager().find_metadata(profile_id, client_id)
    if metadata is None:
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f'No live lease metadata was found for profile {profile_id}.',
            retryable=False,
            recovery_hint='Use browser_launch with the explicit profile_id when no browser process is running.',
        ).to_dict()
    raw_path = metadata.get('profile_path')
    raw_port = metadata.get('cdp_port')
    profile_path = Path(str(raw_path or '')).resolve(strict=False)
    config = get_config()
    allowed_roots = (config.profiles_dir.resolve(strict=False), config.tmp_dir.resolve(strict=False))
    if not _inside_any(profile_path, allowed_roots):
        return StructuredError(ErrorCode.PERMISSION_DENIED, 'Lease profile path is outside managed roots.').to_dict()
    browser_pid = _safe_int(metadata.get('browser_pid'))
    if browser_pid is not None and not _process_is_alive(browser_pid):
        get_profile_lease_manager().release_by_profile(str(profile_path))
        return _stale_lease(profile_id, 'The leased browser process is no longer alive.')
    if not isinstance(raw_port, int) or raw_port <= 0:
        if browser_pid is None:
            get_profile_lease_manager().release_by_profile(str(profile_path))
            return _stale_lease(profile_id, 'The lease has no browser process or CDP endpoint metadata.')
        return _handoff(profile_id, 'Lease metadata has no valid CDP port while the browser process is alive.')
    try:
        ws_address = await asyncio.wait_for(get_browser_ws_address(raw_port), timeout=5.0)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        return _handoff(profile_id, f'CDP endpoint could not be validated: {exc}')

    lease = get_profile_lease_manager().acquire(str(profile_path), client_id, profile_id)
    if lease is None:
        return StructuredError(
            ErrorCode.RESOURCE_LOCKED,
            f'Profile {profile_id} is currently owned by another process.',
            retryable=True,
            details={'profile_id': profile_id, 'status': 'profile_locked'},
        ).to_dict()

    browser = None
    try:
        from pydoll.browser import Chrome

        browser = Chrome(options=create_chromium_options(), connection_port=raw_port)
        first_tab = await asyncio.wait_for(browser.connect(ws_address), timeout=15.0)
        mode = ProfileMode.PERSISTENT
        if index_entry is not None and index_entry.mode == ProfileMode.TEMPORARY.value:
            mode = ProfileMode.TEMPORARY
        profile = ProfileInfo(profile_id, client_id, mode, str(profile_path))
        browser_info = registry.register_browser(
            client_id,
            browser,
            profile,
            headless=False,
            browser_process_id=browser_pid,
        )
        registry.register_tab(
            client_id,
            browser_info.browser_id,
            first_tab,
            target_id=get_tab_target_id(first_tab),
            url=await get_tab_url(first_tab),
            title=await get_tab_title(first_tab),
        )
        sync = await sync_browser_tabs(client_id, browser_info.browser_id)
        attached_tabs = registry.list_tabs(client_id, browser_info.browser_id)
        lease.write_metadata(
            browser_pid,
            raw_port,
            [tab.target_id for tab in attached_tabs],
            [tab.url for tab in attached_tabs],
        )
        return {
            'success': True,
            'status': 'reconnected',
            'reconnected': True,
            'new_instance': False,
            'browser_id': browser_info.browser_id,
            'profile_id': profile_id,
            'tabs': [tab.summary() for tab in attached_tabs],
            'reconciliation': sync.summary(get_limits_config().max_tabs_per_browser),
        }
    except Exception as exc:
        get_profile_lease_manager().release(lease)
        return _handoff(profile_id, f'Browser attach failed: {exc}')


def _handoff(profile_id: str, reason: str) -> JsonObject:
    return {
        'success': False,
        'status': 'requires_handoff',
        'reconnected': False,
        'new_instance': False,
        'profile_id': profile_id,
        'handoff': True,
        'message': reason,
        'recovery_hint': 'Verify the browser process manually, then call browser_launch or attach again.',
    }


def _stale_lease(profile_id: str, reason: str) -> JsonObject:
    return {
        'success': False,
        'status': 'stale_lease',
        'reconnected': False,
        'new_instance': False,
        'profile_id': profile_id,
        'message': reason,
        'recovery_hint': 'The profile may be launched again after the stale lease is released.',
    }


def _inside_any(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(_is_relative_to(path, root) for root in roots)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _process_is_alive(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _not_found(kind: str, resource_id: str, client_id: str) -> JsonObject:
    return {
        'success': False,
        'error_code': 'RESOURCE_NOT_FOUND',
        'message': f'{kind} {resource_id} not found or not owned by {client_id}',
    }
