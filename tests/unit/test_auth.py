"""Tests for authentication module."""

from __future__ import annotations

from pydoll_mcp_server.auth import ClientIdentity


class TestClientIdentity:
    def test_simple_client_id(self) -> None:
        identity = ClientIdentity('my-client-123')
        assert str(identity) == 'my-client-123'

    def test_sanitize_path_traversal(self) -> None:
        identity = ClientIdentity('../../../etc/passwd')
        safe = str(identity)
        assert '..' not in safe
        assert '/' not in safe

    def test_sanitize_special_chars(self) -> None:
        identity = ClientIdentity('test:*?"<>|')
        safe = str(identity)
        assert ':' not in safe
        assert '*' not in safe

    def test_max_length(self) -> None:
        identity = ClientIdentity('a' * 100)
        assert len(str(identity)) <= 64

    def test_empty_defaults_to_unknown(self) -> None:
        identity = ClientIdentity('')
        assert str(identity) == 'unknown'

    def test_dots_stripped(self) -> None:
        identity = ClientIdentity('...test...')
        safe = str(identity)
        assert not safe.startswith('.')
        assert not safe.endswith('.')


class TestValidateToken:
    def test_disabled_auth_always_valid(self) -> None:
        pass
