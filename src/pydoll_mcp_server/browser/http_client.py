"""Bounded HTTP requests sharing the owning browser session."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from contextlib import suppress
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from urllib.parse import urlencode, urljoin, urlsplit

import aiohttp
from pydoll.protocol.network.types import Cookie, CookieParam
from typing_extensions import NotRequired, TypedDict

from pydoll_mcp_server.browser.cdp_helpers import get_user_agent
from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.models import BrowserInfo, TabInfo
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, normalize_json_value

MAX_URL_LENGTH = 16 * 1024
MAX_BODY_BYTES = 16 * 1024 * 1024
MAX_HEADER_BYTES = 128 * 1024
MAX_HEADERS = 256
MAX_REDIRECTS = 20
ALLOWED_METHODS = {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'}


class HttpField(TypedDict):
    name: str
    value: str


class HttpRequestSpec(TypedDict):
    method: str
    url: str
    headers: dict[str, str]
    body: bytes
    follow_redirects: bool
    allow_cross_origin: bool
    timeout: float
    max_response_bytes: int


class PreparedPayload(TypedDict):
    body: bytes
    content_type: NotRequired[str]


@dataclass(frozen=True)
class SessionContext:
    tab: TabInfo
    browser: BrowserInfo
    current_url: str
    user_agent: str
    cookies: list[Cookie]


def prepare_payload(
    json_value: object,
    form_fields: list[HttpField] | None,
    body: str | None,
    body_base64: str | None,
    content_type: str,
    headers: dict[str, str],
) -> PreparedPayload:
    modes = sum(value is not None for value in (json_value, form_fields, body, body_base64))
    if modes > 1:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Only one request payload mode may be used')
    header_content_type = next((value for key, value in headers.items() if key.lower() == 'content-type'), '')
    if json_value is not None:
        raw = json.dumps(normalize_json_value(json_value), ensure_ascii=False, separators=(',', ':')).encode()
        return {'body': raw, 'content_type': header_content_type or 'application/json'}
    if form_fields is not None:
        _validate_fields(form_fields, 'form_fields')
        raw = urlencode([(field['name'], field['value']) for field in form_fields]).encode('ascii')
        return {'body': raw, 'content_type': header_content_type or 'application/x-www-form-urlencoded'}
    if body_base64 is not None:
        try:
            raw = base64.b64decode(body_base64, validate=True)
        except binascii.Error as exc:
            raise StructuredError(ErrorCode.INVALID_INPUT, 'body_base64 is not valid base64') from exc
        if not (header_content_type or content_type):
            raise StructuredError(ErrorCode.INVALID_INPUT, 'content_type is required for a raw body')
        return {'body': raw, 'content_type': header_content_type or content_type}
    if body is not None:
        if not (header_content_type or content_type):
            raise StructuredError(ErrorCode.INVALID_INPUT, 'content_type is required for a raw body')
        return {'body': body.encode('utf-8'), 'content_type': header_content_type or content_type}
    return {'body': b''}


def validate_headers(value: dict[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if len(value) > MAX_HEADERS:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Too many request headers')
    result: dict[str, str] = {}
    total = 0
    for name, item in value.items():
        if not name or '\r' in name or '\n' in name or ':' in name or '\r' in item or '\n' in item:
            raise StructuredError(ErrorCode.INVALID_INPUT, 'Invalid request header')
        total += len(name.encode()) + len(item.encode())
        result[name] = item
    if total > MAX_HEADER_BYTES:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Request headers exceed the size limit')
    return result


def resolve_request_url(value: str, current_url: str, allow_cross_origin: bool) -> str:
    resolved = urljoin(current_url, value)
    if len(resolved) > MAX_URL_LENGTH:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'URL exceeds the size limit')
    parsed = urlsplit(resolved)
    current = urlsplit(current_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Only absolute HTTP(S) destinations are allowed')
    if parsed.username or parsed.password:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Credentials embedded in URLs are not allowed')
    if not allow_cross_origin and parsed.hostname.lower() != (current.hostname or '').lower():
        raise StructuredError(ErrorCode.PERMISSION_DENIED, 'Cross-origin HTTP requests require allow_cross_origin=true')
    return resolved


async def execute_http_request(context: SessionContext, spec: HttpRequestSpec) -> JsonObject:
    proxy = _proxy_for(context.browser)
    headers = dict(spec['headers'])
    if not any(key.lower() == 'user-agent' for key in headers):
        headers['User-Agent'] = context.user_agent
    cookie_header = select_cookie_header(context.cookies, spec['url'])
    if cookie_header:
        headers['Cookie'] = cookie_header
    redirect_chain: JsonArray = []
    current_url = spec['url']
    method = spec['method']
    body = spec['body']
    deadline = asyncio.get_running_loop().time() + spec['timeout']
    response_cookies: list[CookieParam] = []
    timeout = aiohttp.ClientTimeout(total=spec['timeout'])
    async with aiohttp.ClientSession(timeout=timeout, cookie_jar=aiohttp.DummyCookieJar()) as session:
        for redirect_number in range(MAX_REDIRECTS + 1):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            async with session.request(
                method,
                current_url,
                headers=headers,
                data=body or None,
                proxy=proxy,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=remaining),
            ) as response:
                response_cookies.extend(_response_cookie_params(response.cookies, current_url))
                if response.status in {301, 302, 303, 307, 308} and spec['follow_redirects']:
                    location = response.headers.get('Location')
                    if not location:
                        return await _response_result(response, redirect_chain, spec['max_response_bytes'])
                    if redirect_number == MAX_REDIRECTS:
                        raise StructuredError(ErrorCode.EXECUTION_ERROR, 'HTTP redirect limit exceeded')
                    target = resolve_request_url(location, current_url, spec['allow_cross_origin'])
                    redirect_chain.append({'status': response.status, 'url': current_url, 'location': target})
                    current_url = target
                    if response.status == 303 or (response.status in {301, 302} and method == 'POST'):
                        method, body = 'GET', b''
                        headers.pop('Content-Type', None)
                    continue
                result = await _response_result(response, redirect_chain, spec['max_response_bytes'])
                if response_cookies:
                    async with tab_operation_lock(context.tab.tab_id):
                        await context.tab.pydoll_tab.set_cookies(response_cookies)
                return result
    raise StructuredError(ErrorCode.EXECUTION_ERROR, 'HTTP request did not produce a response')


async def build_session_context(tab: TabInfo, browser: BrowserInfo) -> SessionContext:
    async with tab_operation_lock(tab.tab_id):
        cookies = await tab.pydoll_tab.get_cookies()
        agent_result = await get_user_agent(tab.client_id, tab.tab_id)
    agent = agent_result.get('user_agent')
    return SessionContext(tab, browser, tab.url, agent if isinstance(agent, str) else '', cookies)


async def _response_result(response: aiohttp.ClientResponse, chain: JsonArray, max_bytes: int) -> JsonObject:
    collected = bytearray()
    async for chunk in response.content.iter_chunked(65536):
        remaining = max_bytes + 1 - len(collected)
        if remaining > 0:
            collected.extend(chunk[:remaining])
        if len(collected) > max_bytes:
            break
    truncated = len(collected) > max_bytes
    raw = bytes(collected[:max_bytes])
    content_type = response.headers.get('Content-Type', '')
    textual = content_type.startswith('text/') or any(
        token in content_type.lower() for token in ('json', 'xml', 'javascript', 'form-urlencoded')
    )
    if textual:
        charset = response.charset or 'utf-8'
        try:
            body = raw.decode(charset)
        except (LookupError, UnicodeDecodeError):
            body = raw.decode('utf-8', errors='replace')
        encoded = False
    else:
        body = base64.b64encode(raw).decode('ascii')
        encoded = True
    header_values: JsonObject = dict(response.headers.items())
    original = response.content_length
    return {
        'success': True,
        'status': response.status,
        'url': str(response.url),
        'headers': header_values,
        'body': body,
        'base64_encoded': encoded,
        'truncated': truncated,
        'original_size_bytes': original,
        'returned_size_bytes': len(raw),
        'redirect_chain': chain,
    }


def select_cookie_header(cookies: list[Cookie], url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    path = parsed.path or '/'
    now = time.time()
    values: list[str] = []
    for cookie in cookies:
        domain = cookie['domain'].lstrip('.')
        domain_match = host == domain or (cookie['domain'].startswith('.') and host.endswith(f'.{domain}'))
        if not domain_match or not path.startswith(cookie['path']) or (cookie['secure'] and parsed.scheme != 'https'):
            continue
        expires = cookie['expires']
        if expires > 0 and expires <= now:
            continue
        values.append(f'{cookie["name"]}={cookie["value"]}')
    return '; '.join(values)


def _response_cookie_params(cookies: SimpleCookie, url: str) -> list[CookieParam]:
    parsed = urlsplit(url)
    result: list[CookieParam] = []
    for morsel in cookies.values():
        domain = morsel['domain'] or parsed.hostname or ''
        path = morsel['path'] or '/'
        item = CookieParam(name=morsel.key, value=morsel.value, domain=domain, path=path)
        if morsel['secure']:
            item['secure'] = True
        if morsel['expires']:
            with suppress(TypeError, ValueError, OverflowError):
                item['expires'] = parsedate_to_datetime(morsel['expires']).timestamp()
        result.append(item)
    return result


def _proxy_for(browser: BrowserInfo) -> str | None:
    if not browser.proxy_launch_url:
        return None
    if browser.proxy_scheme not in {'http', 'https'}:
        raise StructuredError(ErrorCode.UNSUPPORTED, 'The configured proxy is not supported for direct HTTP requests')
    return browser.proxy_launch_url


def _validate_fields(fields: list[HttpField], label: str) -> None:
    for field in fields:
        if '\r' in field['name'] or '\n' in field['name'] or '\r' in field['value'] or '\n' in field['value']:
            raise StructuredError(ErrorCode.INVALID_INPUT, f'{label} contains an invalid line break')


def validate_query(fields: list[HttpField] | None) -> list[tuple[str, str]]:
    if fields is None:
        return []
    _validate_fields(fields, 'query')
    return [(field['name'], field['value']) for field in fields]
