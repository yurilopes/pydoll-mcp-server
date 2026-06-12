"""File upload and download tools."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.config import get_config, get_timeout_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.security.policy import PathAllowlist


async def download_expect(
    client_id: str,
    tab_id: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    config = get_timeout_config()
    timeout = timeout or config.download
    timeout = min(timeout, config.max_timeout)
    server_config = get_config()
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info._pydoll_tab
    download_dir = server_config.downloads_dir / tab_info.client_id
    download_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with pydoll_tab.expect_download(
            keep_file_at=download_dir,
            timeout=timeout,
        ) as download:
            await download.wait_finished()
            file_path = download.file_path if hasattr(download, 'file_path') else str(download_dir)

        file_size = 0
        if os.path.isfile(file_path):
            file_size = os.path.getsize(file_path)

        return {
            'success': True,
            'path': file_path,
            'size': file_size,
        }
    except asyncio.TimeoutError:
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message=f'Download timed out after {timeout}s',
            retryable=True,
        ).to_dict()
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Download failed: {e}',
            retryable=True,
        ).to_dict()


async def upload_files(
    client_id: str,
    tab_id: str,
    element_id: str,
    paths: list[str],
) -> dict[str, Any]:
    from pydoll_mcp_server.dom.element_cache import get_element_cache

    server_config = get_config()
    registry = get_registry()

    allowed_dirs = [
        str(server_config.artifacts_dir),
        str(server_config.downloads_dir),
        str(server_config.tmp_dir),
    ]
    extra_allowed = os.environ.get('PYDOLL_MCP_UPLOAD_ALLOWLIST', '')
    if extra_allowed:
        allowed_dirs.extend(extra_allowed.split(os.pathsep))

    allowlist = PathAllowlist(allowed_dirs)
    for p in paths:
        if not allowlist.is_allowed(p):
            return StructuredError(
                error_code=ErrorCode.PERMISSION_DENIED,
                message=f'Upload path not in allowed directories: {p}',
                retryable=False,
                recovery_hint='Place files in the artifacts or downloads directory.',
            ).to_dict()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    cache = get_element_cache()
    entry = cache.get_valid(element_id, tab_info.tab_id, tab_info.document_generation)
    if not entry or not entry._pydoll_element:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    element = entry._pydoll_element

    try:
        await element.set_input_files(paths)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Upload failed: {e}',
            retryable=True,
        ).to_dict()

    return {
        'success': True,
        'count': len(paths),
    }
