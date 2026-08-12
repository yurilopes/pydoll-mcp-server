"""Cross-process ownership leases for managed browser profiles."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from urllib.parse import urlsplit

from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.json_types import InvalidJsonValueError, JsonObject, normalize_json_value


@dataclass
class ProfileLease:
    """An OS-backed exclusive lease held for the lifetime of a browser."""

    key: str
    path: Path
    handle: TextIO
    client_id: str
    profile_id: str
    profile_path: str

    def write_metadata(
        self,
        browser_pid: int | None = None,
        cdp_port: int | None = None,
        tab_target_ids: list[str] | None = None,
        tab_urls: list[str] | None = None,
    ) -> None:
        payload = {
            'client_id': self.client_id,
            'profile_id': self.profile_id,
            'server_pid': os.getpid(),
            'browser_pid': browser_pid,
            'cdp_port': cdp_port,
            'profile_path': self.profile_path,
            'last_known_tab_target_ids': list(tab_target_ids or []),
            'last_known_url_origins': [_redact_url(item) for item in tab_urls or []],
        }
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(json.dumps(payload, sort_keys=True))
        self.handle.flush()


class ProfileLeaseManager:
    """Own profile leases in this process and release them deterministically."""

    def __init__(self) -> None:
        self._leases: dict[str, ProfileLease] = {}
        self._locks_dir = get_config().runtime_dir / 'profile-leases'
        self._locks_dir.mkdir(parents=True, exist_ok=True)

    def acquire(self, profile_path: str, client_id: str, profile_id: str) -> ProfileLease | None:
        key = _profile_key(profile_path)
        if key in self._leases or key in _held_keys:
            return None
        path = self._locks_dir / f'{key}.lock'
        handle = path.open('a+', encoding='utf-8')
        try:
            _lock_handle(handle)
        except (BlockingIOError, OSError):
            handle.close()
            return None
        lease = ProfileLease(key, path, handle, client_id, profile_id, str(Path(profile_path).resolve()))
        try:
            lease.write_metadata()
        except OSError:
            with contextlib.suppress(OSError):
                _unlock_handle(handle)
            handle.close()
            return None
        self._leases[key] = lease
        _held_keys.add(key)
        return lease

    def release(self, lease: ProfileLease | None) -> None:
        if lease is None:
            return
        self._leases.pop(lease.key, None)
        _held_keys.discard(lease.key)
        with contextlib.suppress(OSError):
            _unlock_handle(lease.handle)
        with contextlib.suppress(OSError):
            lease.handle.close()

    def release_all(self) -> None:
        for lease in list(self._leases.values()):
            self.release(lease)

    def release_by_profile(self, profile_path: str) -> None:
        lease = self._leases.get(_profile_key(profile_path))
        self.release(lease)

    def is_held(self, profile_path: str) -> bool:
        return _profile_key(profile_path) in self._leases

    def find_metadata(self, profile_id: str, client_id: str = '') -> JsonObject | None:
        """Read restart metadata without claiming ownership of a profile."""

        for path in self._locks_dir.glob('*.lock'):
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            try:
                normalized = normalize_json_value(payload, 'lease metadata')
            except InvalidJsonValueError:
                continue
            if not isinstance(normalized, dict):
                continue
            payload_object: JsonObject = normalized
            if str(payload_object.get('profile_id', '')) != profile_id:
                continue
            if client_id and str(payload_object.get('client_id', '')) != client_id:
                continue
            return payload_object
        return None


def _profile_key(profile_path: str) -> str:
    canonical = str(Path(profile_path).resolve()).lower()
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = f':{parsed.port}' if parsed.port else ''
    except ValueError:
        return ''
    if not parsed.scheme or not parsed.hostname:
        return ''
    return f'{parsed.scheme.lower()}://{parsed.hostname.lower()}{port}/'


def _lock_handle(handle: TextIO) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(' ')
        handle.flush()
    handle.seek(0)
    if sys.platform == 'win32':
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_handle(handle: TextIO) -> None:
    if sys.platform == 'win32':
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


_lease_manager: ProfileLeaseManager | None = None
_held_keys: set[str] = set()


def get_profile_lease_manager() -> ProfileLeaseManager:
    global _lease_manager
    if _lease_manager is None:
        _lease_manager = ProfileLeaseManager()
    return _lease_manager
