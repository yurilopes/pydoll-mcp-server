"""Two-phase downloads and safe PDF generation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.watches import get_watch_manager, safe_file_info
from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.security.paths import validate_artifact_path


async def download_prepare(client_id: str, tab_id: str, timeout: float = 60.0) -> dict[str, Any]:
    try:
        tab = get_registry().get_tab(client_id, tab_id)._pydoll_tab
        target = get_config().downloads_dir / client_id
        target.mkdir(parents=True, exist_ok=True)

        async def run() -> Any:
            async with tab.expect_download(keep_file_at=target, timeout=min(timeout, 120.0)) as download:
                await download.wait_finished()
                return download
        watch = get_watch_manager().create(client_id, tab_id, 'download')
        watch.task = asyncio.create_task(run())
        return {'success': True, 'watch_id': watch.watch_id, 'timeout': timeout}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Download prepare failed: {exc}').to_dict()


async def download_wait(client_id: str, watch_id: str, timeout: float = 60.0) -> dict[str, Any]:
    try:
        watch = get_watch_manager().get(client_id, watch_id, 'download')
        if watch.result:
            return {'success': True, 'watch_id': watch_id, 'download': watch.result}
        if watch.task is None:
            raise StructuredError(ErrorCode.INTERNAL_ERROR, 'Download watch has no task')
        download = await asyncio.wait_for(asyncio.shield(watch.task), min(timeout, 120.0))
        path = str(getattr(download, 'file_path', ''))
        result = safe_file_info(path)
        get_watch_manager().finish(watch, result)
        return {'success': True, 'watch_id': watch_id, 'download': result}
    except StructuredError as exc:
        return exc.to_dict()
    except TimeoutError:
        return StructuredError(ErrorCode.TIMEOUT, 'Download wait timed out', retryable=True).to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Download failed: {exc}', retryable=True).to_dict()


async def download_list(client_id: str, tab_id: str) -> dict[str, Any]:
    try:
        get_registry().get_tab(client_id, tab_id)
        items = get_watch_manager().downloads(client_id, tab_id)
        return {'success': True, 'downloads': items, 'count': len(items)}
    except StructuredError as exc:
        return exc.to_dict()


async def download_get_info(client_id: str, tab_id: str, name: str) -> dict[str, Any]:
    result = await download_list(client_id, tab_id)
    for item in result.get('downloads', []):
        if item.get('name') == Path(name).name:
            return {'success': True, 'download': item}
    return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, f'Download not found: {Path(name).name}').to_dict()


async def page_print_pdf(
    client_id: str, tab_id: str, path: str = '', as_base64: bool = True,
    landscape: bool = False, print_background: bool = True, scale: float = 1.0,
) -> dict[str, Any]:
    if not 0.1 <= scale <= 2.0:
        return StructuredError(ErrorCode.INVALID_INPUT, 'scale must be between 0.1 and 2.0').to_dict()
    safe_path = validate_artifact_path(path, get_config()) if path else None
    if path and safe_path is None:
        return StructuredError(ErrorCode.PERMISSION_DENIED, f'PDF path not allowed: {path}').to_dict()
    try:
        tab = get_registry().get_tab(client_id, tab_id)._pydoll_tab
        data = await tab.print_to_pdf(
            path=safe_path, landscape=landscape, print_background=print_background,
            scale=scale, as_base64=as_base64 or not safe_path,
        )
        return {'success': True, 'path': safe_path or '', 'data': data or '', 'as_base64': as_base64 or not safe_path}
    except StructuredError as exc:
        return exc.to_dict()
    except Exception as exc:
        return StructuredError(ErrorCode.UNSUPPORTED, f'PDF generation unavailable: {exc}').to_dict()

