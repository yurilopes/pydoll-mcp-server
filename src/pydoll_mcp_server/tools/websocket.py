"""WebSocket inspection tools built on Chromium network events."""

from __future__ import annotations

import re
import time

from pydoll.protocol.network.events import NetworkEvent

from pydoll_mcp_server.browser.inspection import get_inspection_manager
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_bool,
    get_float,
    get_int,
    get_object,
    get_string,
    require_json_object,
)

MAX_FRAME_CAPTURE_BYTES = 1_048_576
MAX_FRAME_RETURN_BYTES = 1_048_576
_URL_REDACT = re.compile(r'([?&])(token|key|secret|auth|password|api_key|apikey)=[^&\s]*', re.I)
_SENSITIVE_TEXT_REDACT = re.compile(
    r'(?i)(authorization|cookie|access_token|refresh_token|token|password)(["\s:=]+)[^"\s,}]+',
)
_SENSITIVE_HEADER_NAMES = {
    'authorization',
    'cookie',
    'proxy-authorization',
    'set-cookie',
    'x-api-key',
    'x-auth-token',
}

WEBSOCKET_NETWORK_EVENTS: tuple[NetworkEvent, ...] = (
    NetworkEvent.WEBSOCKET_CREATED,
    NetworkEvent.WEBSOCKET_WILL_SEND_HANDSHAKE_REQUEST,
    NetworkEvent.WEBSOCKET_HANDSHAKE_RESPONSE_RECEIVED,
    NetworkEvent.WEBSOCKET_FRAME_SENT,
    NetworkEvent.WEBSOCKET_FRAME_RECEIVED,
    NetworkEvent.WEBSOCKET_FRAME_ERROR,
    NetworkEvent.WEBSOCKET_CLOSED,
)


def _redact_url(url: str) -> str:
    return _URL_REDACT.sub(r'\1\2=REDACTED', url)


def _redact_sensitive_text(text: str) -> str:
    return _SENSITIVE_TEXT_REDACT.sub(r'\1\2[REDACTED]', text)


def _truncate_text(text: str, max_bytes: int) -> tuple[str, int, bool]:
    raw = text.encode('utf-8')
    if len(raw) <= max_bytes:
        return text, len(raw), False
    return raw[:max_bytes].decode('utf-8', errors='ignore'), len(raw), True


def _connection(tab_id: str, request_id: str) -> JsonObject:
    state = get_inspection_manager().get(tab_id)
    return state.websockets.get(request_id, {'request_id': request_id})


async def capture_websocket_event(tab_id: str, event_value: object) -> None:
    event = require_json_object(event_value, 'websocket event')
    method = get_string(event, 'method')
    params = get_object(event, 'params', {})
    request_id = get_string(params, 'requestId')
    if not request_id:
        return

    state = get_inspection_manager().get(tab_id)
    record = dict(_connection(tab_id, request_id))
    if method == NetworkEvent.WEBSOCKET_CREATED:
        record.update(
            {
                'request_id': request_id,
                'url': get_string(params, 'url'),
                'initiator': get_object(params, 'initiator', {}),
                'created_timestamp': get_float(params, 'timestamp'),
            }
        )
    elif method == NetworkEvent.WEBSOCKET_WILL_SEND_HANDSHAKE_REQUEST:
        record.update(
            {
                'handshake_request': get_object(params, 'request', {}),
                'handshake_request_timestamp': get_float(params, 'timestamp'),
                'handshake_request_wall_time': get_float(params, 'wallTime'),
            }
        )
    elif method == NetworkEvent.WEBSOCKET_HANDSHAKE_RESPONSE_RECEIVED:
        record.update(
            {
                'handshake_response': get_object(params, 'response', {}),
                'handshake_response_timestamp': get_float(params, 'timestamp'),
            }
        )
    elif method == NetworkEvent.WEBSOCKET_FRAME_SENT:
        state.add_websocket_frame(_frame_record(request_id, params, 'sent'))
    elif method == NetworkEvent.WEBSOCKET_FRAME_RECEIVED:
        state.add_websocket_frame(_frame_record(request_id, params, 'received'))
    elif method == NetworkEvent.WEBSOCKET_FRAME_ERROR:
        error = get_string(params, 'errorMessage')
        record['last_error'] = error
        record['last_error_timestamp'] = get_float(params, 'timestamp')
        state.add_websocket_frame(
            {
                'request_id': request_id,
                'direction': 'error',
                'timestamp': get_float(params, 'timestamp'),
                'opcode': 0,
                'mask': False,
                'payload_data': '',
                'payload_size_bytes': 0,
                'returned_size_bytes': 0,
                'base64_encoded': False,
                'truncated': False,
                'error': error,
            }
        )
    elif method == NetworkEvent.WEBSOCKET_CLOSED:
        record['closed_timestamp'] = get_float(params, 'timestamp')
    state.upsert_websocket(request_id, record)


def _frame_record(request_id: str, params: JsonObject, direction: str) -> JsonObject:
    frame = get_object(params, 'response', {})
    payload = get_string(frame, 'payloadData')
    payload, original_size, truncated = _truncate_text(payload, MAX_FRAME_CAPTURE_BYTES)
    opcode = get_int(frame, 'opcode')
    return {
        'request_id': request_id,
        'direction': direction,
        'timestamp': get_float(params, 'timestamp'),
        'opcode': opcode,
        'mask': get_bool(frame, 'mask'),
        'payload_data': payload,
        'payload_size_bytes': original_size,
        'returned_size_bytes': len(payload.encode('utf-8')),
        'base64_encoded': opcode != 1,
        'truncated': truncated,
    }


def _state_name(record: JsonObject) -> str:
    if 'closed_timestamp' in record:
        return 'closed'
    if 'last_error' in record:
        return 'error'
    return 'open'


def _summary(record: JsonObject, frame_count: int) -> JsonObject:
    response = get_object(record, 'handshake_response', {})
    return {
        'request_id': get_string(record, 'request_id'),
        'url': _redact_url(get_string(record, 'url')),
        'state': _state_name(record),
        'status': get_int(response, 'status'),
        'created_timestamp': get_float(record, 'created_timestamp'),
        'closed_timestamp': get_float(record, 'closed_timestamp'),
        'frame_count': frame_count,
        'has_handshake_request': 'handshake_request' in record,
        'has_handshake_response': 'handshake_response' in record,
        'has_error': 'last_error' in record,
    }


def _frame_counts(tab_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for frame in get_inspection_manager().get(tab_id).websocket_frames:
        request_id = get_string(frame, 'request_id')
        counts[request_id] = counts.get(request_id, 0) + 1
    return counts


async def websocket_list(
    client_id: str,
    tab_id: str,
    filter_url: str = '',
    request_id: str = '',
    state: str = '',
    limit: int = 100,
) -> JsonObject:
    if not 1 <= limit <= 1000:
        return StructuredError(ErrorCode.INVALID_INPUT, 'limit must be between 1 and 1000').to_dict()
    if state and state not in {'open', 'closed', 'error'}:
        return StructuredError(ErrorCode.INVALID_INPUT, 'state must be open, closed, or error').to_dict()
    try:
        get_registry().get_tab(client_id, tab_id)
        records = list(get_inspection_manager().get(tab_id).websockets.values())
        counts = _frame_counts(tab_id)
        selected: list[JsonObject] = []
        for record in records:
            current_request_id = get_string(record, 'request_id')
            if request_id and request_id != current_request_id:
                continue
            if filter_url and filter_url not in get_string(record, 'url'):
                continue
            if state and state != _state_name(record):
                continue
            selected.append(_summary(record, counts.get(current_request_id, 0)))
        connections: JsonArray = list(selected[-limit:])
        _trace_event(client_id, 'websocket_list', 'success', tab_id, summary=f'{len(connections)} connections')
        return {'success': True, 'connections': connections, 'count': len(connections), 'total': len(selected)}
    except StructuredError as exc:
        return exc.to_dict()


async def websocket_get(
    client_id: str,
    tab_id: str,
    request_id: str,
    include_frames: bool = True,
    max_frames: int = 100,
    max_payload_bytes: int = 65_536,
    redact: bool = True,
) -> JsonObject:
    if not request_id.strip():
        return StructuredError(ErrorCode.INVALID_INPUT, 'request_id is required').to_dict()
    if not 0 <= max_frames <= 1000:
        return StructuredError(ErrorCode.INVALID_INPUT, 'max_frames must be between 0 and 1000').to_dict()
    if not 1 <= max_payload_bytes <= MAX_FRAME_RETURN_BYTES:
        return StructuredError(ErrorCode.INVALID_INPUT, 'max_payload_bytes must be between 1 and 1048576').to_dict()
    try:
        get_registry().get_tab(client_id, tab_id)
        state = get_inspection_manager().get(tab_id)
        record = state.websockets.get(request_id)
        if record is None:
            message = (
                'WebSocket capture was discarded by the per-tab memory limit'
                if request_id in state.discarded_websocket_ids
                else 'WebSocket not found'
            )
            return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, message).to_dict()
        result = _connection_view(record, redact)
        if include_frames:
            frames = [frame for frame in state.websocket_frames if get_string(frame, 'request_id') == request_id]
            result['frames'] = [_frame_view(frame, max_payload_bytes, redact) for frame in frames[-max_frames:]]
            result['frame_count'] = len(frames)
            result['returned_frame_count'] = min(len(frames), max_frames)
        _trace_event(client_id, 'websocket_get', 'success', tab_id, summary=f'websocket {request_id}')
        return result
    except StructuredError as exc:
        return exc.to_dict()


async def websocket_frames_list(
    client_id: str,
    tab_id: str,
    request_id: str = '',
    direction: str = '',
    opcode: int | None = None,
    filter_payload: str = '',
    limit: int = 100,
    max_payload_bytes: int = 65_536,
    redact: bool = True,
) -> JsonObject:
    if direction and direction not in {'sent', 'received', 'error'}:
        return StructuredError(ErrorCode.INVALID_INPUT, 'direction must be sent, received, or error').to_dict()
    if not 1 <= limit <= 1000:
        return StructuredError(ErrorCode.INVALID_INPUT, 'limit must be between 1 and 1000').to_dict()
    if opcode is not None and not 0 <= opcode <= 15:
        return StructuredError(ErrorCode.INVALID_INPUT, 'opcode must be between 0 and 15').to_dict()
    if not 1 <= max_payload_bytes <= MAX_FRAME_RETURN_BYTES:
        return StructuredError(ErrorCode.INVALID_INPUT, 'max_payload_bytes must be between 1 and 1048576').to_dict()
    try:
        get_registry().get_tab(client_id, tab_id)
        selected: list[JsonObject] = []
        for frame in get_inspection_manager().get(tab_id).websocket_frames:
            if request_id and request_id != get_string(frame, 'request_id'):
                continue
            if direction and direction != get_string(frame, 'direction'):
                continue
            if opcode is not None and opcode != get_int(frame, 'opcode'):
                continue
            if filter_payload and filter_payload not in get_string(frame, 'payload_data'):
                continue
            selected.append(_frame_view(frame, max_payload_bytes, redact))
        frames: JsonArray = list(selected[-limit:])
        _trace_event(client_id, 'websocket_frames_list', 'success', tab_id, summary=f'{len(frames)} frames')
        return {'success': True, 'frames': frames, 'count': len(frames), 'total': len(selected)}
    except StructuredError as exc:
        return exc.to_dict()


def _connection_view(record: JsonObject, redact: bool) -> JsonObject:
    url = _redact_url(get_string(record, 'url')) if redact else get_string(record, 'url')
    return {
        'success': True,
        'request_id': get_string(record, 'request_id'),
        'url': url,
        'state': _state_name(record),
        'initiator': get_object(record, 'initiator', {}),
        'created_timestamp': get_float(record, 'created_timestamp'),
        'closed_timestamp': get_float(record, 'closed_timestamp'),
        'handshake_request': _handshake_view(get_object(record, 'handshake_request', {}), redact),
        'handshake_request_timestamp': get_float(record, 'handshake_request_timestamp'),
        'handshake_request_wall_time': get_float(record, 'handshake_request_wall_time'),
        'handshake_response': _handshake_view(get_object(record, 'handshake_response', {}), redact),
        'handshake_response_timestamp': get_float(record, 'handshake_response_timestamp'),
        'last_error': get_string(record, 'last_error'),
        'last_error_timestamp': get_float(record, 'last_error_timestamp'),
    }


def _handshake_view(value: JsonObject, redact: bool) -> JsonObject:
    if not redact:
        return dict(value)
    result = dict(value)
    for key in ('headers', 'requestHeaders'):
        headers = value.get(key)
        if isinstance(headers, dict):
            result[key] = _redact_headers(require_json_object(headers, key))
    return result


def _redact_headers(headers: JsonObject) -> JsonObject:
    result: JsonObject = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADER_NAMES:
            result[key] = '[REDACTED]'
        elif isinstance(value, str):
            result[key] = _redact_sensitive_text(value)
        else:
            result[key] = value
    return result


def _frame_view(frame: JsonObject, max_payload_bytes: int, redact: bool) -> JsonObject:
    payload = get_string(frame, 'payload_data')
    if redact:
        payload = _redact_sensitive_text(payload)
    payload, original_return_size, return_truncated = _truncate_text(payload, max_payload_bytes)
    return {
        'frame_id': get_string(frame, 'frame_id'),
        'request_id': get_string(frame, 'request_id'),
        'direction': get_string(frame, 'direction'),
        'timestamp': get_float(frame, 'timestamp'),
        'opcode': get_int(frame, 'opcode'),
        'mask': get_bool(frame, 'mask'),
        'payload_data': payload,
        'payload_size_bytes': get_int(frame, 'payload_size_bytes'),
        'returned_size_bytes': len(payload.encode('utf-8')),
        'base64_encoded': get_bool(frame, 'base64_encoded'),
        'truncated': get_bool(frame, 'truncated') or return_truncated,
        'capture_truncated': get_bool(frame, 'truncated'),
        'return_truncated': return_truncated,
        'return_original_size_bytes': original_return_size,
        'error': get_string(frame, 'error'),
    }


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
