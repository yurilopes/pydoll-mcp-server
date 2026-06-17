"""Upload preparation and enhanced upload tools."""

from __future__ import annotations

import shutil
from pathlib import Path

from pydoll.browser.tab import Tab
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.pydoll_compat import set_input_files
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.config import ServerConfig, get_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_object, get_string
from pydoll_mcp_server.security.policy import PathAllowlist
from pydoll_mcp_server.tools.element_resolver import resolve_element
from pydoll_mcp_server.tools.files import file_info, upload_allowlist


async def artifact_prepare_upload(
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
    except OSError:
        return _denied_response(source_path, allowlist, config, client_id)

    if not resolved.is_file():
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'Upload source must be a file.',
        ).to_dict()

    if not allowlist.is_allowed(str(resolved)):
        return _denied_response(str(resolved), allowlist, config, client_id)

    size = resolved.stat().st_size
    if size > max_size_bytes:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            f'File is too large: {size} bytes (max {max_size_bytes}).',
        ).to_dict()

    target_name = _safe_upload_filename(filename or resolved.name)
    if not target_name:
        return StructuredError(ErrorCode.INVALID_INPUT, 'Upload filename is empty.').to_dict()

    target_dir = config.artifacts_dir / client_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / target_name

    try:
        target.resolve(strict=False).relative_to(target_dir.resolve(strict=False))
    except ValueError:
        return StructuredError(
            ErrorCode.PERMISSION_DENIED,
            'Upload filename escapes artifacts directory.',
        ).to_dict()

    shutil.copy2(resolved, target)

    file_data = file_info(target)
    return {
        'success': True,
        'path': str(target),
        'file': file_data,
        'client_artifacts_dir': str(target_dir),
        'warnings': [],
        'evidence': {'source': str(resolved), 'target': str(target), 'size': size},
    }


async def upload_files_enhanced(
    client_id: str,
    tab_id: str,
    element_id: str,
    paths: list[str],
    expect_filename_visible: bool = False,
    verify_timeout: float | None = None,
) -> JsonObject:
    registry = get_registry()

    allowlist = upload_allowlist()
    for p in paths:
        if not allowlist.is_allowed(p):
            return StructuredError(
                ErrorCode.PERMISSION_DENIED,
                message=f'Upload path not in allowed directories: {p}',
                retryable=False,
                recovery_hint='Use artifact_prepare_upload to copy the file into artifacts first.',
            ).to_dict()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    try:
        await set_input_files(element, paths)
    except (PydollException, ValueError, OSError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            message=f'Upload failed: {exc}',
            retryable=True,
        ).to_dict()

    accepted: JsonArray = [file_info(Path(p)) for p in paths]
    native_state = await _get_upload_state_native(tab_info, element_id)
    filename_visible_map: JsonObject = {}
    visible_in_page = False
    nearby_text = ''
    diagnostics: list[str] = []

    if expect_filename_visible:
        verify_limit = verify_timeout or 3.0
        filename_visible_map, visible_in_page, nearby_text = await _wait_filename_visible(
            tab_info.pydoll_tab,
            paths,
            element_id,
            verify_limit,
        )

    native_files_count = 0
    if native_state.get('success'):
        native_files_count = int(str(native_state.get('count', 0)))

    if native_files_count == 0 and visible_in_page:
        diagnostics.append(
            'Native input state shows no files, but filename is visible in the page. '
            'The site likely moved upload state into custom UI.'
        )

    return {
        'success': True,
        'count': len(paths),
        'accepted': accepted,
        'accepted_by_input': native_files_count > 0,
        'visible_in_page': visible_in_page,
        'filename_visible': filename_visible_map,
        'nearby_text': nearby_text,
        'diagnostics': list(diagnostics),
    }


def _denied_response(source_path: str, allowlist: PathAllowlist, config: ServerConfig, client_id: str) -> JsonObject:
    allowed_dirs: list[str] = [str(config.artifacts_dir), str(config.downloads_dir), str(config.tmp_dir)]
    client_artifacts = str(config.artifacts_dir / client_id)
    result: JsonObject = {
        'allowed_directories': list(allowed_dirs),
        'client_artifacts_dir': client_artifacts,
        'recommended_mcp_operation': (
            'Use artifact_get_paths, then provide a file already inside an '
            'allowed directory or configure an explicit import allowlist.'
        ),
    }
    return StructuredError(
        ErrorCode.PERMISSION_DENIED,
        f'Source path is not in an allowed import directory: {source_path}',
        details=result,
        retryable=False,
    ).to_dict()


async def _get_upload_state_native(tab_info: TabInfo, element_id: str) -> JsonObject:
    try:
        element = await resolve_element(tab_info, element_id)
        if element is None:
            return {'success': False, 'count': 0}
        result = await element.execute_script(
            'const files = [...(this.files || [])]; return {count: files.length};',
            return_by_value=True,
        )
        data = extract_script_object(result)
        return {'success': True, 'count': data.get('count', 0)}
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        return {'success': False, 'count': 0}


async def _wait_filename_visible(
    pydoll_tab: Tab, paths: list[str], element_id: str, timeout: float
) -> tuple[JsonObject, bool, str]:
    import asyncio
    import time

    deadline = time.monotonic() + timeout
    name_map: JsonObject = {}
    visible = False
    nearby = ''

    expected_names = [Path(p).name.lower() for p in paths]

    while time.monotonic() < deadline:
        try:
            script = """
            const names = new Set(arguments[0]);
            const result = { visible: {}, nearby: '' };
            const fileInput = document.activeElement || document.querySelector('input[type="file"]');
            const els = document.querySelectorAll('.upload-custom, .file-name, [class*="file"], [class*="upload"]');
            for (const el of els) {
                const t = (el.innerText || el.textContent || '').toLowerCase();
                for (const name of names) {
                    if (t.includes(name)) {
                        result.visible[name] = true;
                    }
                }
            }
            if (fileInput) {
                let cursor = fileInput.nextElementSibling;
                for (let i = 0; cursor && i < 3; i++, cursor = cursor.nextElementSibling) {
                    result.nearby += ' ' + (cursor.innerText || cursor.textContent || '');
                }
            }
            result.any = Object.keys(result.visible).length > 0;
            return result;
            """
            import json

            result = await pydoll_tab.execute_script(
                f'const names={json.dumps(expected_names)};({script})(names)',
                return_by_value=True,
            )
            data = extract_script_object(result)
            if data.get('any'):
                name_map = get_object(data, 'visible', {})
                visible = True
            nearby = get_string(data, 'nearby', '')
            if visible:
                break
        except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
            pass
        await asyncio.sleep(0.2)

    return name_map, visible, nearby


def _safe_upload_filename(filename: str) -> str:
    return Path(filename).name.replace('\x00', '')
