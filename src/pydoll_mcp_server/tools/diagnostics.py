"""Health, diagnostics, tracing, and safe attach tools."""

from __future__ import annotations

import time

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.diagnostics.trace import TraceEvent, get_trace_manager
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject
from pydoll_mcp_server.server_state import SCHEMA_VERSION, get_server_state
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


def server_status(client_id: str = 'anonymous', include_clients: bool = False) -> JsonObject:
    registry = get_registry()
    config = get_config()
    state = get_server_state()
    result: JsonObject = {
        'status': 'ok',
        'version': get_version(),
        'schema_version': SCHEMA_VERSION,
        'uptime_seconds': round(state.uptime_seconds, 1),
        'auth_mode': 'token' if config.auth_enabled else 'none',
        'capabilities': {
            'transports': ['http', 'sse', 'stdio'],
            'browser': ['launch', 'close', 'list', 'attach'],
            'page': ['navigation', 'tree', 'deep_tree', 'interactive_summary', 'screenshot', 'snapshot', 'pdf'],
            'elements': ['find', 'find_deep', 'semantic_find', 'click_by_text', 'mouse_click', 'interact', 'state'],
            'forms': ['framework_safe_fill', 'combobox', 'form_snapshot', 'form_errors'],
            'waits': ['url', 'function', 'text', 'selector', 'network_idle', 'element_value'],
            'artifacts': ['upload', 'upload_state', 'artifact_paths', 'artifact_import'],
            'diagnostics': ['health', 'status', 'diagnostics_snapshot', 'trace'],
            'inspection': ['network', 'console'],
            'security': ['auth', 'redaction', 'path_allowlist', 'no_free_cdp'],
        },
    }
    try:
        browser_values: JsonArray = []
        for browser in registry.list_browsers(client_id):
            browser_values.append(browser.summary())
        result['browsers'] = browser_values
        result['tabs'] = len(registry.list_tabs(client_id))
    except Exception as exc:
        result['browsers_error'] = str(exc)
    if include_clients:
        client_values: JsonArray = []
        client_values.extend(registry.list_clients())
        result['clients'] = client_values
    result['resources'] = state.summary()
    return result


async def diagnostics_snapshot(client_id: str = 'anonymous', include_clients: bool = False) -> JsonObject:
    registry = get_registry()
    config = get_config()
    browsers = registry.list_browsers(client_id)
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
            {'browser_id': b.browser_id, 'headless': b.headless, 'health': b.health.value, 'tabs': len(b.tabs)}
            for b in browsers
        ],
        'tabs': [{'tab_id': t.tab_id, 'url': t.url, 'health': t.health.value} for t in tabs],
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


async def browser_attach(client_id: str, browser_id: str) -> JsonObject:
    try:
        info = get_registry().get_browser(client_id, browser_id)
    except StructuredError as exc:
        return exc.to_dict()
    if info.client_id != client_id:
        return StructuredError(ErrorCode.PERMISSION_DENIED, 'Browser belongs to another client').to_dict()
    return StructuredError(
        ErrorCode.UNSUPPORTED,
        'Browser attach is not supported after server restart.',
        recovery_hint='Use browser_launch to create a new browser instance.',
    ).to_dict()


def _not_found(kind: str, resource_id: str, client_id: str) -> JsonObject:
    return {
        'success': False,
        'error_code': 'RESOURCE_NOT_FOUND',
        'message': f'{kind} {resource_id} not found or not owned by {client_id}',
    }
