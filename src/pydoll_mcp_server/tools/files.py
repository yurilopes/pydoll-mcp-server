"""File upload and download tools."""

from __future__ import annotations

import asyncio
import mimetypes
import os
import shutil
import uuid
from pathlib import Path

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.pydoll_compat import set_input_files
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_object
from pydoll_mcp_server.config import get_config, get_timeout_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_int, get_string
from pydoll_mcp_server.security.upload_policy import validate_upload_path
from pydoll_mcp_server.tools.element_resolver import resolve_element
from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens

_UPLOAD_IDS: dict[tuple[str, str, str], str] = {}
_UPLOAD_STATES: dict[tuple[str, str, str], str] = {}


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
    replace_existing: bool = False,
    clear_existing: bool = False,
) -> JsonObject:
    if not paths and not clear_existing:
        return StructuredError(ErrorCode.INVALID_INPUT, 'At least one upload path is required.').to_dict()
    if expect_filename_visible or verify_timeout is not None:
        from pydoll_mcp_server.tools.upload_prep import upload_files_enhanced

        return await upload_files_enhanced(
            client_id=client_id,
            tab_id=tab_id,
            element_id=element_id,
            paths=paths,
            expect_filename_visible=expect_filename_visible,
            verify_timeout=verify_timeout,
            replace_existing=replace_existing,
        )

    registry = get_registry()

    for p in paths:
        validation_error = validate_upload_path(p)
        if validation_error is not None:
            return validation_error

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

    current_state = await file_upload_state(client_id, tab_id, element_id)
    current_status = str(current_state.get('state', 'absent'))
    if (
        current_status in {'accepted', 'accepted_with_verification_warning', 'processing', 'rendered'}
        and not replace_existing
        and not clear_existing
    ):
        return StructuredError(
            ErrorCode.UPLOAD_STATE_CONFLICT,
            'The upload control already contains a file. Set replace_existing=true to replace it.',
            details={'state': current_state},
            retryable=False,
        ).to_dict()

    try:
        invalidate_review_tokens(client_id, tab_id)
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
        'contract_version': 2,
        'operation_id': f'upload_{uuid.uuid4().hex[:16]}',
        'success': True,
        'status': str(state.get('state', 'unknown')),
        'count': len(paths),
        'accepted': accepted,
        'replace_existing': replace_existing,
        'clear_existing': clear_existing,
        'state': state if state.get('success') else {},
    }


async def file_upload_state(client_id: str, tab_id: str, element_id: str = '', upload_id: str = '') -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    if upload_id and not element_id:
        for key, candidate in _UPLOAD_IDS.items():
            if key[0] == client_id and key[1] == tab_id and candidate == upload_id:
                element_id = key[2]
                break
    element = await resolve_element(tab_info, element_id)
    if element is None:
        stale = StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
        stale.update(
            {
                'contract_version': 2,
                'operation_id': f'upload_state_{uuid.uuid4().hex[:16]}',
                'success': False,
                'status': 'stale',
                'state': 'stale',
                'upload_id': _UPLOAD_IDS.get((client_id, tab_id, element_id), upload_id),
                'element_id': element_id,
                'recovery': 'Re-observe the form and use the current upload control element_id.',
            }
        )
        return stale
    try:
        result = await element.execute_script(
            """
            const files = [...(this.files || [])].map((file) => ({
                name: file.name, size: file.size, type: file.type || ''
            }));
            const root = this.getRootNode ? this.getRootNode() : document;
            const textOf = (node) => (node?.innerText || node?.textContent || '').trim();
            const visible = (node) => {
                if (!node || typeof node.getBoundingClientRect !== 'function') return false;
                const rect = node.getBoundingClientRect();
                const style = getComputedStyle(node);
                return rect.width > 0 && rect.height > 0 && style.display !== 'none'
                    && style.visibility !== 'hidden';
            };
            const isStatusLike = (node) => {
                if (!node) return false;
                const descriptor = [
                    node.id || '',
                    node.className || '',
                    node.getAttribute?.('role') || '',
                    node.getAttribute?.('aria-live') || '',
                    node.getAttribute?.('data-testid') || ''
                ].join(' ').toLowerCase();
                return node.getAttribute?.('role') === 'status'
                    || Boolean(node.getAttribute?.('aria-live'))
                    || /file|upload|resume|curriculum|attachment|document|selected/.test(descriptor);
            };
            const isEmptyFilePlaceholder = (text) => {
                const normalized = text.trim().toLowerCase();
                const exact = new Set([
                    'no file selected', 'no files selected', 'no file chosen',
                    'choose file', 'browse...'
                ]);
                return exact.has(normalized)
                    || normalized.startsWith('click to upload')
                    || normalized.startsWith('upload a ')
                    || normalized.startsWith('upload your ')
                    || normalized.startsWith('select a file')
                    || normalized.startsWith('select your file')
                    || normalized.startsWith('drag ')
                    || normalized.startsWith('attach a file')
                    || normalized.startsWith('attach your file');
            };
            const addStatusText = (node) => {
                const text = textOf(node);
                if (text && !isEmptyFilePlaceholder(text)) nearbyParts.push(text);
            };
            let labelNode = this.closest ? this.closest('label') : null;
            if (!labelNode && this.id && root.querySelector)
                labelNode = root.querySelector('label[for="' + CSS.escape(this.id) + '"]');
            const context = labelNode || (this.closest ? this.closest('fieldset, .field, .form-group') : null);
            const labels = labelNode ? textOf(labelNode) : (context ? textOf(context).slice(0, 200) : '');
            const nearbyParts = [];
            if (context) {
                const statusSelector = '[role="status"],[aria-live],.file-name,' +
                    '[class*="file"],[class*="upload"]';
                for (const node of context.querySelectorAll?.(statusSelector) || [])
                    if (visible(node) && isStatusLike(node)) addStatusText(node);
            }
            let cursor = this.nextElementSibling;
            for (let i = 0; cursor && i < 3; i++, cursor = cursor.nextElementSibling)
                if (visible(cursor) && isStatusLike(cursor)) addStatusText(cursor);
            const nearby = [...new Set(nearbyParts.filter(Boolean))].join(' ').slice(0, 1000);
            const status_text = nearby;
            return {files, count: files.length, nearby_text: nearby, status_text, label: labels};
            """,
            return_by_value=True,
        )
        state = extract_normalized_object(result, 'file_upload_state')
        key = (client_id, tab_id, element_id)
        stable_upload_id = _UPLOAD_IDS.setdefault(key, f'upload_{uuid.uuid4().hex[:16]}')
        files = state.get('files') if isinstance(state.get('files'), list) else []
        file_values: JsonArray = files if isinstance(files, list) else []
        nearby = get_string(state, 'nearby_text', '')
        status_text = get_string(state, 'status_text', nearby)
        folded_status = status_text.casefold()
        key = (client_id, tab_id, element_id)
        previous_state = _UPLOAD_STATES.get(key, '')
        if any(marker in folded_status for marker in ('reject', 'invalid', 'failed', 'error')):
            semantic_state = 'rejected'
        elif any(marker in folded_status for marker in ('processing', 'uploading', 'scanning')):
            semantic_state = 'processing'
        elif files:
            semantic_state = 'accepted' if nearby else 'accepted_with_verification_warning'
        elif nearby:
            semantic_state = 'rendered'
        elif previous_state in {'accepted', 'accepted_with_verification_warning', 'processing', 'rendered'}:
            semantic_state = 'cleared'
        else:
            semantic_state = 'absent'
        _UPLOAD_STATES[key] = semantic_state
        records: JsonArray = []
        for item in file_values:
            if isinstance(item, dict):
                name = str(item.get('name', ''))
                records.append(
                    {
                        'name': name,
                        'size': get_int(item, 'size', 0),
                        'mime': str(item.get('type', '') or mimetypes.guess_type(name)[0] or ''),
                    }
                )
        return {
            'contract_version': 2,
            'operation_id': f'upload_state_{int(asyncio.get_running_loop().time() * 1000)}',
            'success': True,
            'status': semantic_state,
            'state': semantic_state,
            'upload_id': stable_upload_id,
            'element_id': element_id,
            'label': str(state.get('label', '')),
            'files': records,
            'count': len(records),
            'nearby_text': nearby,
            'native_input_state': 'present' if files else 'empty',
            'rendered_state': 'present' if nearby else 'absent',
            'evidence': {'visible_text': nearby, 'filename_count': len(records)},
            'warnings': [] if files else ['The browser input has no accepted file.'],
            'recovery': (
                'Use replace_existing=true only after confirming the current state.'
                if files
                else 'Retry only after resolving the upload control again.'
            ),
        }
    except (PydollException, InvalidScriptResponseError, KeyError, TypeError, ValueError) as exc:
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
    source = Path(source_path)
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, f'Import source not found: {exc}').to_dict()
    if not resolved.is_file():
        return StructuredError(ErrorCode.INVALID_INPUT, 'Import source must be a file.').to_dict()
    validation_error = validate_upload_path(str(resolved), max_size_bytes)
    if validation_error is not None:
        return validation_error
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


def file_info(path: Path) -> JsonObject:
    return {'name': path.name, 'path': str(path), 'size': path.stat().st_size if path.exists() else 0}


def _safe_filename(filename: str) -> str:
    return Path(filename).name.replace('\x00', '')
