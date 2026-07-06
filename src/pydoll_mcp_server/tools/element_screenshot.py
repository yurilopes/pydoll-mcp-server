"""Element screenshot capture tool."""

from __future__ import annotations

import uuid
from contextlib import suppress
from pathlib import Path

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.security.paths import validate_artifact_path
from pydoll_mcp_server.tools.element_resolver import resolve_element


async def element_screenshot(
    client_id: str,
    tab_id: str,
    element_id: str,
    path: str = '',
    return_base64: bool = False,
) -> JsonObject:
    registry = get_registry()
    config = get_config()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    safe_path: str | None = None
    if path:
        safe_path = validate_artifact_path(path, config)
        if safe_path is None:
            return StructuredError(
                error_code=ErrorCode.PERMISSION_DENIED,
                message=f'Screenshot path not allowed: {path}',
                retryable=False,
                recovery_hint='Use a relative path (stored in artifacts dir) or a path in an allowed directory.',
            ).to_dict()

    if not safe_path and not return_base64:
        screenshots_dir = config.artifacts_dir / client_id
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        safe_path = str(screenshots_dir / f'screenshot_{uuid.uuid4().hex[:12]}.png')

    try:
        async with tab_operation_lock(tab_id):
            if safe_path:
                await element.take_screenshot(path=safe_path, as_base64=False)
                return _file_result(safe_path)
            result = await element.take_screenshot(as_base64=True)
            return {
                'success': True,
                'data': result if isinstance(result, str) else '',
                'return_base64': True,
                'evidence': {},
            }
    except Exception as exc:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Element screenshot failed: {exc}',
            retryable=True,
        ).to_dict()


def _file_result(path: str) -> JsonObject:
    file_size = 0
    with suppress(OSError):
        file_size = Path(path).stat().st_size
    return {
        'success': True,
        'path': path,
        'mime_type': 'image/png',
        'return_base64': False,
        'data': '',
        'size': file_size,
        'evidence': {},
    }
