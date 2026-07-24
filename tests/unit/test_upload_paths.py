"""Tests for local upload source handling and native picker staging."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_native_picker_staging_preserves_filename_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pydoll_mcp_server.config import get_config
    from pydoll_mcp_server.tools import upload_paths

    source = tmp_path / 'resume original.pdf'
    source.write_bytes(b'%PDF-1.4 staged upload')
    staging_root = tmp_path / 'staging'
    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    monkeypatch.setenv('PYDOLL_MCP_UPLOAD_POLICY', 'local')
    monkeypatch.setenv('PYDOLL_MCP_UPLOAD_STAGING_DIR', str(staging_root))
    get_config.cache_clear()
    monkeypatch.setattr('pydoll_mcp_server.tools.upload_paths._is_windows', lambda: True)

    staged = await upload_paths.prepare_native_picker_upload(str(source))

    assert staged.staged is True
    assert staged.picker_path.name == source.name
    assert staged.picker_path.exists()
    assert staged.picker_path.read_bytes() == source.read_bytes()
    staging_dir = staged.staging_dir
    assert staging_dir is not None

    await staged.cleanup()

    assert not staging_dir.exists()
