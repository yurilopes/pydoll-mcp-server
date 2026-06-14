"""Tests for local file URL navigation policy."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.unit]


def _clear_config_cache() -> None:
    from pydoll_mcp_server.config import get_config

    get_config.cache_clear()


def test_normalize_navigation_url_accepts_file_under_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pydoll_mcp_server.tools.page import _normalize_navigation_url

    monkeypatch.setenv('PYDOLL_MCP_ALLOW_NO_AUTH', 'true')
    monkeypatch.chdir(tmp_path)
    _clear_config_cache()

    page = tmp_path / 'local.html'
    page.write_text('<html><body>ok</body></html>', encoding='utf-8')

    url, error = _normalize_navigation_url(page.as_uri())

    assert error is None
    assert url == page.resolve().as_uri()


def test_normalize_navigation_url_rejects_file_outside_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pydoll_mcp_server.tools.page import _normalize_navigation_url

    cwd = tmp_path / 'cwd'
    outside = tmp_path / 'outside'
    cwd.mkdir()
    outside.mkdir()
    page = outside / 'local.html'
    page.write_text('<html><body>outside</body></html>', encoding='utf-8')

    monkeypatch.setenv('PYDOLL_MCP_ALLOW_NO_AUTH', 'true')
    monkeypatch.chdir(cwd)
    _clear_config_cache()

    url, error = _normalize_navigation_url(page.as_uri())

    assert url is None
    assert error is not None
    assert error.error_code.value == 'PERMISSION_DENIED'


def test_normalize_navigation_url_accepts_file_allowlist_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pydoll_mcp_server.tools.page import _normalize_navigation_url

    cwd = tmp_path / 'cwd'
    allowed = tmp_path / 'allowed'
    cwd.mkdir()
    allowed.mkdir()
    page = allowed / 'local.html'
    page.write_text('<html><body>allowed</body></html>', encoding='utf-8')

    monkeypatch.setenv('PYDOLL_MCP_ALLOW_NO_AUTH', 'true')
    monkeypatch.setenv('PYDOLL_MCP_FILE_ALLOWLIST', str(allowed))
    monkeypatch.chdir(cwd)
    _clear_config_cache()

    url, error = _normalize_navigation_url(page.as_uri())

    assert error is None
    assert url == page.resolve().as_uri()


@pytest.mark.asyncio
async def test_page_goto_passes_normalized_file_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pydoll_mcp_server.tools import page as page_tools

    monkeypatch.setenv('PYDOLL_MCP_ALLOW_NO_AUTH', 'true')
    monkeypatch.chdir(tmp_path)
    _clear_config_cache()

    local_page = tmp_path / 'page.html'
    local_page.write_text('<html><title>Local</title><body>ok</body></html>', encoding='utf-8')

    class FakeTab:
        def __init__(self) -> None:
            self.url = ''
            self.calls: list[tuple[str, float | None]] = []

        @property
        async def current_url(self) -> str:
            return self.url

        @property
        async def title(self) -> str:
            return 'Local'

        async def go_to(self, url: str, timeout: float | None = None) -> None:
            self.calls.append((url, timeout))
            self.url = url

    class FakeRegistry:
        def __init__(self, tab: FakeTab) -> None:
            self.tab = tab

        def get_tab(self, client_id: str, tab_id: str):
            return SimpleNamespace(
                client_id=client_id,
                tab_id=tab_id,
                browser_id='browser-1',
                document_generation=0,
                _pydoll_tab=self.tab,
                mark_navigated=lambda: None,
            )

    tab = FakeTab()
    monkeypatch.setattr(page_tools, 'get_registry', lambda: FakeRegistry(tab))

    result = await page_tools.page_goto('client-1', 'tab-1', local_page.as_uri())

    assert result['success'] is True
    assert tab.calls == [(local_page.resolve().as_uri(), 30.0)]
