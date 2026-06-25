"""Lossless, per-tab HTTP request inspection."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from contextlib import suppress
from urllib.parse import parse_qsl

from pydoll.protocol.network.events import NetworkEvent

from pydoll_mcp_server.browser.inspection import get_inspection_manager
from pydoll_mcp_server.browser.pydoll_compat import (
    disable_network_events,
    enable_network_events,
    get_request_post_data,
    register_network_callback,
    remove_tab_callback,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_bool,
    get_float,
    get_int,
    get_object,
    get_string,
    normalize_json_value,
    require_json_object,
)
from pydoll_mcp_server.tools.websocket import WEBSOCKET_NETWORK_EVENTS, capture_websocket_event

MAX_REQUEST_BYTES = 16 * 1024 * 1024
_URL_REDACT = re.compile(r'([?&])(token|key|secret|auth|password|api_key|apikey)=[^&\s]*', re.I)


def redact_url(url: str) -> str:
    return _URL_REDACT.sub(r'\1\2=REDACTED', url)


def normalize_network_log(log: object) -> JsonObject:
    event = require_json_object(log, 'network event')
    params = get_object(event, 'params', {})
    request = get_object(params, 'request', {})
    response = get_object(params, 'response', {})
    return {
        'request_id': get_string(params, 'requestId'),
        'url': redact_url(get_string(request, 'url') or get_string(response, 'url')),
        'method': get_string(request, 'method'),
        'status': get_int(response, 'status'),
        'type': get_string(params, 'type'),
        'timestamp': get_float(params, 'timestamp'),
        'event': get_string(event, 'method'),
    }


def _record(state_id: str, request_id: str) -> JsonObject:
    state = get_inspection_manager().get(state_id)
    return state.requests.get(request_id, {'request_id': request_id})


async def capture_network_event(tab_id: str, event_value: object) -> None:
    event = require_json_object(event_value, 'network event')
    method = get_string(event, 'method')
    params = get_object(event, 'params', {})
    request_id = get_string(params, 'requestId')
    if not request_id:
        return
    state = get_inspection_manager().get(tab_id)
    record = dict(_record(tab_id, request_id))
    if method == NetworkEvent.REQUEST_WILL_BE_SENT:
        request = get_object(params, 'request', {})
        if 'request' in record:
            chain = list(get_array(record, 'redirect_chain', []))
            chain.append({'request': record['request'], 'response': params.get('redirectResponse')})
            record['redirect_chain'] = chain
        record.update(
            {
                'request': request,
                'document_url': get_string(params, 'documentURL'),
                'resource_type': get_string(params, 'type'),
                'initiator': get_object(params, 'initiator', {}),
                'timestamp': get_float(params, 'timestamp'),
                'wall_time': get_float(params, 'wallTime'),
                'redirect_chain': get_array(record, 'redirect_chain', []),
            }
        )
    elif method == NetworkEvent.REQUEST_WILL_BE_SENT_EXTRA_INFO:
        record['request_extra_info'] = params
    elif method == NetworkEvent.RESPONSE_RECEIVED:
        record['response'] = get_object(params, 'response', {})
    elif method == NetworkEvent.RESPONSE_RECEIVED_EXTRA_INFO:
        record['response_extra_info'] = params
    elif method == NetworkEvent.REQUEST_SERVED_FROM_CACHE:
        record['served_from_cache'] = True
    elif method == NetworkEvent.LOADING_FINISHED:
        record['finished'] = params
    elif method == NetworkEvent.LOADING_FAILED:
        record['failure'] = params
    state.upsert_request(request_id, record)


async def network_enable(client_id: str, tab_id: str, max_events: int = 1000) -> JsonObject:
    if not 1 <= max_events <= 10000:
        return StructuredError(ErrorCode.INVALID_INPUT, 'max_events must be between 1 and 10000').to_dict()
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        state = get_inspection_manager().get(tab_id)
        if state.network_enabled:
            return {'success': True, 'tab_id': tab_id, 'network_enabled': True}
        await asyncio.wait_for(enable_network_events(tab), 10.0)
        state.max_events = max_events
        for event_name in (
            NetworkEvent.REQUEST_WILL_BE_SENT,
            NetworkEvent.REQUEST_WILL_BE_SENT_EXTRA_INFO,
            NetworkEvent.RESPONSE_RECEIVED,
            NetworkEvent.RESPONSE_RECEIVED_EXTRA_INFO,
            NetworkEvent.REQUEST_SERVED_FROM_CACHE,
            NetworkEvent.LOADING_FINISHED,
            NetworkEvent.LOADING_FAILED,
        ):

            async def callback(event: object, current: str = tab_id) -> None:
                await capture_network_event(current, event)

            state.network_callback_ids.append(await register_network_callback(tab, event_name, callback))
        for event_name in WEBSOCKET_NETWORK_EVENTS:

            async def websocket_callback(event: object, current: str = tab_id) -> None:
                await capture_websocket_event(current, event)

            state.network_callback_ids.append(await register_network_callback(tab, event_name, websocket_callback))
        state.network_enabled = True
        _trace_event(client_id, 'network_enable', 'success', tab_id)
        return {'success': True, 'tab_id': tab_id, 'network_enabled': True}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception:
        return StructuredError(ErrorCode.EXECUTION_ERROR, 'Failed to enable network capture', retryable=True).to_dict()


async def network_disable(client_id: str, tab_id: str) -> JsonObject:
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        state = get_inspection_manager().get(tab_id)
        for callback_id in state.network_callback_ids:
            await asyncio.wait_for(remove_tab_callback(tab, callback_id), 5.0)
        await asyncio.wait_for(disable_network_events(tab), 10.0)
        state.disable_network()
        return {'success': True, 'tab_id': tab_id, 'network_enabled': False}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception:
        return StructuredError(ErrorCode.EXECUTION_ERROR, 'Failed to disable network capture').to_dict()


def _summary(record: JsonObject) -> JsonObject:
    request = get_object(record, 'request', {})
    response = get_object(record, 'response', {})
    return {
        'request_id': get_string(record, 'request_id'),
        'url': redact_url(get_string(request, 'url')),
        'method': get_string(request, 'method'),
        'resource_type': get_string(record, 'resource_type'),
        'has_post_data': get_bool(request, 'hasPostData') or 'postData' in request,
        'status': get_int(response, 'status'),
        'redirect_count': len(get_array(record, 'redirect_chain', [])),
        'served_from_cache': get_bool(record, 'served_from_cache'),
        'failed': 'failure' in record,
        'response_received': 'response' in record,
        'timestamp': get_float(record, 'timestamp'),
    }


async def network_list(
    client_id: str,
    tab_id: str,
    filter_url: str = '',
    method: str = '',
    resource_type: str = '',
    has_post_data: bool | None = None,
    request_id: str = '',
    limit: int = 100,
) -> JsonObject:
    if not 1 <= limit <= 1000:
        return StructuredError(ErrorCode.INVALID_INPUT, 'limit must be between 1 and 1000').to_dict()
    try:
        get_registry().get_tab(client_id, tab_id)
        records = list(get_inspection_manager().get(tab_id).requests.values())
        selected: list[JsonObject] = []
        for record in records:
            request = get_object(record, 'request', {})
            present = get_bool(request, 'hasPostData') or 'postData' in request
            if filter_url and filter_url not in get_string(request, 'url'):
                continue
            if method and method.upper() != get_string(request, 'method').upper():
                continue
            if resource_type and resource_type != get_string(record, 'resource_type'):
                continue
            if has_post_data is not None and has_post_data != present:
                continue
            if request_id and request_id != get_string(record, 'request_id'):
                continue
            selected.append(_summary(record))
        events: JsonArray = list(selected[-limit:])
        _trace_event(client_id, 'network_list', 'success', tab_id, summary=f'{len(events)} events')
        return {'success': True, 'events': events, 'count': len(events), 'total': len(selected)}
    except StructuredError as exc:
        return exc.to_dict()


def _truncate_text(text: str, max_bytes: int) -> tuple[str, int, bool]:
    raw = text.encode('utf-8')
    if len(raw) <= max_bytes:
        return text, len(raw), False
    return raw[:max_bytes].decode('utf-8', errors='ignore'), len(raw), True


async def network_get_request(
    client_id: str,
    tab_id: str,
    request_id: str,
    max_bytes: int = 1_048_576,
) -> JsonObject:
    if not request_id.strip():
        return StructuredError(ErrorCode.INVALID_INPUT, 'request_id is required').to_dict()
    if not 1 <= max_bytes <= MAX_REQUEST_BYTES:
        return StructuredError(ErrorCode.INVALID_INPUT, 'max_bytes must be between 1 and 16777216').to_dict()
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        state = get_inspection_manager().get(tab_id)
        record = state.requests.get(request_id)
        if record is None:
            message = (
                'Request capture was discarded by the per-tab memory limit'
                if request_id in state.discarded_request_ids
                else 'Request not found'
            )
            return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, message).to_dict()
        request = get_object(record, 'request', {})
        has_post_data = get_bool(request, 'hasPostData') or 'postData' in request
        post_data_value = request.get('postData')
        post_data = post_data_value if isinstance(post_data_value, str) else None
        if has_post_data and post_data is None:
            try:
                post_data = await asyncio.wait_for(get_request_post_data(tab, request_id), 10.0)
            except Exception:
                post_data = None
        entries = get_array(request, 'postDataEntries', [])
        base64_encoded = False
        original_size = 0
        truncated = False
        returned_size = 0
        if post_data is not None:
            post_data, original_size, truncated = _truncate_text(post_data, max_bytes)
            returned_size = len(post_data.encode('utf-8'))
        elif len(entries) == 1:
            entry = require_json_object(entries[0], 'post data entry')
            encoded = get_string(entry, 'bytes')
            if encoded:
                decoded = base64.b64decode(encoded, validate=True)
                original_size = len(decoded)
                if original_size > max_bytes:
                    encoded = base64.b64encode(decoded[:max_bytes]).decode('ascii')
                    truncated = True
                post_data = encoded
                returned_size = min(original_size, max_bytes)
                base64_encoded = True
        extra = get_object(record, 'request_extra_info', {})
        event_headers = get_object(request, 'headers', {})
        headers = get_object(extra, 'headers', event_headers)
        content_type = next((str(value) for key, value in headers.items() if key.lower() == 'content-type'), '')
        result: JsonObject = {
            'success': True,
            'request_id': request_id,
            'url': get_string(request, 'url'),
            'method': get_string(request, 'method'),
            'resource_type': get_string(record, 'resource_type'),
            'document_url': get_string(record, 'document_url'),
            'headers': headers,
            'event_headers': event_headers,
            'headers_source': 'extra_info' if extra else 'request_event',
            'has_post_data': has_post_data,
            'post_data': post_data,
            'post_data_entries': entries,
            'content_type': content_type,
            'payload_size_bytes': original_size,
            'returned_size_bytes': returned_size,
            'base64_encoded': base64_encoded,
            'truncated': truncated,
            'initiator': get_object(record, 'initiator', {}),
            'redirect_chain': get_array(record, 'redirect_chain', []),
            'served_from_cache': get_bool(record, 'served_from_cache'),
            'response': get_object(record, 'response', {}),
            'failure': get_object(record, 'failure', {}),
        }
        if (
            content_type.lower().startswith('application/x-www-form-urlencoded')
            and post_data is not None
            and not base64_encoded
        ):
            result['form_fields'] = [
                {'name': name, 'value': value} for name, value in parse_qsl(post_data, keep_blank_values=True)
            ]
        if 'json' in content_type.lower() and post_data is not None and not truncated:
            with suppress(json.JSONDecodeError, ValueError):
                result['json_value'] = normalize_json_value(json.loads(post_data), 'request JSON')
        if content_type.lower().startswith('multipart/form-data'):
            result['limitations'] = ['CDP may omit file contents from multipart request data.']
        elif len(entries) > 1 and post_data is None:
            result['limitations'] = ['Multiple postDataEntries were preserved and were not reconstructed.']
        _trace_event(
            client_id, 'network_get_request', 'success', tab_id, summary=f'request {request_id}; {returned_size} bytes'
        )
        return result
    except StructuredError as exc:
        return exc.to_dict()
    except (ValueError, TypeError):
        return StructuredError(ErrorCode.EXECUTION_ERROR, 'Captured request data is invalid').to_dict()


async def network_get_response(
    client_id: str, tab_id: str, request_id: str, max_bytes: int = 65536, redact: bool = True
) -> JsonObject:
    if not request_id.strip() or max_bytes < 1:
        return StructuredError(ErrorCode.INVALID_INPUT, 'request_id and positive max_bytes are required').to_dict()
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        if request_id not in get_inspection_manager().get(tab_id).requests:
            return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, 'Request not found').to_dict()
        body = await asyncio.wait_for(tab.get_network_response_body(request_id), 10.0)
        value, original, truncated = _truncate_text(body, max_bytes)
        if redact:
            value = _redact_sensitive(value)
        return {
            'success': True,
            'body': value,
            'truncated': truncated,
            'size_bytes': len(value.encode()),
            'original_size_bytes': original,
        }
    except StructuredError as exc:
        return exc.to_dict()
    except Exception:
        return StructuredError(ErrorCode.EXECUTION_ERROR, 'Failed to get response body').to_dict()


async def network_clear(client_id: str, tab_id: str) -> JsonObject:
    try:
        get_registry().get_tab(client_id, tab_id)
        get_inspection_manager().get(tab_id).clear_network()
        return {'success': True, 'tab_id': tab_id, 'cleared': True}
    except StructuredError as exc:
        return exc.to_dict()


async def network_summary(client_id: str, tab_id: str) -> JsonObject:
    result = await network_list(client_id, tab_id, limit=1000)
    if not result.get('success'):
        return result
    methods: dict[str, int] = {}
    for value in get_array(result, 'events', []):
        method = get_string(require_json_object(value), 'method')
        methods[method] = methods.get(method, 0) + 1
    method_values: JsonObject = dict(methods)
    return {'success': True, 'total': get_int(result, 'total'), 'methods': method_values}


def _redact_sensitive(text: str) -> str:
    return re.sub(r'(?i)(authorization|cookie|access_token|refresh_token)(["\s:=]+)[^"\s,}]+', r'\1\2[REDACTED]', text)


def _trace_event(
    client_id: str, tool: str, status: str, tab_id: str = '', error_code: str = '', summary: str = ''
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
