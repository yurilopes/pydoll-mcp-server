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
    return {
        'request_id': params.get('requestId', ''),
        'url': _redact_url(str(request.get('url', ''))),
        'method': request.get('method', ''),
        'type': params.get('type', ''),
        'timestamp': params.get('timestamp', 0),
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

    get_inspection_manager().get(tab_id).clear_network()
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
    events = [
        _normalize_network_log(log) for log in logs
        if isinstance(log, dict) and log.get('params', {}).get('request', {}).get('url')
    ]

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
    return StructuredError(
        error_code=ErrorCode.UNSUPPORTED,
        message=(
            'Console inspection is not yet supported with the installed '
            'Pydoll runtime event API.'
        ),
        retryable=False,
        details={'reason': 'Runtime domain events require additional Pydoll API validation.'},
    ).to_dict()


async def console_disable(
    client_id: str,
    tab_id: str,
) -> dict[str, Any]:
    return StructuredError(
        error_code=ErrorCode.UNSUPPORTED,
        message='Console inspection is not yet supported.',
        retryable=False,
    ).to_dict()


async def console_list(
    client_id: str,
    tab_id: str,
    filter_level: str = '',
    limit: int = 100,
) -> dict[str, Any]:
    return StructuredError(
        error_code=ErrorCode.UNSUPPORTED,
        message='Console inspection is not yet supported.',
        retryable=False,
    ).to_dict()


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
