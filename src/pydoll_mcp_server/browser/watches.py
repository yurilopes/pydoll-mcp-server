"""Two-phase popup and download watches."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject


@dataclass
class Watch:
    watch_id: str
    client_id: str
    tab_id: str
    kind: str
    created_at: float
    task: asyncio.Task[object] | None = None
    baseline: set[str] | None = None
    result: JsonObject | None = None


class WatchManager:
    def __init__(self) -> None:
        self._watches: dict[str, Watch] = {}
        self._downloads: dict[tuple[str, str], list[JsonObject]] = {}

    def create(
        self,
        client_id: str,
        tab_id: str,
        kind: str,
        *,
        task: asyncio.Task[object] | None = None,
        baseline: set[str] | None = None,
        result: JsonObject | None = None,
    ) -> Watch:
        watch = Watch(
            f'watch_{uuid.uuid4().hex[:12]}',
            client_id,
            tab_id,
            kind,
            time.time(),
            task=task,
            baseline=baseline,
            result=result,
        )
        self._watches[watch.watch_id] = watch
        return watch

    def get(self, client_id: str, watch_id: str, kind: str) -> Watch:
        watch = self._watches.get(watch_id)
        if watch is None or watch.client_id != client_id or watch.kind != kind:
            raise StructuredError(ErrorCode.RESOURCE_NOT_FOUND, f'{kind} watch not found: {watch_id}')
        return watch

    def finish(self, watch: Watch, result: JsonObject) -> None:
        watch.result = result
        if watch.kind == 'download':
            self._downloads.setdefault((watch.client_id, watch.tab_id), []).append(result)

    def downloads(self, client_id: str, tab_id: str) -> list[JsonObject]:
        return list(self._downloads.get((client_id, tab_id), []))

    def cleanup(self, max_age: float = 3600) -> int:
        old = [key for key, value in self._watches.items() if time.time() - value.created_at > max_age]
        for key in old:
            watch = self._watches.pop(key)
            if watch.task and not watch.task.done():
                watch.task.cancel()
        return len(old)


def safe_file_info(path: str) -> JsonObject:
    item = Path(path)
    return {'path': str(item), 'name': item.name, 'size': item.stat().st_size if item.is_file() else 0}


_MANAGER = WatchManager()


def get_watch_manager() -> WatchManager:
    return _MANAGER
