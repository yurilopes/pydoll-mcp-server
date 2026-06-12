"""Network and console inspection state per tab."""

from __future__ import annotations

from collections import defaultdict


class InspectionState:
    def __init__(self, max_events: int = 1000) -> None:
        self.network_events: list[dict] = []
        self.console_events: list[dict] = []
        self.network_enabled: bool = False
        self.console_enabled: bool = False
        self.max_events = max_events

    def add_network_event(self, event: dict) -> None:
        if len(self.network_events) >= self.max_events:
            self.network_events = self.network_events[-self.max_events // 2:]
        self.network_events.append(event)

    def add_console_event(self, event: dict) -> None:
        if len(self.console_events) >= self.max_events:
            self.console_events = self.console_events[-self.max_events // 2:]
        self.console_events.append(event)

    def clear_network(self) -> None:
        self.network_events.clear()
        self.network_enabled = False

    def clear_console(self) -> None:
        self.console_events.clear()
        self.console_enabled = False


class InspectionManager:
    def __init__(self) -> None:
        self._states: dict[str, InspectionState] = defaultdict(InspectionState)

    def get(self, tab_id: str) -> InspectionState:
        return self._states[tab_id]

    def remove(self, tab_id: str) -> None:
        self._states.pop(tab_id, None)


_inspection: InspectionManager | None = None


def get_inspection_manager() -> InspectionManager:
    global _inspection
    if _inspection is None:
        _inspection = InspectionManager()
    return _inspection
