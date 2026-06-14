"""Navigation tools: goto, reload, back, forward, wait."""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.pydoll_compat import get_tab_title, get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_value
from pydoll_mcp_server.config import get_config, get_timeout_config
from pydoll_mcp_server.errors import ErrorCode, ResourceState, StructuredError
from pydoll_mcp_server.logging import OperationLog, get_logger
from pydoll_mcp_server.security.policy import PathAllowlist

URL_PATTERN = re.compile(r'^https?://')
FILE_URL_PATTERN = re.compile(r'^file://', re.IGNORECASE)


def _file_url_to_path(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != 'file':
        return None
    if parsed.netloc and parsed.netloc.lower() not in ('localhost',):
        return None
    try:
        return Path(url2pathname(unquote(parsed.path))).resolve(strict=False)
    except Exception:
        return None


def _file_navigation_allowlist() -> PathAllowlist:
    config = get_config()
    allowed_dirs = [
        str(Path.cwd()),
        str(config.artifacts_dir),
        str(config.downloads_dir),
        str(config.tmp_dir),
    ]
    extra_allowed = os.environ.get('PYDOLL_MCP_FILE_ALLOWLIST', '')
    if extra_allowed:
        allowed_dirs.extend(extra_allowed.split(os.pathsep))
    return PathAllowlist(allowed_dirs)


def _normalize_navigation_url(url: str) -> tuple[str | None, StructuredError | None]:
    if URL_PATTERN.match(url):
        return url, None

    if not FILE_URL_PATTERN.match(url):
        return None, StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message=(
                f'Invalid URL: {url}. Must start with http://, https://, '
                'or file:// for allowed local files'
            ),
            retryable=False,
        )

    path = _file_url_to_path(url)
    if path is None:
        return None, StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message=f'Invalid file URL: {url}. Only local file URLs are allowed.',
            retryable=False,
        )
    if not path.is_file():
        return None, StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message=f'Local file URL does not point to an existing file: {url}',
            retryable=False,
        )
    if not _file_navigation_allowlist().is_allowed(str(path)):
        return None, StructuredError(
            error_code=ErrorCode.PERMISSION_DENIED,
            message=f'Local file path not in allowed directories: {path}',
            retryable=False,
            recovery_hint=(
                'Place the file under the server working directory or runtime '
                'directories, or configure PYDOLL_MCP_FILE_ALLOWLIST.'
            ),
        )
    return path.as_uri(), None


async def page_goto(
    client_id: str,
    tab_id: str,
    url: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    config = get_timeout_config()
    timeout = timeout or config.goto
    timeout = min(timeout, config.max_timeout)
    registry = get_registry()
    logger = get_logger()

    normalized_url, validation_error = _normalize_navigation_url(url)
    if validation_error:
        return validation_error.to_dict()
    assert normalized_url is not None

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    start = time.time()
    try:
        async with tab_operation_lock(tab_id):
            pydoll_tab = tab_info._pydoll_tab
            await asyncio.wait_for(
                pydoll_tab.go_to(normalized_url, timeout=timeout),
                timeout=timeout + 5,
            )
            tab_info.mark_navigated()
            final_url = await get_tab_url(pydoll_tab) or normalized_url
            tab_info.url = final_url
            tab_info.title = await get_tab_title(pydoll_tab)

        duration_ms = (time.time() - start) * 1000
        logger.log_operation(OperationLog(
            client_id=client_id, tab_id=tab_id, tool='page_goto',
            status='success', duration_ms=duration_ms,
        ))
        return {
            'success': True,
            'url': final_url,
            'load_state': 'complete',
            'timing_ms': round(duration_ms, 1),
        }
    except asyncio.TimeoutError:
        duration_ms = (time.time() - start) * 1000
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message=f'Navigation to {normalized_url} timed out after {timeout}s',
            retryable=True,
            resource_state=ResourceState.DEGRADED,
            details={
                'url': normalized_url,
                'timeout': timeout,
                'timing_ms': round(duration_ms, 1),
            },
            recovery_hint='The page may have loaded partially. Check tab status.',
        ).to_dict()
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.NAVIGATION_ERROR,
            message=f'Navigation error: {e}',
            retryable=True,
            details={'url': normalized_url, 'error': str(e)},
        ).to_dict()


async def page_reload(
    client_id: str,
    tab_id: str,
    ignore_cache: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    config = get_timeout_config()
    timeout = timeout or config.reload
    timeout = min(timeout, config.max_timeout)
    registry = get_registry()
    get_logger()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    start = time.time()
    try:
        async with tab_operation_lock(tab_id):
            pydoll_tab = tab_info._pydoll_tab
            await asyncio.wait_for(
                pydoll_tab.refresh(ignore_cache=ignore_cache),
                timeout=timeout + 5,
            )
            tab_info.mark_navigated()
            tab_info.url = await get_tab_url(pydoll_tab)
            tab_info.title = await get_tab_title(pydoll_tab)
        duration_ms = (time.time() - start) * 1000
        return {
            'success': True,
            'url': tab_info.url,
            'load_state': 'complete',
            'timing_ms': round(duration_ms, 1),
        }
    except asyncio.TimeoutError:
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message=f'Page reload timed out after {timeout}s',
            retryable=True,
            resource_state=ResourceState.DEGRADED,
        ).to_dict()
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.NAVIGATION_ERROR,
            message=f'Reload error: {e}',
            retryable=True,
        ).to_dict()


async def page_back(
    client_id: str,
    tab_id: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    config = get_timeout_config()
    timeout = timeout or config.back_forward
    timeout = min(timeout, config.max_timeout)
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    try:
        async with tab_operation_lock(tab_id):
            pydoll_tab = tab_info._pydoll_tab
            result = await asyncio.wait_for(
                pydoll_tab.execute_script('history.back(); return location.href;',
                                            return_by_value=True),
                timeout=timeout,
            )
            url = extract_script_value(result) or ''
            tab_info.mark_navigated()
        return {
            'success': True,
            'url': url,
        }
    except asyncio.TimeoutError:
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message=f'Back navigation timed out after {timeout}s',
            retryable=True,
        ).to_dict()
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.NAVIGATION_ERROR,
            message=f'Back navigation error: {e}',
            retryable=False,
        ).to_dict()


async def page_forward(
    client_id: str,
    tab_id: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    config = get_timeout_config()
    timeout = timeout or config.back_forward
    timeout = min(timeout, config.max_timeout)
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    try:
        async with tab_operation_lock(tab_id):
            pydoll_tab = tab_info._pydoll_tab
            result = await asyncio.wait_for(
                pydoll_tab.execute_script('history.forward(); return location.href;',
                                            return_by_value=True),
                timeout=timeout,
            )
            url = extract_script_value(result) or ''
            tab_info.mark_navigated()
        return {
            'success': True,
            'url': url,
        }
    except asyncio.TimeoutError:
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message=f'Forward navigation timed out after {timeout}s',
            retryable=True,
        ).to_dict()
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.NAVIGATION_ERROR,
            message=f'Forward navigation error: {e}',
            retryable=False,
        ).to_dict()


async def page_wait(
    client_id: str,
    tab_id: str,
    state: str = 'load',
    selector: str = '',
    text: str = '',
    timeout: float | None = None,
) -> dict[str, Any]:
    config = get_timeout_config()
    timeout = timeout or config.wait_selector
    timeout = min(timeout, config.max_timeout)
    registry = get_registry()
    get_logger()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info._pydoll_tab
    start = time.time()

    try:
        if selector:
            element = await asyncio.wait_for(
                pydoll_tab.query(selector, timeout=timeout, find_all=False, raise_exc=False),
                timeout=timeout + 5,
            )
            if element is None:
                return StructuredError(
                    error_code=ErrorCode.TIMEOUT,
                    message=f'Selector "{selector}" not found within {timeout}s',
                    retryable=True,
                ).to_dict()
            duration_ms = (time.time() - start) * 1000
            return {
                'success': True,
                'matched': True,
                'selector': selector,
                'timing_ms': round(duration_ms, 1),
            }
        elif text:
            deadline = time.time() + timeout
            while time.time() < deadline:
                page_text = await asyncio.wait_for(
                    pydoll_tab.execute_script('return document.body.innerText || "";',
                                                 return_by_value=True),
                    timeout=5.0,
                )
                page_str = str(page_text) if page_text else ''
                if text in page_str:
                    duration_ms = (time.time() - start) * 1000
                    return {
                        'success': True,
                        'matched': True,
                        'text': text,
                        'timing_ms': round(duration_ms, 1),
                    }
                await asyncio.sleep(0.5)
            return StructuredError(
                error_code=ErrorCode.TIMEOUT,
                message=f'Text "{text}" not found within {timeout}s',
                retryable=True,
            ).to_dict()
        else:
            await asyncio.sleep(1.0)
            duration_ms = (time.time() - start) * 1000
            return {
                'success': True,
                'state': state,
                'timing_ms': round(duration_ms, 1),
            }
    except asyncio.TimeoutError:
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message=f'Wait timed out after {timeout}s',
            retryable=True,
        ).to_dict()
