"""Direct authenticated HTTP tools."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlencode

import aiohttp

from pydoll_mcp_server.browser.http_client import (
    MAX_BODY_BYTES,
    HttpField,
    HttpRequestSpec,
    build_session_context,
    execute_http_request,
    prepare_payload,
    resolve_request_url,
    validate_headers,
    validate_query,
)
from pydoll_mcp_server.browser.inspection import get_inspection_manager
from pydoll_mcp_server.browser.operations import get_operation_manager
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.config import get_timeout_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_object,
    get_string,
    require_json_object,
)

MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
OMITTED_REPLAY_HEADERS = {'host', 'content-length', 'transfer-encoding', 'connection', 'cookie'}


async def http_request(
    client_id: str,
    tab_id: str,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    query: list[HttpField] | None = None,
    json_value: object = None,
    form_fields: list[HttpField] | None = None,
    body: str | None = None,
    body_base64: str | None = None,
    content_type: str = '',
    follow_redirects: bool = True,
    allow_cross_origin: bool = False,
    timeout: float = 30.0,
    max_response_bytes: int = 1_048_576,
    operation_id: str = '',
) -> JsonObject:
    try:
        return await get_operation_manager().run(
            client_id,
            operation_id,
            _http_request_impl(
                client_id,
                tab_id,
                method,
                url,
                headers,
                query,
                json_value,
                form_fields,
                body,
                body_base64,
                content_type,
                follow_redirects,
                allow_cross_origin,
                timeout,
                max_response_bytes,
            ),
        )
    except StructuredError as exc:
        return exc.to_dict()
    except asyncio.TimeoutError:
        return StructuredError(ErrorCode.TIMEOUT, 'HTTP request timed out', retryable=True).to_dict()
    except asyncio.CancelledError:
        return StructuredError(ErrorCode.EXECUTION_ERROR, 'HTTP request was cancelled', retryable=True).to_dict()
    except aiohttp.ClientError:
        return StructuredError(ErrorCode.EXECUTION_ERROR, 'HTTP request failed', retryable=True).to_dict()
    except Exception:
        return StructuredError(ErrorCode.INTERNAL_ERROR, 'Unexpected HTTP request failure').to_dict()


async def _http_request_impl(
    client_id: str,
    tab_id: str,
    method: str,
    url: str,
    headers: dict[str, str] | None,
    query: list[HttpField] | None,
    json_value: object,
    form_fields: list[HttpField] | None,
    body: str | None,
    body_base64: str | None,
    content_type: str,
    follow_redirects: bool,
    allow_cross_origin: bool,
    timeout: float,
    max_response_bytes: int,
) -> JsonObject:
    normalized_method = method.upper().strip()
    from pydoll_mcp_server.browser.http_client import ALLOWED_METHODS

    if normalized_method not in ALLOWED_METHODS:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Unsupported HTTP method')
    max_timeout = get_timeout_config().max_timeout
    if not 0 < timeout <= max_timeout:
        raise StructuredError(ErrorCode.INVALID_INPUT, f'timeout must be between 0 and {max_timeout}')
    if not 1 <= max_response_bytes <= MAX_BODY_BYTES:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'max_response_bytes must be between 1 and 16777216')
    tab, browser = get_registry().resolve_tab_with_browser(client_id, tab_id)
    context = await build_session_context(tab, browser)
    request_headers = validate_headers(headers)
    payload = prepare_payload(json_value, form_fields, body, body_base64, content_type, request_headers)
    request_body = payload['body']
    if len(request_body) > MAX_BODY_BYTES:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Request body exceeds the 16 MiB limit')
    if 'content_type' in payload and not any(key.lower() == 'content-type' for key in request_headers):
        request_headers['Content-Type'] = payload['content_type']
    resolved = resolve_request_url(url, context.current_url, allow_cross_origin)
    query_values = validate_query(query)
    if query_values:
        resolved = f'{resolved}{"&" if "?" in resolved else "?"}{urlencode(query_values)}'
    spec = HttpRequestSpec(
        method=normalized_method,
        url=resolved,
        headers=request_headers,
        body=request_body,
        follow_redirects=follow_redirects,
        allow_cross_origin=allow_cross_origin,
        timeout=timeout,
        max_response_bytes=max_response_bytes,
    )
    started = time.monotonic()
    result = await execute_http_request(context, spec)
    _trace_http(client_id, 'http_request', tab_id, result, started)
    return result


async def network_replay_request(
    client_id: str,
    tab_id: str,
    request_id: str,
    confirm_side_effects: bool = False,
    follow_redirects: bool = True,
    allow_cross_origin: bool = False,
    timeout: float = 30.0,
    max_response_bytes: int = 1_048_576,
    operation_id: str = '',
) -> JsonObject:
    if not request_id.strip():
        return StructuredError(ErrorCode.INVALID_INPUT, 'request_id is required').to_dict()
    try:
        get_registry().get_tab(client_id, tab_id)
        record = get_inspection_manager().get(tab_id).requests.get(request_id)
        if record is None:
            return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, 'Request not found').to_dict()
        request = get_object(record, 'request', {})
        method = get_string(request, 'method').upper()
        if method in MUTATING_METHODS and not confirm_side_effects:
            return StructuredError(
                ErrorCode.PERMISSION_DENIED,
                'Replaying this method requires confirm_side_effects=true',
            ).to_dict()
        post_data_value = request.get('postData')
        post_data = post_data_value if isinstance(post_data_value, str) else None
        entries = get_array(request, 'postDataEntries', [])
        content_type = _content_type(get_object(request, 'headers', {}))
        if content_type.lower().startswith('multipart/form-data') and post_data is None:
            return StructuredError(
                ErrorCode.UNSUPPORTED, 'Multipart replay requires the original complete payload'
            ).to_dict()
        if len(entries) > 1 and post_data is None:
            return StructuredError(
                ErrorCode.UNSUPPORTED, 'Multiple post data entries cannot be reconstructed'
            ).to_dict()
        body_base64 = ''
        if post_data is None and len(entries) == 1:
            body_base64 = get_string(require_json_object(entries[0], 'post data entry'), 'bytes')
        raw_headers = get_object(
            get_object(record, 'request_extra_info', {}), 'headers', get_object(request, 'headers', {})
        )
        replay_headers: dict[str, str] = {}
        omitted: list[str] = []
        for name, value in raw_headers.items():
            if name.lower() in OMITTED_REPLAY_HEADERS:
                omitted.append(name)
            elif isinstance(value, str):
                replay_headers[name] = value
        result = await http_request(
            client_id=client_id,
            tab_id=tab_id,
            method=method,
            url=get_string(request, 'url'),
            headers=replay_headers,
            body=post_data if post_data is not None else None,
            body_base64=body_base64 or None,
            content_type=content_type,
            follow_redirects=follow_redirects,
            allow_cross_origin=allow_cross_origin,
            timeout=timeout,
            max_response_bytes=max_response_bytes,
            operation_id=operation_id,
        )
        if result.get('success'):
            result['source_request_id'] = request_id
            omitted_values: JsonArray = list(omitted)
            result['omitted_headers'] = omitted_values
        return result
    except StructuredError as exc:
        return exc.to_dict()
    except Exception:
        return StructuredError(ErrorCode.INTERNAL_ERROR, 'Unexpected request replay failure').to_dict()


def _content_type(headers: JsonObject) -> str:
    return next(
        (value for name, value in headers.items() if name.lower() == 'content-type' and isinstance(value, str)), ''
    )


def _trace_http(client_id: str, tool: str, tab_id: str, result: JsonObject, started: float) -> None:
    from pydoll_mcp_server.diagnostics.trace import TraceEvent, get_trace_manager

    redirects = get_array(result, 'redirect_chain', [])
    status = result.get('status')
    size = result.get('returned_size_bytes')
    get_trace_manager().add_event_to_active(
        client_id,
        TraceEvent(
            timestamp=time.time(),
            tool=tool,
            status='success',
            duration_ms=(time.monotonic() - started) * 1000,
            tab_id=tab_id,
            summary=f'HTTP {status}; {len(redirects)} redirects; {size} bytes',
        ),
    )
