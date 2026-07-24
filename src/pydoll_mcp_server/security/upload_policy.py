"""Local upload source policy and validation shared by all upload tools."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.security.policy import PathAllowlist

DEFAULT_MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class UploadSource:
    """A validated local file selected explicitly by an upload operation."""

    requested_path: str
    resolved_path: Path
    filename: str
    size_bytes: int


class UploadPathError(ValueError):
    """A source path failed the common upload validation contract."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        *,
        details: JsonObject | None = None,
        retryable: bool = False,
        recovery_hint: str = '',
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.retryable = retryable
        self.recovery_hint = recovery_hint

    def to_dict(self) -> JsonObject:
        return StructuredError(
            self.error_code,
            self.message,
            details=self.details,
            retryable=self.retryable,
            recovery_hint=self.recovery_hint,
        ).to_dict()


def upload_allowlist() -> PathAllowlist:
    """Return the configured upload policy, local and frictionless by default."""

    config = get_config()
    allowed_dirs = [str(config.artifacts_dir), str(config.downloads_dir), str(config.tmp_dir)]
    for env_name in ('PYDOLL_MCP_UPLOAD_ALLOWLIST', 'PYDOLL_MCP_IMPORT_ALLOWLIST'):
        extra_allowed = os.environ.get(env_name, '')
        if extra_allowed:
            allowed_dirs.extend(extra_allowed.split(os.pathsep))
    return PathAllowlist(allowed_dirs, allow_any=config.upload_policy == 'local')


def resolve_upload_source(
    path: str,
    max_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES,
) -> UploadSource:
    """Resolve and validate one explicit local file before browser interaction."""

    if not path.strip():
        raise UploadPathError(ErrorCode.INVALID_INPUT, 'Upload path is required.')
    candidate = Path(path)
    try:
        policy_path = candidate.resolve(strict=False)
    except OSError:
        raise UploadPathError(ErrorCode.PERMISSION_DENIED, f'Upload path could not be resolved: {path}') from None
    if not upload_allowlist().is_allowed(str(policy_path)):
        raise UploadPathError(
            ErrorCode.PERMISSION_DENIED,
            f'Upload path not in allowed directories: {path}',
            recovery_hint='Set PYDOLL_MCP_UPLOAD_POLICY=local or configure an explicit upload allowlist.',
        )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise UploadPathError(ErrorCode.RESOURCE_NOT_FOUND, f'Upload file does not exist: {path}') from None
    if not resolved.is_file():
        raise UploadPathError(ErrorCode.INVALID_INPUT, f'Upload path is not a regular file: {path}')
    try:
        size = resolved.stat().st_size
    except OSError:
        raise UploadPathError(ErrorCode.RESOURCE_NOT_FOUND, f'Upload file could not be inspected: {path}') from None
    if size > max_size_bytes:
        raise UploadPathError(
            ErrorCode.INVALID_INPUT,
            f'Upload file is too large: {size} bytes (max {max_size_bytes}).',
        )
    return UploadSource(path, resolved, resolved.name, size)


def validate_upload_path(path: str, max_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES) -> JsonObject | None:
    """Return a structured error or None for one valid local upload source."""

    try:
        resolve_upload_source(path, max_size_bytes)
    except UploadPathError as exc:
        return exc.to_dict()
    return None


__all__ = [
    'DEFAULT_MAX_UPLOAD_SIZE_BYTES',
    'UploadPathError',
    'UploadSource',
    'resolve_upload_source',
    'upload_allowlist',
    'validate_upload_path',
]
