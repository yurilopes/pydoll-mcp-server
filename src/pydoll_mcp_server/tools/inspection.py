"""Network and console inspection tools."""

from __future__ import annotations

import re
import time
from typing import Any

from pydoll_mcp_server.browser.inspection import get_inspection_manager
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, StructuredError

_URL_REDACT = re.compile(
    r'([?&])(token|key|secret|auth|password|api_key|apikey)=[^&\s]*',
    re.IGNORECASE,
)


def _redact_url(url: str) -> str:
    return _URL_REDACT.sub(r'\1\2=REDACTED', url)


def _normalize_network_log(log: dict) -> dict:
    params = log.get('params', {}) if isinstance(log, dict) else {}
    request = params.get('request', {}) if isinstance(params, dict) else {}
    response = params.get('response', {}) if isinstance(params, dict) else {}
    return {
        'request_id': params.get('requestId', ''),
        'url': _redact_url(str(request.get('url') or response.get('url', ''))),
        'method': request.get('method', ''),
        'status': response.get('status', 0),
        'type': params.get('type', ''),
        'timestamp': params.get('timestamp', 0),
        'event': log.get('method', ''),
    }


async def network_enable(
    client_id: str,
    tab_id: str,
    max_events: int = 1000,
) -> dict[str, Any]:
    registry = get_registry()
    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info._pydoll_tab
    try:
        await pydoll_tab.enable_network_events()
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
) -> dict[str, Any]:
    registry = get_registry()
    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    import contextlib
    pydoll_tab = tab_info._pydoll_tab
    with contextlib.suppress(Exception):
        await pydoll_tab.disable_network_events()

    get_inspection_manager().get(tab_id).disable_network()
    return {'success': True, 'tab_id': tab_id, 'network_enabled': False}


async def network_list(
    client_id: str,
    tab_id: str,
    filter_url: str = '',
    limit: int = 100,
) -> dict[str, Any]:
    registry = get_registry()
    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    pydoll_tab = tab_info._pydoll_tab

    try:
        raw_logs = await pydoll_tab.get_network_logs(filter=None)
    except Exception as exc2:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get network logs: {exc2}',
            retryable=True,
        ).to_dict()

    logs = raw_logs if isinstance(raw_logs, list) else []
    events = [_normalize_network_log(log) for log in logs if isinstance(log, dict)]
    events = [event for event in events if event.get('url')]

    if filter_url:
        events = [e for e in events if filter_url in e.get('url', '')]

    limited = events[-limit:] if limit > 0 else events

    state = get_inspection_manager().get(tab_id)
    for evt in events:
        state.add_network_event(evt)

    _trace_event(client_id, 'network_list', 'success', tab_id, summary=f'{len(events)} events')

    return {
        'success': True,
        'events': limited,
        'count': len(limited),
        'total': len(events),
    }


async def network_get_response(
    client_id: str,
    tab_id: str,
    request_id: str,
    max_bytes: int = 65536,
    redact: bool = True,
) -> dict[str, Any]:
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

    pydoll_tab = tab_info._pydoll_tab

    try:
        body = await pydoll_tab.get_network_response_body(request_id)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get response body: {e}',
            retryable=False,
        ).to_dict()

    body_str = str(body) if not isinstance(body, str) else body
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
) -> dict[str, Any]:
    try:
        tab = get_registry().get_tab(client_id, tab_id)._pydoll_tab
        state = get_inspection_manager().get(tab_id)
        state.max_events = max(1, min(max_events, 10000))
        if state.console_enabled:
            return {'success': True, 'tab_id': tab_id, 'console_enabled': True}
        from pydoll.protocol.runtime.events import RuntimeEvent

        async def on_console(event: dict) -> None:
            params = event.get('params', {})
            values = []
            for arg in params.get('args', []):
                value = arg.get('value', arg.get('description', '')) if isinstance(arg, dict) else str(arg)
                values.append(_redact_sensitive(str(value))[:4000])
            state.add_console_event({
                'level': params.get('type', 'log'),
                'text': ' '.join(values),
                'timestamp': params.get('timestamp', 0),
            })

        await tab.enable_runtime_events()
        state.console_callback_id = await tab.on(RuntimeEvent.CONSOLE_API_CALLED, on_console)
        state.console_enabled = True
        return {'success': True, 'tab_id': tab_id, 'console_enabled': True}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.UNSUPPORTED, f'Console inspection unavailable: {exc}').to_dict()


async def console_disable(
    client_id: str,
    tab_id: str,
) -> dict[str, Any]:
    try:
        tab = get_registry().get_tab(client_id, tab_id)._pydoll_tab
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
) -> dict[str, Any]:
    try:
        get_registry().get_tab(client_id, tab_id)
        events = get_inspection_manager().get(tab_id).console_events
        if filter_level:
            events = [event for event in events if event.get('level') == filter_level]
        selected = events[-max(0, min(limit, 1000)):]
        return {'success': True, 'events': selected, 'count': len(selected), 'total': len(events)}
    except StructuredError as exc:
        return exc.to_dict()


async def network_summary(client_id: str, tab_id: str) -> dict[str, Any]:
    result = await network_list(client_id, tab_id, limit=1000)
    if not result.get('success'):
        return result
    events = result.get('events', [])
    methods: dict[str, int] = {}
    types: dict[str, int] = {}
    statuses: dict[str, int] = {}
    for event in events:
        methods[event.get('method', '')] = methods.get(event.get('method', ''), 0) + 1
        types[event.get('type', '')] = types.get(event.get('type', ''), 0) + 1
        if event.get('status'):
            key = str(event['status'])
            statuses[key] = statuses.get(key, 0) + 1
    return {'success': True, 'total': len(events), 'methods': methods, 'types': types, 'statuses': statuses}


async def network_clear(client_id: str, tab_id: str) -> dict[str, Any]:
    try:
        get_registry().get_tab(client_id, tab_id)
        get_inspection_manager().get(tab_id).clear_network()
        return {'success': True, 'tab_id': tab_id, 'cleared': True}
    except StructuredError as exc:
        return exc.to_dict()


def _trace_event(
    client_id: str,
    tool: str,
    status: str,
    tab_id: str = '',
    error_code: str = '',
    summary: str = '',
) -> None:
    from pydoll_mcp_server.diagnostics.trace import TraceEvent, get_trace_manager
    get_trace_manager().add_event_to_active(client_id, TraceEvent(
        timestamp=time.time(),
        tool=tool,
        status=status,
        tab_id=tab_id,
        error_code=error_code,
        summary=summary,
    ))


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
    text = re.sub(
        r'"Set-Cookie"\s*:\s*"[^"]*"',
        '"Set-Cookie":"[REDACTED]"',
        text,
        flags=re.IGNORECASE,
    )
    return text
