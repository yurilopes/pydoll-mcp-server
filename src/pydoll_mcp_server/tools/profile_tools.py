"""Profile listing and promotion tools."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import time
from pathlib import Path

from pydoll_mcp_server.auth import ClientIdentity
from pydoll_mcp_server.browser.models import ProfileMode
from pydoll_mcp_server.browser.profile_index import ProfileIndexEntry, get_profile_index
from pydoll_mcp_server.browser.profiles import get_profile_manager
from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject


async def profile_list(client_id: str = '', include_site_hints: bool = False) -> JsonObject:
    index = get_profile_index()
    index.discover_preserved_temps(client_id=client_id)

    entries = index.list_all(owner_client_id=client_id) if client_id else index.list_all()

    profiles: JsonArray = []
    for entry in entries:
        item: JsonObject = {
            'profile_id': entry.profile_id,
            'owner_client_id': entry.owner_client_id,
            'mode': entry.mode,
            'last_used_at': entry.last_used_at,
            'display_name': entry.display_name,
            'path_kind': entry.path_kind,
            'is_locked': entry.is_locked,
        }
        if include_site_hints:
            item['site_hints'] = list(entry.site_hints)
        profiles.append(item)
    return {
        'success': True,
        'profiles': profiles,
        'count': len(profiles),
    }


async def profile_promote(
    source_profile_id: str,
    target_profile_id: str,
    client_id: str,
    overwrite: bool = False,
) -> JsonObject:
    config = get_config()
    profile_mgr = get_profile_manager()
    index = get_profile_index()
    now = time.time()

    index.discover_preserved_temps(client_id=client_id)

    source_info = profile_mgr.get(source_profile_id)
    source_index_entry = index.get(source_profile_id)

    if source_info is None and source_index_entry is None:
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f'Source profile {source_profile_id} not found',
            retryable=False,
        ).to_dict()

    if source_info is not None and source_info.mode != ProfileMode.TEMPORARY:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'Only temporary profiles can be promoted',
            retryable=False,
        ).to_dict()

    if source_index_entry and source_index_entry.mode not in ('temporary',):
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            f'Source profile {source_profile_id} is not temporary',
            retryable=False,
        ).to_dict()

    is_preserved = source_index_entry is not None and source_index_entry.path_kind == 'preserved_temporary'

    if source_info is not None:
        source_path = Path(source_info.path).resolve()
    elif is_preserved and source_index_entry:
        display = source_index_entry.display_name
        owner = source_index_entry.owner_client_id
        tmp_scan = config.tmp_dir / owner / display
        if tmp_scan.exists():
            source_path = tmp_scan.resolve()
        else:
            return StructuredError(
                ErrorCode.RESOURCE_NOT_FOUND,
                f'Preserved temporary profile directory not found: {display}',
                retryable=False,
            ).to_dict()
    else:
        return StructuredError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f'Cannot resolve source path for {source_profile_id}',
            retryable=False,
        ).to_dict()

    allowed_roots = [
        config.profiles_dir.resolve(),
        config.tmp_dir.resolve(),
    ]
    if not any(is_under(source_path, root) for root in allowed_roots):
        return StructuredError(
            ErrorCode.PERMISSION_DENIED,
            'Source profile is not inside managed runtime directories',
            retryable=False,
        ).to_dict()

    safe_target_name = ClientIdentity(target_profile_id).safe
    if not safe_target_name:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'target_profile_id produces empty safe name',
            retryable=False,
        ).to_dict()
    target_dir = (config.profiles_dir / ClientIdentity(client_id).safe / safe_target_name).resolve()
    if not is_under(target_dir, config.profiles_dir.resolve()):
        return StructuredError(
            ErrorCode.PERMISSION_DENIED,
            'Destination profile path is not inside managed profiles directory',
            retryable=False,
        ).to_dict()

    if target_dir.exists():
        if not overwrite:
            return StructuredError(
                ErrorCode.INVALID_INPUT,
                f'Target profile {target_profile_id} already exists. Use overwrite=true to replace.',
                retryable=False,
                recovery_hint='Use overwrite=true if you intend to replace the existing profile.',
            ).to_dict()
        try:
            await asyncio.to_thread(shutil.rmtree, str(target_dir))
        except OSError as exc:
            return StructuredError(
                ErrorCode.EXECUTION_ERROR,
                f'Failed to remove existing target directory: {exc}',
                retryable=True,
            ).to_dict()

    try:
        await asyncio.to_thread(_copy_profile_dir, str(source_path), str(target_dir))
    except OSError as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Failed to copy profile: {exc}',
            retryable=True,
        ).to_dict()

    for lock_file in target_dir.glob('Singleton*'):
        with contextlib.suppress(OSError):
            os.unlink(lock_file)

    new_info = profile_mgr.create_named(client_id, target_profile_id)
    new_info.path = str(target_dir)

    source_hints: list[str] = list(source_index_entry.site_hints) if source_index_entry else []
    index_entry = ProfileIndexEntry(
        profile_id=new_info.profile_id,
        owner_client_id=client_id,
        mode='persistent',
        created_at=now,
        last_used_at=now,
        display_name=target_profile_id,
        site_hints=source_hints,
        path_kind='promoted_from_temporary',
    )
    index.upsert(new_info.profile_id, index_entry)

    return {
        'success': True,
        'source_profile_id': source_profile_id,
        'target_profile_id': new_info.profile_id,
        'mode': 'persistent',
        'warnings': [],
    }


async def profile_list_non_async(client_id: str = '', include_site_hints: bool = False) -> JsonObject:
    return await profile_list(client_id=client_id, include_site_hints=include_site_hints)


def is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _copy_profile_dir(src: str, dst: str) -> None:
    shutil.copytree(src, dst, symlinks=False, ignore=shutil.ignore_patterns('Singleton*'))
