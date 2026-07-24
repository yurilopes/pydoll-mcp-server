"""Shared source handling for frictionless local uploads."""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.errors import ErrorCode
from pydoll_mcp_server.security.upload_policy import (
    DEFAULT_MAX_UPLOAD_SIZE_BYTES,
    UploadPathError,
    UploadSource,
    resolve_upload_source,
)


@dataclass
class NativePickerUpload:
    """Original source and the path presented to a native picker."""

    source: UploadSource
    picker_path: Path
    staging_dir: Path | None

    @property
    def staged(self) -> bool:
        return self.staging_dir is not None

    async def cleanup(self) -> None:
        if self.staging_dir is not None:
            await asyncio.to_thread(_remove_staging_dir, self.staging_dir)


async def prepare_native_picker_upload(
    path: str,
    max_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES,
) -> NativePickerUpload:
    """Copy one validated source to a user-controlled picker-safe directory."""

    source = resolve_upload_source(path, max_size_bytes)
    if not _is_windows():
        return NativePickerUpload(source, source.resolved_path, None)

    staging_root = get_config().native_upload_staging_dir
    staging_dir = staging_root / uuid.uuid4().hex
    picker_path = staging_dir / source.filename
    try:
        await asyncio.to_thread(_copy_source_with_retry, source.resolved_path, picker_path, staging_dir)
    except OSError as exc:
        await asyncio.to_thread(_remove_staging_dir, staging_dir)
        raise UploadPathError(
            ErrorCode.EXECUTION_ERROR,
            f'Could not stage upload for the native picker: {exc}',
            details={'reason': 'native_upload_staging_failed'},
            retryable=True,
            recovery_hint='Use a writable user-controlled upload staging directory.',
        ) from exc
    return NativePickerUpload(source, picker_path, staging_dir)


def _copy_source_with_retry(source: Path, target: Path, staging_dir: Path) -> None:
    staging_dir.mkdir(parents=True, exist_ok=False)
    last_error: OSError | None = None
    for _attempt in range(3):
        try:
            before_size = source.stat().st_size
            shutil.copy2(source, target)
            after_size = source.stat().st_size
            if before_size == after_size and target.stat().st_size == after_size:
                return
            target.unlink(missing_ok=True)
        except OSError as exc:
            last_error = exc
        time.sleep(0.2)
    if last_error is not None:
        raise last_error
    raise OSError('The source file changed while it was being staged')


def _remove_staging_dir(staging_dir: Path) -> None:
    with suppress(OSError):
        shutil.rmtree(staging_dir)


def _is_windows() -> bool:
    return sys.platform == 'win32'


__all__ = ['NativePickerUpload', 'prepare_native_picker_upload']
