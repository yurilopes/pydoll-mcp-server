"""Tests for security module - redaction and permissions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pydoll_mcp_server.logging import OperationLog, redact
from pydoll_mcp_server.security.policy import (
    PathAllowlist,
    is_sensitive_field,
    redact_dict,
)


class TestRedaction:
    def test_is_sensitive_field(self) -> None:
        assert is_sensitive_field('password') is True
        assert is_sensitive_field('PASSWORD') is True
        assert is_sensitive_field('secret-token') is True
        assert is_sensitive_field('api_key') is True
        assert is_sensitive_field('apiKey') is True
        assert is_sensitive_field('authorization') is True
        assert is_sensitive_field('username') is False
        assert is_sensitive_field('name') is False

    def test_redact_sensitive_values(self) -> None:
        data = {
            'username': 'john',
            'password': 'secret123',
            'api_key': 'sk-abc123',
            'name': 'John',
        }
        result = redact_dict(data)
        assert result['username'] == 'john'
        assert result['password'] == '[REDACTED]'
        assert result['api_key'] == '[REDACTED]'
        assert result['name'] == 'John'

    def test_redact_nested_dict(self) -> None:
        data = {
            'user': {'name': 'john', 'token': 'abc'},
            'public': 'value',
        }
        result = redact_dict(data)
        assert result['user']['token'] == '[REDACTED]'
        assert result['public'] == 'value'

    def test_redact_list_with_dicts(self) -> None:
        data = {
            'items': [
                {'name': 'i1', 'password': 'p1'},
                {'name': 'i2', 'secret': 's2'},
            ],
        }
        result = redact_dict(data)
        assert result['items'][0]['password'] == '[REDACTED]'
        assert result['items'][1]['secret'] == '[REDACTED]'

    def test_csrf_sensitive(self) -> None:
        assert is_sensitive_field('csrf_token') is True
        assert is_sensitive_field('XSRF-TOKEN') is True

    def test_session_sensitive(self) -> None:
        assert is_sensitive_field('session_id') is True
        assert is_sensitive_field('Session-Id') is True

    def test_redact_all(self) -> None:
        data = {'a': '1', 'b': '2'}
        result = redact_dict(data, redact_all=True)
        assert result == {'a': '[REDACTED]', 'b': '[REDACTED]'}

    def test_log_redaction_removes_json_token_and_cookie_values(self) -> None:
        payload = OperationLog(
            client_id='client-1',
            tool='test',
            extra={
                'token': 'secret-token-value',
                'cookie': 'sid=secret-cookie',
                'authorization': 'Bearer secret-bearer',
            },
        ).to_json()

        redacted = redact(payload)

        assert 'secret-token-value' not in redacted
        assert 'secret-cookie' not in redacted
        assert 'secret-bearer' not in redacted
        assert '[REDACTED]' in redacted or '[REDACTED_COOKIE]' in redacted


class TestElementAttributeRedaction:
    @pytest.mark.asyncio
    async def test_element_get_attribute_redacts_sensitive_attribute(self, monkeypatch) -> None:
        from pydoll_mcp_server.tools import elements as element_tools

        class FakeElement:
            def get_attribute(self, name: str) -> str:
                return 'secret-value'

        async def resolve_element(tab_info, element_id):
            return FakeElement()

        class FakeRegistry:
            def get_tab(self, client_id: str, tab_id: str):
                return SimpleNamespace(tab_id=tab_id, document_generation=1)

        monkeypatch.setattr(element_tools, 'get_registry', lambda: FakeRegistry())
        monkeypatch.setattr(element_tools, '_resolve_element', resolve_element)

        result = await element_tools.element_get_attribute(
            'client-1',
            'tab-1',
            'el-1',
            'data-access-token',
        )

        assert result['success'] is True
        assert result['value'] == '[REDACTED]'
        assert result['redacted'] is True


class TestStorageRedaction:
    @pytest.mark.asyncio
    async def test_cookies_get_redacts_values_by_default(self, monkeypatch) -> None:
        from pydoll_mcp_server.tools import storage as storage_tools

        class FakeTab:
            async def get_cookies(self):
                return [{'name': 'sid', 'value': 'secret-cookie', 'domain': 'example.test'}]

        class FakeRegistry:
            def get_tab(self, client_id: str, tab_id: str):
                return SimpleNamespace(_pydoll_tab=FakeTab())

        monkeypatch.setattr(storage_tools, 'get_registry', lambda: FakeRegistry())

        result = await storage_tools.cookies_get('client-1', tab_id='tab-1')

        assert result['success'] is True
        assert result['cookies'][0]['value'] == '[REDACTED]'
        assert result['redacted'] is True

    @pytest.mark.asyncio
    async def test_storage_get_redacts_values_by_default(self, monkeypatch) -> None:
        from pydoll_mcp_server.tools import storage as storage_tools

        class FakeTab:
            async def execute_script(self, script: str, return_by_value: bool = False):
                return {
                    'result': {
                        'result': {
                            'value': {
                                'local': {'token': 'local-secret'},
                                'session': {'sid': 'session-secret'},
                            }
                        }
                    }
                }

        class FakeRegistry:
            def get_tab(self, client_id: str, tab_id: str):
                return SimpleNamespace(_pydoll_tab=FakeTab())

        monkeypatch.setattr(storage_tools, 'get_registry', lambda: FakeRegistry())

        result = await storage_tools.storage_get('client-1', 'tab-1')

        assert result['success'] is True
        assert result['storage']['local']['token'] == '[REDACTED]'
        assert result['storage']['session']['sid'] == '[REDACTED]'
        assert result['redacted'] is True


class TestPathAllowlist:
    def test_basic_allow(self) -> None:
        allowlist = PathAllowlist(['/tmp/allowed'])
        assert allowlist.is_allowed('/tmp/allowed/file.txt') is True

    def test_deny_outside(self) -> None:
        allowlist = PathAllowlist(['/tmp/allowed'])
        assert allowlist.is_allowed('/etc/passwd') is False

    def test_deny_parent_traversal(self) -> None:
        allowlist = PathAllowlist(['/tmp/allowed'])
        assert allowlist.is_allowed('/tmp/allowed/../../../etc/passwd') is False

    def test_validate_read(self) -> None:
        allowlist = PathAllowlist(['/tmp/allowed'])
        allowlist.validate_read('/tmp/allowed/x.txt')

    def test_validate_read_raises(self) -> None:
        allowlist = PathAllowlist(['/tmp/allowed'])
        with __import__('pytest').raises(PermissionError):
            allowlist.validate_read('/etc/secret.txt')

    def test_validate_upload_denied(self) -> None:
        allowlist = PathAllowlist(['/tmp/allowed'])
        denied = allowlist.validate_upload(['/tmp/allowed/a.txt', '/etc/b.txt'])
        assert denied == ['/etc/b.txt']

    def test_multiple_allowed_dirs(self) -> None:
        allowlist = PathAllowlist(['/tmp/a', '/tmp/b'])
        assert allowlist.is_allowed('/tmp/a/file.txt') is True
        assert allowlist.is_allowed('/tmp/b/file.txt') is True
        assert allowlist.is_allowed('/tmp/c/file.txt') is False

    def test_prefix_bypass_blocked(self) -> None:
        allowlist = PathAllowlist(['/tmp/allowed'])
        assert allowlist.is_allowed('/tmp/allowed-other/file.txt') is False
