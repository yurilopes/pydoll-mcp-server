"""Authentication module for bearer token validation."""

from __future__ import annotations

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    BaseUser,
    SimpleUser,
)
from starlette.requests import HTTPConnection

from pydoll_mcp_server.config import get_config


class BearerUser(SimpleUser):
    def __init__(self, username: str) -> None:
        super().__init__(username)


class BearerTokenBackend(AuthenticationBackend):
    async def authenticate(
        self, conn: HTTPConnection
    ) -> tuple[AuthCredentials, BaseUser] | None:
        if conn.url.path == '/health':
            return AuthCredentials([]), BearerUser('public')

        config = get_config()
        if not config.auth_enabled:
            return AuthCredentials(['authenticated']), BearerUser('anonymous')

        auth_header = conn.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            raise AuthenticationError('Bearer token required')

        token = auth_header[7:].strip()
        if token != config.auth_token:
            raise AuthenticationError('Invalid bearer token')

        return AuthCredentials(['authenticated']), BearerUser('authenticated')


class ClientIdentity:
    def __init__(self, raw_client_id: str) -> None:
        invalid_chars = {'/', '\\', '..', ':', '*', '?', '"', '<', '>', '|'}
        sanitized = raw_client_id
        for ch in invalid_chars:
            sanitized = sanitized.replace(ch, '_')
        sanitized = sanitized.strip().strip('.')[:64]
        if not sanitized:
            sanitized = 'unknown'
        self.raw = raw_client_id
        self.safe = sanitized

    def __str__(self) -> str:
        return self.safe
