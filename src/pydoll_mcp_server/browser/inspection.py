"""Network and console inspection state per tab."""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict, defaultdict

from pydoll_mcp_server.json_types import JsonObject

DEFAULT_MAX_CAPTURE_BYTES = 16 * 1024 * 1024


class InspectionState:
    def __init__(self, max_events: int = 1000) -> None:
        self.requests: OrderedDict[str, JsonObject] = OrderedDict()
        self.network_events: list[JsonObject] = []
        self.discarded_request_ids: set[str] = set()
        self.console_events: list[JsonObject] = []
        self.network_enabled = False
        self.console_enabled = False
        self.network_callback_ids: list[int] = []
        self.console_callback_id: int | None = None
        self.max_events = max_events
        self.max_capture_bytes = DEFAULT_MAX_CAPTURE_BYTES
        self.capture_bytes = 0
        self.generation = 0
        self.changed = asyncio.Event()

    def upsert_request(self, request_id: str, record: JsonObject) -> None:
        previous = self.requests.pop(request_id, None)
        if previous is not None:
            self.capture_bytes -= self._size(previous)
        size = self._size(record)
        if size > self.max_capture_bytes:
            self.discarded_request_ids.add(request_id)
        else:
            self.requests[request_id] = record
            self.capture_bytes += size
            while len(self.requests) > self.max_events or self.capture_bytes > self.max_capture_bytes:
                old_id, old = self.requests.popitem(last=False)
                self.capture_bytes -= self._size(old)
                self.discarded_request_ids.add(old_id)
        self.generation += 1
        self.changed.set()

    def touch(self) -> None:
        self.generation += 1
        self.changed.set()

    def add_console_event(self, event: JsonObject) -> None:
        if len(self.console_events) >= self.max_events:
            self.console_events = self.console_events[-self.max_events // 2 :]
        self.console_events.append(event)

    def add_network_event(self, event: JsonObject) -> None:
        if len(self.network_events) >= self.max_events:
            self.network_events = self.network_events[-self.max_events // 2 :]
        self.network_events.append(event)

    def clear_network(self) -> None:
        self.requests.clear()
        self.network_events.clear()
        self.discarded_request_ids.clear()
        self.capture_bytes = 0
        self.touch()

    def disable_network(self) -> None:
        self.clear_network()
        self.network_enabled = False
        self.network_callback_ids.clear()

    def clear_console(self) -> None:
        self.console_events.clear()

    def disable_console(self) -> None:
        self.clear_console()
        self.console_enabled = False
        self.console_callback_id = None

    @staticmethod
    def _size(value: JsonObject) -> int:
        return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


class InspectionManager:
    def __init__(self) -> None:
        self._states: dict[str, InspectionState] = defaultdict(InspectionState)

    def get(self, tab_id: str) -> InspectionState:
        return self._states[tab_id]

    def remove(self, tab_id: str) -> None:
        state = self._states.pop(tab_id, None)
        if state is not None:
            state.clear_network()
            state.clear_console()


_inspection: InspectionManager | None = None


def get_inspection_manager() -> InspectionManager:
    global _inspection
    if _inspection is None:
        _inspection = InspectionManager()
    return _inspection
