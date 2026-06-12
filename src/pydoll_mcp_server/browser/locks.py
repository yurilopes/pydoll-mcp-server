"""Resource locks for concurrent operations."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class ResourceLock:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: str = ''

    @property
    def owner(self) -> str:
        return self._owner

    def is_locked(self) -> bool:
        return self._lock.locked()

    async def __aenter__(self) -> None:
        await self._lock.acquire()

    async def __aexit__(self, *args: Any) -> None:
        self._owner = ''
        self._lock.release()


class LockManager:
    def __init__(self) -> None:
        self._tab_locks: dict[str, ResourceLock] = defaultdict(ResourceLock)
        self._browser_locks: dict[str, ResourceLock] = defaultdict(ResourceLock)
        self._profile_locks: dict[str, ResourceLock] = defaultdict(ResourceLock)

    def tab_mutex(self, tab_id: str) -> ResourceLock:
        return self._tab_locks[tab_id]

    def browser_mutex(self, browser_id: str) -> ResourceLock:
        return self._browser_locks[browser_id]

    def profile_mutex(self, profile_id: str) -> ResourceLock:
        return self._profile_locks[profile_id]

    def clear_tab(self, tab_id: str) -> None:
        self._tab_locks.pop(tab_id, None)

    def clear_browser(self, browser_id: str) -> None:
        self._browser_locks.pop(browser_id, None)

    def clear_profile(self, profile_id: str) -> None:
        self._profile_locks.pop(profile_id, None)


_lock_manager: LockManager | None = None


def get_lock_manager() -> LockManager:
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = LockManager()
    return _lock_manager


@asynccontextmanager
async def tab_operation_lock(tab_id: str) -> AsyncIterator[None]:
    lm = get_lock_manager()
    async with lm.tab_mutex(tab_id):
        yield


@asynccontextmanager
async def browser_operation_lock(browser_id: str) -> AsyncIterator[None]:
    lm = get_lock_manager()
    async with lm.browser_mutex(browser_id):
        yield
