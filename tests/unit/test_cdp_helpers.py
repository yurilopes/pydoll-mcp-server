"""Tests for CDP-backed helper tools."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pytest import MonkeyPatch

from pydoll_mcp_server.json_types import JsonObject, JsonValue

pytestmark = [pytest.mark.unit]


class _FakeTab:
    def __init__(self, value: JsonValue) -> None:
        self.value = value
        self.calls: list[tuple[str, bool]] = []

    async def execute_script(self, script: str, return_by_value: bool = False) -> JsonObject:
        self.calls.append((script, return_by_value))
        return {'result': {'result': {'value': self.value}}}


class _FakeRegistry:
    def __init__(self, tab: _FakeTab) -> None:
        self.tab = tab

    def get_tab(self, client_id: str, tab_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            client_id=client_id,
            tab_id=tab_id,
            pydoll_tab=self.tab,
        )


@pytest.mark.asyncio
async def test_user_agent_get_reads_navigator_user_agent(monkeypatch: MonkeyPatch) -> None:
    from pydoll_mcp_server.browser import cdp_helpers

    tab = _FakeTab('TestAgent/1.0')
    monkeypatch.setattr(cdp_helpers, 'get_registry', lambda: _FakeRegistry(tab))

    result = await cdp_helpers.get_user_agent('client-1', 'tab-1')

    assert result == {
        'success': True,
        'tab_id': 'tab-1',
        'user_agent': 'TestAgent/1.0',
        'source': 'navigator.userAgent',
    }
    assert tab.calls == [('return navigator.userAgent;', True)]


@pytest.mark.asyncio
async def test_viewport_get_reads_window_metrics(monkeypatch: MonkeyPatch) -> None:
    from pydoll_mcp_server.browser import cdp_helpers

    viewport: JsonObject = {'width': 1024, 'height': 768, 'device_pixel_ratio': 1.25}
    tab = _FakeTab(viewport)
    monkeypatch.setattr(cdp_helpers, 'get_registry', lambda: _FakeRegistry(tab))

    result = await cdp_helpers.get_viewport('client-1', 'tab-1')

    assert result == {
        'success': True,
        'tab_id': 'tab-1',
        'viewport': viewport,
        'source': 'window',
    }
    script, return_by_value = tab.calls[0]
    assert 'window.innerWidth' in script
    assert 'window.innerHeight' in script
    assert 'window.devicePixelRatio' in script
    assert return_by_value is True
