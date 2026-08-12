"""Controlled export of registered runtime artifacts."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from pydoll_mcp_server.browser.artifact_registry import get_artifact
from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.security.paths import validate_artifact_path


async def artifact_export(
    client_id: str,
    artifact_id: str,
    destination: str = '',
) -> JsonObject:
    record = get_artifact(client_id, artifact_id)
    if record is None:
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, f'Artifact {artifact_id} was not found.').to_dict()
    config = get_config()
    target_name = destination or f'{client_id}/exports/{Path(record.relative_path).name}'
    safe_target = validate_artifact_path(target_name, config)
    if safe_target is None:
        return StructuredError(
            ErrorCode.PERMISSION_DENIED,
            'Artifact export destination is outside the configured allowlist.',
            recovery_hint='Use a relative destination under the configured artifacts, downloads, or tmp directory.',
        ).to_dict()
    target = Path(safe_target).resolve(strict=False)
    source = Path(record.absolute_path).resolve(strict=False)
    allowed_bases = tuple(
        base.resolve(strict=False) for base in (config.artifacts_dir, config.downloads_dir, config.tmp_dir)
    )
    try:
        source.relative_to(config.artifacts_dir.resolve(strict=False))
        if not any(_is_relative_to(target, base) for base in allowed_bases):
            raise ValueError
    except ValueError:
        return StructuredError(
            ErrorCode.PERMISSION_DENIED, 'Artifact export path failed client allowlist validation.'
        ).to_dict()
    try:
        if not source.is_file():
            raise OSError('artifact source is no longer available')
        digest = _sha256(source)
    except OSError as exc:
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, f'Artifact source is unavailable: {exc}').to_dict()
    if digest != record.sha256:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            'Artifact source changed after registration; export was refused.',
            retryable=False,
        ).to_dict()
    if source == target:
        return {'success': True, 'artifact_id': artifact_id, 'relative_path': record.relative_path, 'copied': False}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    except OSError as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Artifact export failed: {exc}', retryable=True).to_dict()
    return {
        'contract_version': 2,
        'operation_id': f'artifact_export_{artifact_id.removeprefix("artifact_")}',
        'success': True,
        'status': 'exported',
        'artifact_id': artifact_id,
        'relative_path': _relative_to_allowed(target, allowed_bases),
        'size': target.stat().st_size,
        'sha256': digest,
        'copied': True,
    }


__all__ = ['artifact_export']


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _relative_to_allowed(path: Path, bases: tuple[Path, ...]) -> str:
    for base in bases:
        if _is_relative_to(path, base):
            return path.relative_to(base).as_posix()
    return path.name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
