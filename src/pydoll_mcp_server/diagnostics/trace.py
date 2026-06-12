"""Lightweight trace manager with redaction and per-client isolation."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceEvent:
    timestamp: float
    tool: str
    status: str
    duration_ms: float = 0
    browser_id: str = ''
    tab_id: str = ''
    error_code: str = ''
    summary: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'tool': self.tool,
            'status': self.status,
            'duration_ms': round(self.duration_ms, 2),
            'browser_id': self.browser_id,
            'tab_id': self.tab_id,
            'error_code': self.error_code,
            'summary': self.summary,
        }


@dataclass
class Trace:
    trace_id: str
    client_id: str
    name: str
    created_at: float
    status: str = 'running'
    events: list[TraceEvent] = field(default_factory=list)
    max_events: int = 500
    include_screenshots: bool = False

    def add_event(self, event: TraceEvent) -> None:
        if len(self.events) >= self.max_events:
            self.events = self.events[-self.max_events // 2 :]
        self.events.append(event)

    def stop(self) -> None:
        self.status = 'stopped'

    def summary(self) -> dict[str, Any]:
        return {
            'trace_id': self.trace_id,
            'client_id': self.client_id,
            'name': self.name,
            'status': self.status,
            'events_count': len(self.events),
            'created_at': self.created_at,
        }


class TraceManager:
    def __init__(self, max_traces: int = 50) -> None:
        self._traces: dict[str, Trace] = {}
        self._max_traces = max_traces

    def create(self, client_id: str, name: str = '', include_screenshots: bool = False) -> Trace:
        trace_id = f'trace_{uuid.uuid4().hex[:12]}'
        trace = Trace(
            trace_id=trace_id,
            client_id=client_id,
            name=name or trace_id,
            created_at=time.time(),
            include_screenshots=include_screenshots,
        )
        if len(self._traces) >= self._max_traces:
            oldest = min(self._traces.values(), key=lambda t: t.created_at)
            del self._traces[oldest.trace_id]
        self._traces[trace_id] = trace
        return trace

    def get(self, client_id: str, trace_id: str) -> Trace | None:
        trace = self._traces.get(trace_id)
        if trace and trace.client_id != client_id:
            return None
        return trace

    def stop(self, client_id: str, trace_id: str) -> Trace | None:
        trace = self.get(client_id, trace_id)
        if trace:
            trace.stop()
        return trace

    def cleanup(self, client_id: str, older_than_seconds: int = 86400) -> int:
        cutoff = time.time() - older_than_seconds
        to_remove = [
            tid
            for tid, t in self._traces.items()
            if t.client_id == client_id and t.created_at < cutoff
        ]
        for tid in to_remove:
            del self._traces[tid]
        return len(to_remove)

    def list_client_traces(self, client_id: str) -> list[dict[str, Any]]:
        return [
            t.summary()
            for t in self._traces.values()
            if t.client_id == client_id
        ]

    def get_active(self, client_id: str) -> Trace | None:
        running = [
            t for t in self._traces.values()
            if t.client_id == client_id and t.status == 'running'
        ]
        return running[-1] if running else None

    def add_event_to_active(self, client_id: str, event: TraceEvent) -> bool:
        trace = self.get_active(client_id)
        if trace is None:
            return False
        trace.add_event(event)
        return True


_trace_manager: TraceManager | None = None


def get_trace_manager() -> TraceManager:
    global _trace_manager
    if _trace_manager is None:
        _trace_manager = TraceManager()
    return _trace_manager
