"""Profile management for browser user data directories."""

from __future__ import annotations

import shutil
import tempfile
import time

from pydoll_mcp_server.auth import ClientIdentity
from pydoll_mcp_server.browser.models import ProfileInfo, ProfileMode, generate_id
from pydoll_mcp_server.config import get_config


class ProfileManager:
    def __init__(self) -> None:
        self._profiles: dict[str, ProfileInfo] = {}
        self._locks: dict[str, str] = {}
        config = get_config()
        self._profiles_dir = config.profiles_dir
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

    def get_or_create_default(
        self,
        client_id: str,
    ) -> ProfileInfo:
        identity = ClientIdentity(client_id)
        profile_dir = self._profiles_dir / identity.safe / 'default'
        profile_id = f'prof_{identity.safe}_default'
        if profile_id in self._profiles:
            return self._profiles[profile_id]
        info = ProfileInfo(
            profile_id=profile_id,
            client_id=client_id,
            mode=ProfileMode.PERSISTENT,
            path=str(profile_dir),
        )
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._profiles[profile_id] = info
        return info

    def create_temporary(self, client_id: str) -> ProfileInfo:
        identity = ClientIdentity(client_id)
        tmp_root = get_config().tmp_dir / identity.safe
        tmp_root.mkdir(parents=True, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(prefix='profile_', dir=str(tmp_root))
        profile_id = generate_id('prof')
        info = ProfileInfo(
            profile_id=profile_id,
            client_id=client_id,
            mode=ProfileMode.TEMPORARY,
            path=tmp_dir,
        )
        self._profiles[profile_id] = info
        return info

    def create_named(self, client_id: str, profile_name: str) -> ProfileInfo:
        identity = ClientIdentity(client_id)
        safe_name = ClientIdentity(profile_name).safe
        profile_dir = self._profiles_dir / identity.safe / safe_name
        profile_id = f'prof_{identity.safe}_{safe_name}'
        if profile_id in self._profiles:
            return self._profiles[profile_id]
        info = ProfileInfo(
            profile_id=profile_id,
            client_id=client_id,
            mode=ProfileMode.PERSISTENT,
            path=str(profile_dir),
        )
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._profiles[profile_id] = info
        return info

    def lock(self, profile_id: str, owner: str) -> bool:
        if profile_id in self._locks:
            return False
        self._locks[profile_id] = owner
        if profile_id in self._profiles:
            self._profiles[profile_id].is_locked = True
            self._profiles[profile_id].locked_by = owner
        return True

    def unlock(self, profile_id: str) -> None:
        self._locks.pop(profile_id, None)
        if profile_id in self._profiles:
            self._profiles[profile_id].is_locked = False
            self._profiles[profile_id].locked_by = ''

    def is_locked(self, profile_id: str) -> bool:
        return profile_id in self._locks

    def cleanup_temporary(self, profile_id: str) -> None:
        if profile_id not in self._profiles:
            return
        info = self._profiles[profile_id]
        if info.mode == ProfileMode.TEMPORARY:
            for attempt in range(5):
                try:
                    shutil.rmtree(info.path, ignore_errors=False)
                    break
                except OSError:
                    if attempt == 4:
                        raise
                    # Chromium can briefly retain profile files after process shutdown on Windows.
                    time.sleep(0.2 * (attempt + 1))
        self._profiles.pop(profile_id, None)
        self._locks.pop(profile_id, None)

    def release(self, profile_id: str) -> None:
        self._profiles.pop(profile_id, None)
        self._locks.pop(profile_id, None)

    def get(self, profile_id: str) -> ProfileInfo | None:
        return self._profiles.get(profile_id)


_profile_manager: ProfileManager | None = None


def get_profile_manager() -> ProfileManager:
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ProfileManager()
    return _profile_manager
