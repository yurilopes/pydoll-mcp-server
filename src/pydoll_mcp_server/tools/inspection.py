"""Network and console inspection tools."""

from __future__ import annotations

import re
import time

from pydoll_mcp_server.browser.inspection import get_inspection_manager
from pydoll_mcp_server.browser.pydoll_compat import (
    disable_network_events,
    enable_network_events,
    enable_runtime_events,
    register_runtime_callback,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_float,
    get_int,
    get_object,
    get_string,
    require_json_object,
)

_URL_REDACT = re.compile(
    r'([?&])(token|key|secret|auth|password|api_key|apikey)=[^&\s]*',
    re.IGNORECASE,
)


def _redact_url(url: str) -> str:
    return _URL_REDACT.sub(r'\1\2=REDACTED', url)


def redact_url(url: str) -> str:
    return _redact_url(url)


def _normalize_network_log(log: object) -> JsonObject:
    event = require_json_object(log, 'network event')
    params = get_object(event, 'params', {})
    request = get_object(params, 'request', {})
    response = get_object(params, 'response', {})
    return {
        'request_id': get_string(params, 'requestId'),
        'url': _redact_url(get_string(request, 'url') or get_string(response, 'url')),
        'method': get_string(request, 'method'),
        'status': get_int(response, 'status'),
        'type': get_string(params, 'type'),
        'timestamp': get_float(params, 'timestamp'),
        'event': get_string(event, 'method'),
    }


def normalize_network_log(log: object) -> JsonObject:
    return _normalize_network_log(log)


async def network_enable(
    client_id: str,
    tab_id: str,
    max_events: int = 1000,
) -> JsonObject:
    registry = get_registry()
    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab
    try:
        await enable_network_events(pydoll_tab)
        state = get_inspection_manager().get(tab_id)
        state.network_enabled = True
        state.max_events = max_events
    except Exception as e:
        _trace_event(client_id, 'network_enable', 'error', tab_id, 'EXECUTION_ERROR', str(e))
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to enable network: {e}',
            retryable=True,
        ).to_dict()

    _trace_event(client_id, 'network_enable', 'success', tab_id)
    return {'success': True, 'tab_id': tab_id, 'network_enabled': True}


async def network_disable(
    client_id: str,
    tab_id: str,
) -> JsonObject:
    registry = get_registry()
    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab
    try:
        await disable_network_events(pydoll_tab)
    except Exception as exc:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to disable network: {exc}',
            retryable=True,
        ).to_dict()

    get_inspection_manager().get(tab_id).disable_network()
    return {'success': True, 'tab_id': tab_id, 'network_enabled': False}


async def network_list(
    client_id: str,
    tab_id: str,
    filter_url: str = '',
    limit: int = 100,
) -> JsonObject:
    registry = get_registry()
    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    pydoll_tab = tab_info.pydoll_tab

    try:
        raw_logs = await pydoll_tab.get_network_logs(filter=None)
    except Exception as exc2:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get network logs: {exc2}',
            retryable=True,
        ).to_dict()

    events = [_normalize_network_log(log) for log in raw_logs]
    events = [event for event in events if get_string(event, 'url')]

    if filter_url:
        events = [event for event in events if filter_url in get_string(event, 'url')]

    limited = events[-limit:] if limit > 0 else events

    state = get_inspection_manager().get(tab_id)
    for evt in events:
        state.add_network_event(evt)

    _trace_event(client_id, 'network_list', 'success', tab_id, summary=f'{len(events)} events')

    event_values: JsonArray = list(limited)
    return {
        'success': True,
        'events': event_values,
        'count': len(limited),
        'total': len(events),
    }


async def network_get_response(
    client_id: str,
    tab_id: str,
    request_id: str,
    max_bytes: int = 65536,
    redact: bool = True,
) -> JsonObject:
    if not request_id or not request_id.strip():
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message='request_id is required and cannot be empty',
            retryable=False,
        ).to_dict()

    registry = get_registry()
    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab

    try:
        body = await pydoll_tab.get_network_response_body(request_id)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get response body: {e}',
            retryable=False,
        ).to_dict()

    body_str = body
    truncated = len(body_str.encode('utf-8')) > max_bytes
    if truncated:
        body_str = body_str[:max_bytes]

    if redact:
        body_str = _redact_sensitive(body_str)

    _trace_event(client_id, 'network_get_response', 'success', tab_id, summary=f'{len(body_str)} bytes')

    return {
        'success': True,
        'body': body_str,
        'truncated': truncated,
        'size_bytes': len(body_str.encode('utf-8')),
    }


async def console_enable(
    client_id: str,
    tab_id: str,
    max_events: int = 1000,
) -> JsonObject:
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        state = get_inspection_manager().get(tab_id)
        state.max_events = max(1, min(max_events, 10000))
        if state.console_enabled:
            return {'success': True, 'tab_id': tab_id, 'console_enabled': True}
        from pydoll.protocol.runtime.events import RuntimeEvent

        async def on_console(event: object) -> None:
            params = get_object(require_json_object(event, 'console event'), 'params', {})
            values: list[str] = []
            for arg_value in get_array(params, 'args', []):
                arg = require_json_object(arg_value, 'console argument')
                value = get_string(arg, 'value') or get_string(arg, 'description')
                values.append(_redact_sensitive(value)[:4000])
            state.add_console_event(
                {
                    'level': get_string(params, 'type', 'log'),
                    'text': ' '.join(values),
                    'timestamp': get_float(params, 'timestamp'),
                }
            )

        await enable_runtime_events(tab)
        state.console_callback_id = await register_runtime_callback(tab, RuntimeEvent.CONSOLE_API_CALLED, on_console)
        state.console_enabled = True
        return {'success': True, 'tab_id': tab_id, 'console_enabled': True}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.UNSUPPORTED, f'Console inspection unavailable: {exc}').to_dict()


async def console_disable(
    client_id: str,
    tab_id: str,
) -> JsonObject:
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        state = get_inspection_manager().get(tab_id)
        if state.console_callback_id is not None:
            await tab.remove_callback(state.console_callback_id)
        state.disable_console()
        return {'success': True, 'tab_id': tab_id, 'console_enabled': False}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Console disable failed: {exc}').to_dict()


async def console_list(
    client_id: str,
    tab_id: str,
    filter_level: str = '',
    limit: int = 100,
) -> JsonObject:
    try:
        get_registry().get_tab(client_id, tab_id)
        events = get_inspection_manager().get(tab_id).console_events
        if filter_level:
            events = [event for event in events if event.get('level') == filter_level]
        selected = events[-max(0, min(limit, 1000)) :]
        selected_values: JsonArray = list(selected)
        return {'success': True, 'events': selected_values, 'count': len(selected), 'total': len(events)}
    except StructuredError as exc:
        return exc.to_dict()


async def network_summary(client_id: str, tab_id: str) -> JsonObject:
    result = await network_list(client_id, tab_id, limit=1000)
    if not result.get('success'):
        return result
    events = get_array(result, 'events', [])
    methods: dict[str, int] = {}
    types: dict[str, int] = {}
    statuses: dict[str, int] = {}
    for event_value in events:
        event = require_json_object(event_value, 'network event')
        method = get_string(event, 'method')
        event_type = get_string(event, 'type')
        methods[method] = methods.get(method, 0) + 1
        types[event_type] = types.get(event_type, 0) + 1
        status = get_int(event, 'status')
        if status:
            key = str(status)
            statuses[key] = statuses.get(key, 0) + 1
    method_values: JsonObject = dict(methods)
    type_values: JsonObject = dict(types)
    status_values: JsonObject = dict(statuses)
    return {
        'success': True,
        'total': len(events),
        'methods': method_values,
        'types': type_values,
        'statuses': status_values,
    }


async def network_clear(client_id: str, tab_id: str) -> JsonObject:
    try:
        get_registry().get_tab(client_id, tab_id)
        get_inspection_manager().get(tab_id).clear_network()
        return {'success': True, 'tab_id': tab_id, 'cleared': True}
    except StructuredError as exc:
        return exc.to_dict()


def trace_inspection_event(
    client_id: str,
    tool: str,
    status: str,
    tab_id: str = '',
    error_code: str = '',
    summary: str = '',
) -> None:
    from pydoll_mcp_server.diagnostics.trace import TraceEvent, get_trace_manager

    get_trace_manager().add_event_to_active(
        client_id,
        TraceEvent(
            timestamp=time.time(),
            tool=tool,
            status=status,
            tab_id=tab_id,
            error_code=error_code,
            summary=summary,
        ),
    )


_trace_event = trace_inspection_event


def _redact_sensitive(text: str) -> str:
    text = re.sub(r'"access_token"\s*:\s*"[^"]*"', '"access_token":"[REDACTED]"', text)
    text = re.sub(r'"refresh_token"\s*:\s*"[^"]*"', '"refresh_token":"[REDACTED]"', text)
    text = re.sub(
        r'"Authorization"\s*:\s*"[^"]*"',
        '"Authorization":"[REDACTED]"',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'"cookie"\s*:\s*"[^"]*"',
        '"cookie":"[REDACTED]"',
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r'"Set-Cookie"\s*:\s*"[^"]*"',
        '"Set-Cookie":"[REDACTED]"',
        text,
        flags=re.IGNORECASE,
    )
