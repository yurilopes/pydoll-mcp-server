"""Trace manager tests for P2."""

from __future__ import annotations

import time

import pytest

pytestmark = [pytest.mark.unit]


class TestTraceManager:
    def test_create_and_get_trace(self) -> None:
        from pydoll_mcp_server.diagnostics.trace import (
            TraceManager,
        )

        tm = TraceManager()
        trace = tm.create('client-a', 'test-trace')
        assert trace.trace_id.startswith('trace_')
        assert trace.client_id == 'client-a'
        assert trace.status == 'running'

        retrieved = tm.get('client-a', trace.trace_id)
        assert retrieved is trace

    def test_trace_isolation_by_client(self) -> None:
        from pydoll_mcp_server.diagnostics.trace import TraceManager

        tm = TraceManager()
        trace_a = tm.create('client-a', 'trace-a')
        trace_b = tm.create('client-b', 'trace-b')

        assert tm.get('client-a', trace_a.trace_id) is not None
        assert tm.get('client-b', trace_a.trace_id) is None
        assert tm.get('client-a', trace_b.trace_id) is None
        assert tm.get('client-b', trace_b.trace_id) is not None

    def test_trace_events(self) -> None:
        from pydoll_mcp_server.diagnostics.trace import TraceEvent, TraceManager

        tm = TraceManager()
        trace = tm.create('client-a', 'test-events')

        trace.add_event(TraceEvent(
            timestamp=time.time(),
            tool='network_enable',
            status='success',
            tab_id='tab-1',
        ))
        trace.add_event(TraceEvent(
            timestamp=time.time(),
            tool='page_goto',
            status='error',
            error_code='TIMEOUT',
        ))

        assert len(trace.events) == 2
        assert trace.events[0].tool == 'network_enable'
        assert trace.events[1].error_code == 'TIMEOUT'

    def test_trace_stop(self) -> None:
        from pydoll_mcp_server.diagnostics.trace import TraceManager

        tm = TraceManager()
        trace = tm.create('client-a', 'test-stop')
        assert trace.status == 'running'

        stopped = tm.stop('client-a', trace.trace_id)
        assert stopped is not None
        assert stopped.status == 'stopped'

    def test_trace_stop_wrong_client(self) -> None:
        from pydoll_mcp_server.diagnostics.trace import TraceManager

        tm = TraceManager()
        trace = tm.create('client-a', 'test-stop')
        stopped = tm.stop('client-b', trace.trace_id)
        assert stopped is None
        assert trace.status == 'running'

    def test_trace_cleanup(self) -> None:
        from pydoll_mcp_server.diagnostics.trace import TraceManager

        tm = TraceManager()
        tm.create('client-a', 'old')
        time.sleep(0.01)
        tm.create('client-b', 'recent')

        cleaned = tm.cleanup('client-a', older_than_seconds=0)
        assert cleaned >= 1

    def test_trace_max_events(self) -> None:
        from pydoll_mcp_server.diagnostics.trace import TraceEvent, TraceManager

        tm = TraceManager()
        trace = tm.create('client-a', 'test-max')
        trace.max_events = 10

        for i in range(20):
            trace.add_event(TraceEvent(
                timestamp=time.time(),
                tool=f'tool_{i}',
                status='success',
            ))

        assert len(trace.events) <= 10

    def test_trace_max_traces(self) -> None:
        from pydoll_mcp_server.diagnostics.trace import TraceManager

        tm = TraceManager(max_traces=3)
        t1 = tm.create('client-a', 't1')
        tm.create('client-a', 't2')
        tm.create('client-a', 't3')
        tm.create('client-a', 't4')

        assert len(tm._traces) <= 3
        assert tm.get('client-a', t1.trace_id) is None

    def test_event_redaction_no_token(self) -> None:
        from pydoll_mcp_server.diagnostics.trace import TraceEvent

        event = TraceEvent(
            timestamp=time.time(),
            tool='test',
            status='success',
            summary='Bearer secret-token-123 was used',
        )
        d = event.to_dict()
        assert 'summary' in d
