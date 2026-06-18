"""Direct HTTP request validation contracts."""

from __future__ import annotations

import base64
import time

import pytest
from pydoll.protocol.network.types import Cookie, CookiePriority, CookieSourceScheme

from pydoll_mcp_server.browser.http_client import (
    prepare_payload,
    resolve_request_url,
    select_cookie_header,
    validate_headers,
    validate_query,
)
from pydoll_mcp_server.errors import ErrorCode, StructuredError

pytestmark = pytest.mark.unit


def test_form_payload_preserves_order_and_duplicates() -> None:
    result = prepare_payload(
        None,
        [
            {'name': 'instalacao', 'value': '4002229168'},
            {'name': 'tag', 'value': 'a'},
            {'name': 'tag', 'value': 'b'},
        ],
        None,
        None,
        '',
        {},
    )
    assert result['body'] == b'instalacao=4002229168&tag=a&tag=b'
    assert result.get('content_type') == 'application/x-www-form-urlencoded'


def test_payload_modes_are_mutually_exclusive() -> None:
    with pytest.raises(StructuredError) as raised:
        prepare_payload({'value': 1}, None, 'text', None, 'text/plain', {})
    assert raised.value.error_code == ErrorCode.INVALID_INPUT


def test_binary_body_is_decoded_exactly() -> None:
    raw = b'\x00\xffbinary'
    result = prepare_payload(None, None, None, base64.b64encode(raw).decode(), 'application/octet-stream', {})
    assert result['body'] == raw


def test_cross_origin_requires_explicit_permission() -> None:
    with pytest.raises(StructuredError) as raised:
        resolve_request_url('https://other.test/api', 'https://example.test/page', False)
    assert raised.value.error_code == ErrorCode.PERMISSION_DENIED
    assert resolve_request_url('/api', 'https://example.test/page', False) == 'https://example.test/api'


def test_credentials_in_url_are_rejected() -> None:
    with pytest.raises(StructuredError):
        resolve_request_url('https://user:secret@example.test/', 'https://example.test/', False)


def test_headers_and_query_reject_line_breaks() -> None:
    with pytest.raises(StructuredError):
        validate_headers({'X-Test': 'safe\r\ninjected: yes'})
    with pytest.raises(StructuredError):
        validate_query([{'name': 'safe', 'value': 'bad\nvalue'}])


def test_cookie_selection_respects_domain_path_secure_and_expiry() -> None:
    future = time.time() + 3600
    cookies: list[Cookie] = [
        _cookie('host', 'one', 'example.test', '/', False, future),
        _cookie('domain', 'two', '.example.test', '/api', True, future),
        _cookie('expired', 'three', 'example.test', '/', False, time.time() - 1),
        _cookie('other', 'four', 'other.test', '/', False, future),
    ]
    assert select_cookie_header(cookies, 'https://sub.example.test/api/value') == 'domain=two'
    assert select_cookie_header(cookies, 'http://example.test/') == 'host=one'


def _cookie(name: str, value: str, domain: str, path: str, secure: bool, expires: float) -> Cookie:
    return {
        'name': name,
        'value': value,
        'domain': domain,
        'path': path,
        'expires': expires,
        'size': len(name) + len(value),
        'httpOnly': False,
        'secure': secure,
        'session': False,
        'priority': CookiePriority.MEDIUM,
        'sameParty': False,
        'sourceScheme': CookieSourceScheme.SECURE if secure else CookieSourceScheme.NON_SECURE,
        'sourcePort': 443 if secure else 80,
    }
