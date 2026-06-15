"""Bounded page snapshot storage and comparison."""

from __future__ import annotations

import uuid
from collections import defaultdict, deque

from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject


class SnapshotManager:
    def __init__(self, per_tab_limit: int = 20) -> None:
        self._items: dict[tuple[str, str], deque[JsonObject]] = defaultdict(
            lambda: deque(maxlen=per_tab_limit),
        )

    def store(self, client_id: str, tab_id: str, snapshot: JsonObject) -> str:
        snapshot_id = f'snap_{uuid.uuid4().hex[:12]}'
        snapshot['snapshot_id'] = snapshot_id
        self._items[(client_id, tab_id)].append(snapshot)
        return snapshot_id

    def get(self, client_id: str, tab_id: str, snapshot_id: str) -> JsonObject:
        for item in self._items[(client_id, tab_id)]:
            if item.get('snapshot_id') == snapshot_id:
                return item
        raise StructuredError(ErrorCode.RESOURCE_NOT_FOUND, f'Snapshot not found: {snapshot_id}')

    def clear_tab(self, client_id: str, tab_id: str) -> None:
        self._items.pop((client_id, tab_id), None)


_MANAGER = SnapshotManager()


def get_snapshot_manager() -> SnapshotManager:
    return _MANAGER
