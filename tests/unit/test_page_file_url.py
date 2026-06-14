"""Tests for the complete file URL navigation block."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.unit]


def test_normalize_navigation_url_rejects_file_url() -> None:
    from pydoll_mcp_server.tools.page import _normalize_navigation_url

    url, error = _normalize_navigation_url('file:///C:/allowed/local.html')

    assert url is None
    assert error is not None
    assert error.error_code.value == 'INVALID_INPUT'
    assert 'Only http:// and https://' in error.message


def test_normalize_navigation_url_accepts_http_and_https() -> None:
    from pydoll_mcp_server.tools.page import _normalize_navigation_url

    for url in ('http://127.0.0.1:8000/local.html', 'https://example.test/page'):
        normalized, error = _normalize_navigation_url(url)
        assert error is None
        assert normalized == url


@pytest.mark.asyncio
async def test_page_goto_rejects_file_before_resolving_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.tools import page as page_tools

    class FakeRegistry:
        def get_tab(self, client_id: str, tab_id: str) -> SimpleNamespace:
            raise AssertionError('Registry must not be accessed for blocked file URLs')

    monkeypatch.setattr(page_tools, 'get_registry', FakeRegistry)

    result = await page_tools.page_goto('client-1', 'tab-1', 'file:///C:/secret.txt')

    assert result['error_code'] == 'INVALID_INPUT'
    assert result['retryable'] is False
