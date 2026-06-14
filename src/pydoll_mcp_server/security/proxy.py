"""Strict proxy validation and credential-safe metadata."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from pydoll_mcp_server.errors import ErrorCode, StructuredError

ALLOWED_PROXY_SCHEMES = {'http', 'https', 'socks4', 'socks5'}


@dataclass(frozen=True)
class ProxyConfig:
    launch_url: str
    sanitized_url: str
    scheme: str
    host: str
    port: int
    has_credentials: bool
    bypass_list: str = ''

    def summary(self) -> dict[str, object]:
        return {
            'proxy_enabled': True,
            'proxy_scheme': self.scheme,
            'proxy_server': self.sanitized_url,
            'proxy_has_credentials': self.has_credentials,
            'proxy_bypass_list': self.bypass_list,
        }


def validate_proxy(proxy_server: str, proxy_bypass_list: str = '') -> ProxyConfig:
    value = proxy_server.strip()
    if not value:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'proxy_server cannot be empty')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Invalid proxy port') from exc
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_PROXY_SCHEMES:
        raise StructuredError(
            ErrorCode.INVALID_INPUT,
            f'Unsupported proxy scheme: {scheme or "missing"}. Use http, https, socks4, or socks5.',
        )
    if not parsed.hostname or port is None or not 1 <= port <= 65535:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Proxy must use scheme://host:port')
    if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Proxy URL cannot contain a path, query, or fragment')
    if any(char.isspace() for char in value) or '\r' in value or '\n' in value:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Proxy URL cannot contain whitespace')
    host = parsed.hostname
    if _is_blocked_host(host):
        raise StructuredError(ErrorCode.PERMISSION_DENIED, 'Loopback and unspecified proxy hosts are blocked')
    username = unquote(parsed.username or '')
    password = unquote(parsed.password or '')
    has_credentials = bool(username or password)
    if bool(username) != bool(password):
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Proxy credentials require both username and password')
    if len(username) > 512 or len(password) > 2048:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Proxy credentials exceed allowed size')
    bypass = _validate_bypass_list(proxy_bypass_list)
    display_host = f'[{host}]' if ':' in host else host
    sanitized = f'{scheme}://{display_host}:{port}'
    return ProxyConfig(value, sanitized, scheme, host, port, has_credentials, bypass)


def proxy_validate(proxy_server: str, proxy_bypass_list: str = '') -> dict[str, object]:
    try:
        config = validate_proxy(proxy_server, proxy_bypass_list)
    except StructuredError as exc:
        return exc.to_dict()
    return {'success': True, **config.summary()}


def _is_blocked_host(host: str) -> bool:
    lowered = host.lower().rstrip('.')
    if lowered == 'localhost':
        return True
    try:
        address = ipaddress.ip_address(lowered)
        return address.is_loopback or address.is_unspecified
    except ValueError:
        return False


def _validate_bypass_list(value: str) -> str:
    if len(value) > 4096 or '\r' in value or '\n' in value:
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Invalid proxy bypass list')
    entries = [entry.strip() for entry in value.split(',') if entry.strip()]
    if any('://' in entry or '@' in entry or any(char.isspace() for char in entry) for entry in entries):
        raise StructuredError(ErrorCode.INVALID_INPUT, 'Proxy bypass entries must be host patterns')
    return ','.join(entries)

