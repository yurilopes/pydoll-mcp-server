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
        self.websockets: OrderedDict[str, JsonObject] = OrderedDict()
        self.websocket_frames: list[JsonObject] = []
        self.discarded_websocket_ids: set[str] = set()
        self.discarded_websocket_frame_ids: set[str] = set()
        self.console_events: list[JsonObject] = []
        self.network_enabled = False
        self.console_enabled = False
        self.network_callback_ids: list[int] = []
        self.console_callback_id: int | None = None
        self.max_events = max_events
        self.max_capture_bytes = DEFAULT_MAX_CAPTURE_BYTES
        self.capture_bytes = 0
        self.websocket_capture_bytes = 0
        self.websocket_frame_sequence = 0
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

    def upsert_websocket(self, request_id: str, record: JsonObject) -> None:
        previous = self.websockets.pop(request_id, None)
        if previous is not None:
            self.websocket_capture_bytes -= self._size(previous)
        size = self._size(record)
        if size > self.max_capture_bytes:
            self.discarded_websocket_ids.add(request_id)
        else:
            self.websockets[request_id] = record
            self.websocket_capture_bytes += size
            self._trim_websocket_capture()
        self.touch()

    def add_websocket_frame(self, frame: JsonObject) -> None:
        self.websocket_frame_sequence += 1
        frame_id = f'wsf-{self.websocket_frame_sequence}'
        record = {'frame_id': frame_id, **frame}
        size = self._size(record)
        if size > self.max_capture_bytes:
            self.discarded_websocket_frame_ids.add(frame_id)
        else:
            self.websocket_frames.append(record)
            self.websocket_capture_bytes += size
            self._trim_websocket_capture()
        self.touch()

    def clear_network(self) -> None:
        self.requests.clear()
        self.network_events.clear()
        self.discarded_request_ids.clear()
        self.websockets.clear()
        self.websocket_frames.clear()
        self.discarded_websocket_ids.clear()
        self.discarded_websocket_frame_ids.clear()
        self.capture_bytes = 0
        self.websocket_capture_bytes = 0
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

    def _trim_websocket_capture(self) -> None:
        while len(self.websockets) > self.max_events and self.websockets:
            old_id, old = self.websockets.popitem(last=False)
            self.websocket_capture_bytes -= self._size(old)
            self.discarded_websocket_ids.add(old_id)
        while (
            len(self.websocket_frames) > self.max_events or self.websocket_capture_bytes > self.max_capture_bytes
        ) and self.websocket_frames:
            old_frame = self.websocket_frames.pop(0)
            self.websocket_capture_bytes -= self._size(old_frame)
            frame_id = old_frame.get('frame_id')
            if isinstance(frame_id, str):
                self.discarded_websocket_frame_ids.add(frame_id)

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
