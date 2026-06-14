"""Tests for concurrency locks in mutation operations."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


class TestConcurrency:
    def test_tab_operation_lock_serializes(self) -> None:
        from pydoll_mcp_server.browser.locks import LockManager

        lm = LockManager()
        order: list[str] = []

        async def mutation_a():
            async with lm.tab_mutex('tab-1'):
                order.append('a-start')
                await asyncio.sleep(0.05)
                order.append('a-end')

        async def mutation_b():
            async with lm.tab_mutex('tab-1'):
                order.append('b-start')
                await asyncio.sleep(0.01)
                order.append('b-end')

        async def run():
            await asyncio.gather(mutation_a(), mutation_b())

        asyncio.run(run())
        assert order in (
            ['a-start', 'a-end', 'b-start', 'b-end'],
            ['b-start', 'b-end', 'a-start', 'a-end'],
        )

    def test_different_tabs_independent_locks(self) -> None:
        from pydoll_mcp_server.browser.locks import LockManager

        lm = LockManager()
        completed: set[str] = set()

        async def mutation(tab_id: str):
            async with lm.tab_mutex(tab_id):
                await asyncio.sleep(0.02)
                completed.add(tab_id)

        async def run():
            await asyncio.gather(
                mutation('tab-1'),
                mutation('tab-2'),
                mutation('tab-3'),
            )

        asyncio.run(run())
        assert completed == {'tab-1', 'tab-2', 'tab-3'}

    def test_page_goto_uses_lock(self) -> None:
        import os

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            import inspect

            from pydoll_mcp_server.tools.page import page_goto
            source = inspect.getsource(page_goto)
            assert 'tab_operation_lock' in source, (
                'page_goto does not use tab_operation_lock'
            )

    def test_element_click_uses_lock(self) -> None:
        import os

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            import inspect

            from pydoll_mcp_server.tools.elements import element_click
            source = inspect.getsource(element_click)
            assert 'tab_operation_lock' in source, (
                'element_click does not use tab_operation_lock'
            )

    def test_tab_close_uses_lock(self) -> None:
        import os

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            import inspect

            from pydoll_mcp_server.tools.tabs import tab_close
            source = inspect.getsource(tab_close)
            assert 'tab_operation_lock' in source, (
                'tab_close does not use tab_operation_lock'
            )

    def test_storage_set_uses_lock(self) -> None:
        import os

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            import inspect

            from pydoll_mcp_server.tools.storage import storage_set
            source = inspect.getsource(storage_set)
            assert 'tab_operation_lock' in source, (
                'storage_set does not use tab_operation_lock'
            )

    def test_cookies_set_uses_tab_lock(self) -> None:
        import os

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            import inspect

            from pydoll_mcp_server.tools.storage import cookies_set
            source = inspect.getsource(cookies_set)
            assert 'tab_operation_lock' in source, (
                'cookies_set does not use tab_operation_lock'
            )

    def test_cookies_set_uses_browser_lock(self) -> None:
        import os

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            import inspect

            from pydoll_mcp_server.tools.storage import cookies_set
            source = inspect.getsource(cookies_set)
            assert 'browser_operation_lock' in source, (
                'cookies_set does not use browser_operation_lock'
            )


class _LockProbe:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.active: set[str] = set()

    def lock(self, resource_id: str):
        probe = self

        class _Context:
            async def __aenter__(self) -> None:
                probe.events.append(('enter', resource_id))
                probe.active.add(resource_id)

            async def __aexit__(self, *args) -> None:
                probe.events.append(('exit', resource_id))
                probe.active.discard(resource_id)

        return _Context()


class _FakeTab:
    def __init__(self, lock_probe: _LockProbe | None = None, tab_id: str = 'tab-1') -> None:
        self.lock_probe = lock_probe
        self.tab_id = tab_id
        self.url = 'http://example.test/'
        self.title_value = 'Example'
        self.calls: list[str] = []

    @property
    async def current_url(self) -> str:
        return self.url

    @property
    async def title(self) -> str:
        return self.title_value

    async def go_to(self, url: str, timeout: float | None = None) -> None:
        assert self.lock_probe is not None
        assert self.tab_id in self.lock_probe.active
        self.calls.append(f'go_to:{url}:{timeout}')
        self.url = url

    async def execute_script(self, script: str, return_by_value: bool = False):
        assert self.lock_probe is not None
        assert self.tab_id in self.lock_probe.active
        self.calls.append(script)
        return {'result': {'result': {'value': 1 if return_by_value else None}}}

    async def set_cookies(self, cookies: list[dict]) -> None:
        assert self.lock_probe is not None
        assert self.tab_id in self.lock_probe.active
        self.calls.append(f'cookies:{len(cookies)}')


class _FakeElement:
    def __init__(self, lock_probe: _LockProbe, tab_id: str = 'tab-1') -> None:
        self.lock_probe = lock_probe
        self.tab_id = tab_id
        self.calls: list[str] = []

    async def scroll_into_view(self) -> None:
        assert self.tab_id in self.lock_probe.active
        self.calls.append('scroll')

    async def click(self) -> None:
        assert self.tab_id in self.lock_probe.active
        self.calls.append('click')


class _FakeBrowser:
    def __init__(self, lock_probe: _LockProbe | None = None, browser_id: str = 'browser-1') -> None:
        self.lock_probe = lock_probe
        self.browser_id = browser_id
        self.stopped = False
        self.calls: list[str] = []

    async def start(self) -> _FakeTab:
        await asyncio.sleep(0.05)
        return _FakeTab()

    async def stop(self) -> None:
        self.stopped = True

    async def set_cookies(self, cookies: list[dict]) -> None:
        assert self.lock_probe is not None
        assert self.browser_id in self.lock_probe.active
        self.calls.append(f'cookies:{len(cookies)}')


class _FakeRegistry:
    def __init__(
        self,
        tab: _FakeTab | None = None,
        browser: _FakeBrowser | None = None,
    ) -> None:
        self.tab = tab
        self.browser = browser

    def get_tab(self, client_id: str, tab_id: str):
        return SimpleNamespace(
            client_id=client_id,
            tab_id=tab_id,
            browser_id='browser-1',
            document_generation=0,
            _pydoll_tab=self.tab,
            mark_navigated=lambda: None,
        )

    def get_pydoll_browser(self, client_id: str, browser_id: str):
        return self.browser


class TestBehavioralLocks:
    @pytest.mark.asyncio
    async def test_page_goto_operation_occurs_inside_tab_lock(self, monkeypatch) -> None:
        from pydoll_mcp_server.tools import page as page_tools

        lock_probe = _LockProbe()
        tab = _FakeTab(lock_probe)
        monkeypatch.setattr(page_tools, 'tab_operation_lock', lock_probe.lock)
        monkeypatch.setattr(page_tools, 'get_registry', lambda: _FakeRegistry(tab=tab))

        result = await page_tools.page_goto('client-1', 'tab-1', 'http://example.test/path')

        assert result['success'] is True
        assert lock_probe.events == [('enter', 'tab-1'), ('exit', 'tab-1')]
        assert tab.calls[0].startswith('go_to:http://example.test/path')

    @pytest.mark.asyncio
    async def test_element_click_operation_occurs_inside_tab_lock(self, monkeypatch) -> None:
        from pydoll_mcp_server.tools import elements as element_tools

        lock_probe = _LockProbe()
        element = _FakeElement(lock_probe)

        async def resolve_element(tab_info, element_id):
            return element

        monkeypatch.setattr(element_tools, 'tab_operation_lock', lock_probe.lock)
        monkeypatch.setattr(element_tools, 'get_registry', lambda: _FakeRegistry())
        monkeypatch.setattr(
            element_tools,
            '_resolve_element',
            resolve_element,
        )

        result = await element_tools.element_click('client-1', 'tab-1', 'el-1')

        assert result['success'] is True
        assert lock_probe.events == [('enter', 'tab-1'), ('exit', 'tab-1')]
        assert element.calls == ['scroll', 'click']

    @pytest.mark.asyncio
    async def test_storage_set_operation_occurs_inside_tab_lock(self, monkeypatch) -> None:
        from pydoll_mcp_server.tools import storage as storage_tools

        lock_probe = _LockProbe()
        tab = _FakeTab(lock_probe)
        monkeypatch.setattr(storage_tools, 'tab_operation_lock', lock_probe.lock)
        monkeypatch.setattr(storage_tools, 'get_registry', lambda: _FakeRegistry(tab=tab))

        result = await storage_tools.storage_set(
            'client-1',
            'tab-1',
            items=[{'type': 'local', 'key': 'k', 'value': 'v'}],
        )

        assert result['success'] is True
        assert lock_probe.events == [('enter', 'tab-1'), ('exit', 'tab-1')]

    @pytest.mark.asyncio
    async def test_cookies_set_operation_occurs_inside_tab_lock(self, monkeypatch) -> None:
        from pydoll_mcp_server.tools import storage as storage_tools

        lock_probe = _LockProbe()
        tab = _FakeTab(lock_probe)
        monkeypatch.setattr(storage_tools, 'tab_operation_lock', lock_probe.lock)
        monkeypatch.setattr(storage_tools, 'get_registry', lambda: _FakeRegistry(tab=tab))

        result = await storage_tools.cookies_set(
            'client-1',
            tab_id='tab-1',
            cookies=[{'name': 'a', 'value': 'b'}],
        )

        assert result['success'] is True
        assert lock_probe.events == [('enter', 'tab-1'), ('exit', 'tab-1')]

    @pytest.mark.asyncio
    async def test_cookies_set_operation_occurs_inside_browser_lock(self, monkeypatch) -> None:
        from pydoll_mcp_server.tools import storage as storage_tools

        lock_probe = _LockProbe()
        browser = _FakeBrowser(lock_probe)
        monkeypatch.setattr(storage_tools, 'browser_operation_lock', lock_probe.lock)
        monkeypatch.setattr(
            storage_tools,
            'get_registry',
            lambda: _FakeRegistry(browser=browser),
        )

        result = await storage_tools.cookies_set(
            'client-1',
            browser_id='browser-1',
            cookies=[{'name': 'a', 'value': 'b'}],
        )

        assert result['success'] is True
        assert lock_probe.events == [('enter', 'browser-1'), ('exit', 'browser-1')]
