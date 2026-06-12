"""Tests for upload and download path policies."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.unit]


class _FakeDownload:
    def __init__(self, file_path: Path) -> None:
        self.file_path = str(file_path)

    async def wait_finished(self) -> None:
        self.file_path = self.file_path


class _DownloadContext:
    def __init__(self, download: _FakeDownload) -> None:
        self.download = download

    async def __aenter__(self) -> _FakeDownload:
        return self.download

    async def __aexit__(self, *args) -> None:
        return None


class _FakeDownloadTab:
    def __init__(self) -> None:
        self.keep_file_at = None
        self.timeout = None

    def expect_download(self, keep_file_at=None, timeout=None):
        self.keep_file_at = keep_file_at
        self.timeout = timeout
        file_path = Path(keep_file_at) / 'download.txt'
        return _DownloadContext(_FakeDownload(file_path))


def _reset_config(monkeypatch, tmp_path: Path) -> None:
    from pydoll_mcp_server.config import get_config

    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    monkeypatch.setenv('PYDOLL_MCP_RUNTIME_DIR', str(tmp_path))
    get_config.cache_clear()


@pytest.mark.asyncio
async def test_download_expect_uses_runtime_download_dir(monkeypatch, tmp_path: Path) -> None:
    from pydoll_mcp_server.tools import files as file_tools

    _reset_config(monkeypatch, tmp_path)
    tab = _FakeDownloadTab()

    class FakeRegistry:
        def get_tab(self, client_id: str, tab_id: str):
            return SimpleNamespace(
                client_id=client_id,
                tab_id=tab_id,
                _pydoll_tab=tab,
            )

    monkeypatch.setattr(file_tools, 'get_registry', lambda: FakeRegistry())

    result = await file_tools.download_expect('client-1', 'tab-1', timeout=3)

    expected_dir = tmp_path / 'downloads' / 'client-1'
    assert result['success'] is True
    assert Path(tab.keep_file_at).resolve(strict=False) == expected_dir.resolve(strict=False)
    assert Path(result['path']).resolve(strict=False).is_relative_to(
        expected_dir.resolve(strict=False)
    )


@pytest.mark.asyncio
async def test_upload_files_rejects_outside_allowlist(monkeypatch, tmp_path: Path) -> None:
    from pydoll_mcp_server.tools import files as file_tools

    _reset_config(monkeypatch, tmp_path)

    result = await file_tools.upload_files(
        'client-1',
        'tab-1',
        'el-1',
        [str(tmp_path.parent / 'outside.txt')],
    )

    assert result['error_code'] == 'PERMISSION_DENIED'


@pytest.mark.asyncio
async def test_upload_files_rejects_allowed_dir_traversal(monkeypatch, tmp_path: Path) -> None:
    from pydoll_mcp_server.tools import files as file_tools

    _reset_config(monkeypatch, tmp_path)
    traversal = tmp_path / 'artifacts' / 'subdir' / '..' / '..' / 'escape.txt'

    result = await file_tools.upload_files(
        'client-1',
        'tab-1',
        'el-1',
        [str(traversal)],
    )

    assert result['error_code'] == 'PERMISSION_DENIED'
