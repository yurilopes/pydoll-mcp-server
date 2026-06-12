"""Network inspection tests for P2."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


class TestNetworkInspection:
    def test_redact_url_tokens(self) -> None:
        from pydoll_mcp_server.tools.inspection import _redact_url

        url = 'https://example.com/api?token=secret123&key=abc'
        redacted = _redact_url(url)
        assert 'secret123' not in redacted
        assert 'REDACTED' in redacted

    def test_redact_url_auth(self) -> None:
        from pydoll_mcp_server.tools.inspection import _redact_url

        url = 'https://example.com/api?auth=mysecret&password=hunter2'
        redacted = _redact_url(url)
        assert 'mysecret' not in redacted
        assert 'hunter2' not in redacted
        assert 'REDACTED' in redacted

    def test_normalize_network_log(self) -> None:
        from pydoll_mcp_server.tools.inspection import _normalize_network_log

        log = {
            'params': {
                'requestId': 'req-123',
                'request': {
                    'url': 'https://example.com/page',
                    'method': 'GET',
                },
                'type': 'Document',
                'timestamp': 1000.5,
            },
        }
        normalized = _normalize_network_log(log)
        assert normalized['request_id'] == 'req-123'
        assert normalized['url'] == 'https://example.com/page'
        assert normalized['method'] == 'GET'
        assert normalized['type'] == 'Document'

    def test_network_get_response_rejects_empty_request_id(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.tools.inspection import network_get_response

            async def _run():
                return await network_get_response('test', 'tab-test', '')

            result = asyncio.run(_run())
            assert result.get('error_code') == 'INVALID_INPUT'

    def test_network_normalize_empty_log(self) -> None:
        from pydoll_mcp_server.tools.inspection import _normalize_network_log

        normalized = _normalize_network_log({})
        assert normalized['request_id'] == ''
        assert normalized['url'] == ''

    def test_network_list_filters_empty_urls(self) -> None:
        logs = [
            {'params': {
                'requestId': 'r1', 'request': {'url': '', 'method': 'GET'},
                'type': 'Doc', 'timestamp': 1,
            }},
            {'params': {
                'requestId': 'r2', 'request': {'url': 'https://a.com', 'method': 'GET'},
                'type': 'Doc', 'timestamp': 2,
            }},
            {'params': {'requestId': 'r3'}},
            {'params': {
                'requestId': 'r4', 'request': {'url': 'https://b.com', 'method': 'POST'},
                'type': 'XHR', 'timestamp': 3,
            }},
        ]
        from pydoll_mcp_server.tools.inspection import _normalize_network_log

        events = [
            _normalize_network_log(log)
            for log in logs
            if isinstance(log, dict) and log.get('params', {}).get('request', {}).get('url')
        ]
        assert len(events) == 2
        assert events[0]['request_id'] == 'r2'
        assert events[1]['request_id'] == 'r4'

    def test_network_list_calls_get_network_logs(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            fake_tab = MagicMock()
            fake_tab.get_network_logs = AsyncMock(return_value=[
                {'params': {
                    'requestId': 'r1',
                    'request': {'url': 'https://a.com', 'method': 'GET'},
                    'type': 'Doc', 'timestamp': 1,
                }},
            ])
            fake_tab_info = MagicMock()
            fake_tab_info._pydoll_tab = fake_tab

            with patch(
                'pydoll_mcp_server.tools.inspection.get_registry',
            ) as mock_reg:
                mock_reg.return_value.get_tab.return_value = fake_tab_info

                from pydoll_mcp_server.tools.inspection import network_list

                async def _run():
                    return await network_list('test', 'tab-test')

                result = asyncio.run(_run())
                fake_tab.get_network_logs.assert_called_once()
                assert result['success'] is True
                assert len(result['events']) == 1
                assert result['events'][0]['request_id'] == 'r1'
