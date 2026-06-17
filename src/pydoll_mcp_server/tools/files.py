"""File upload and download tools."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.pydoll_compat import set_input_files
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.config import get_config, get_timeout_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject
from pydoll_mcp_server.security.policy import PathAllowlist
from pydoll_mcp_server.tools.element_resolver import resolve_element


async def download_expect(
    client_id: str,
    tab_id: str,
    timeout: float | None = None,
) -> JsonObject:
    config = get_timeout_config()
    timeout = timeout or config.download
    timeout = min(timeout, config.max_timeout)
    server_config = get_config()
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab
    download_dir = server_config.downloads_dir / tab_info.client_id
    download_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with pydoll_tab.expect_download(
            keep_file_at=download_dir,
            timeout=timeout,
        ) as download:
            await download.wait_finished()
            file_path = download.file_path or str(download_dir)

        file_size = 0
        if file_path and os.path.isfile(file_path):
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
    expect_filename_visible: bool = False,
    verify_timeout: float | None = None,
) -> JsonObject:
    if expect_filename_visible or verify_timeout is not None:
        from pydoll_mcp_server.tools.upload_prep import upload_files_enhanced

        return await upload_files_enhanced(
            client_id=client_id,
            tab_id=tab_id,
            element_id=element_id,
            paths=paths,
            expect_filename_visible=expect_filename_visible,
            verify_timeout=verify_timeout,
        )

    registry = get_registry()

    allowlist = upload_allowlist()
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

    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    try:
        await set_input_files(element, paths)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Upload failed: {e}',
            retryable=True,
        ).to_dict()

    accepted: JsonArray = [file_info(Path(path)) for path in paths]
    state = await file_upload_state(client_id, tab_id, element_id)

    return {
        'success': True,
        'count': len(paths),
        'accepted': accepted,
        'state': state if state.get('success') else {},
    }


async def file_upload_state(client_id: str, tab_id: str, element_id: str) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
    try:
        result = await element.execute_script(
            """
            const files = [...(this.files || [])].map((file) => ({
                name: file.name, size: file.size, type: file.type || ''
            }));
            let nearby = '';
            let cursor = this.nextElementSibling;
            for (let i = 0; cursor && i < 3; i++, cursor = cursor.nextElementSibling) {
                nearby += ' ' + (cursor.innerText || cursor.textContent || '');
            }
            return {files, count: files.length, nearby_text: nearby.trim()};
            """,
            return_by_value=True,
        )
        state = extract_script_object(result)
        return {'success': True, 'element_id': element_id, **state}
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Upload state failed: {exc}', retryable=True).to_dict()


async def artifact_get_paths(client_id: str = 'anonymous') -> JsonObject:
    config = get_config()
    config.ensure_directories()
    client_artifacts = config.artifacts_dir / client_id
    client_downloads = config.downloads_dir / client_id
    client_tmp = config.tmp_dir / client_id
    for directory in (client_artifacts, client_downloads, client_tmp):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        'success': True,
        'artifacts_dir': str(config.artifacts_dir),
        'downloads_dir': str(config.downloads_dir),
        'tmp_dir': str(config.tmp_dir),
        'client_artifacts_dir': str(client_artifacts),
        'client_downloads_dir': str(client_downloads),
        'client_tmp_dir': str(client_tmp),
    }


async def artifact_import(
    client_id: str,
    source_path: str,
    filename: str = '',
    max_size_bytes: int = 50 * 1024 * 1024,
) -> JsonObject:
    config = get_config()
    allowlist = upload_allowlist()
    source = Path(source_path)
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, f'Import source not found: {exc}').to_dict()
    if not resolved.is_file():
        return StructuredError(ErrorCode.INVALID_INPUT, 'Import source must be a file.').to_dict()
    if not allowlist.is_allowed(str(resolved)):
        return StructuredError(
            ErrorCode.PERMISSION_DENIED,
            f'Import source not in allowed directories: {source_path}',
            recovery_hint='Use artifacts, downloads, tmp, or PYDOLL_MCP_IMPORT_ALLOWLIST.',
        ).to_dict()
    size = resolved.stat().st_size
    if size > max_size_bytes:
        return StructuredError(ErrorCode.INVALID_INPUT, f'File is too large: {size} bytes').to_dict()
    target_name = _safe_filename(filename or resolved.name)
    if not target_name:
        return StructuredError(ErrorCode.INVALID_INPUT, 'Imported filename is empty.').to_dict()
    target_dir = config.artifacts_dir / client_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / target_name).resolve(strict=False)
    try:
        target.relative_to(target_dir.resolve(strict=False))
    except ValueError:
        return StructuredError(ErrorCode.PERMISSION_DENIED, 'Imported filename escapes artifacts directory.').to_dict()
    shutil.copy2(resolved, target)
    return {'success': True, 'path': str(target), 'file': file_info(target)}


def upload_allowlist() -> PathAllowlist:
    config = get_config()
    allowed_dirs = [str(config.artifacts_dir), str(config.downloads_dir), str(config.tmp_dir)]
    for env_name in ('PYDOLL_MCP_UPLOAD_ALLOWLIST', 'PYDOLL_MCP_IMPORT_ALLOWLIST'):
        extra_allowed = os.environ.get(env_name, '')
        if extra_allowed:
            allowed_dirs.extend(extra_allowed.split(os.pathsep))
    return PathAllowlist(allowed_dirs)


def file_info(path: Path) -> JsonObject:
    return {'name': path.name, 'path': str(path), 'size': path.stat().st_size if path.exists() else 0}


def _safe_filename(filename: str) -> str:
    return Path(filename).name.replace('\x00', '')
