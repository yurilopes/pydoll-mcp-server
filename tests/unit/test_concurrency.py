"""Tests for concurrency locks in mutation operations."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace, TracebackType

import pytest
from pytest import MonkeyPatch

from pydoll_mcp_server.json_types import JsonObject

pytestmark = [pytest.mark.unit]


class TestConcurrency:
    def test_tab_operation_lock_serializes(self) -> None:
        from pydoll_mcp_server.browser.locks import LockManager

        lm = LockManager()
        order: list[str] = []

        async def mutation_a() -> None:
            async with lm.tab_mutex('tab-1'):
                order.append('a-start')
                await asyncio.sleep(0.05)
                order.append('a-end')

        async def mutation_b() -> None:
            async with lm.tab_mutex('tab-1'):
                order.append('b-start')
                await asyncio.sleep(0.01)
                order.append('b-end')

        async def run() -> None:
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

        async def mutation(tab_id: str) -> None:
            async with lm.tab_mutex(tab_id):
                await asyncio.sleep(0.02)
                completed.add(tab_id)

        async def run() -> None:
            await asyncio.gather(
                mutation('tab-1'),
                mutation('tab-2'),
                mutation('tab-3'),
            )

        asyncio.run(run())
        assert completed == {'tab-1', 'tab-2', 'tab-3'}


class _LockProbe:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.active: set[str] = set()

    def lock(self, resource_id: str) -> object:
        probe = self

        class _Context:
            async def __aenter__(self) -> None:
                probe.events.append(('enter', resource_id))
                probe.active.add(resource_id)

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
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

    async def execute_script(self, script: str, return_by_value: bool = False) -> JsonObject:
        assert self.lock_probe is not None
        assert self.tab_id in self.lock_probe.active
        self.calls.append(script)
        return {'result': {'result': {'value': 1 if return_by_value else None}}}

    async def set_cookies(self, cookies: list[JsonObject]) -> None:
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

    async def execute_script(self, script: str, return_by_value: bool = False) -> JsonObject:
        assert self.tab_id in self.lock_probe.active
        self.calls.append(script)
        return {'result': {'result': {'value': True if return_by_value else None}}}

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

    async def set_cookies(self, cookies: list[JsonObject]) -> None:
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

    def get_tab(self, client_id: str, tab_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            client_id=client_id,
            tab_id=tab_id,
            browser_id='browser-1',
            document_generation=0,
            pydoll_tab=self.tab,
            mark_navigated=lambda: None,
        )

    def get_pydoll_browser(self, client_id: str, browser_id: str) -> _FakeBrowser | None:
        return self.browser


class TestBehavioralLocks:
    @pytest.mark.asyncio
    async def test_page_goto_operation_occurs_inside_tab_lock(self, monkeypatch: MonkeyPatch) -> None:
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
    async def test_element_click_operation_occurs_inside_tab_lock(self, monkeypatch: MonkeyPatch) -> None:
        from pydoll_mcp_server.tools import elements as element_tools

        lock_probe = _LockProbe()
        element = _FakeElement(lock_probe)

        async def resolve_element(tab_info: object, element_id: str) -> _FakeElement:
            return element

        monkeypatch.setattr(element_tools, 'tab_operation_lock', lock_probe.lock)
        monkeypatch.setattr(element_tools, 'get_registry', lambda: _FakeRegistry())
        monkeypatch.setattr(
            element_tools,
            'resolve_element',
            resolve_element,
        )

        result = await element_tools.element_click('client-1', 'tab-1', 'el-1')

        assert result['success'] is True
        assert lock_probe.events == [('enter', 'tab-1'), ('exit', 'tab-1')]
        assert element.calls == ["this.scrollIntoView({block:'center'}); return true;", 'click']

    @pytest.mark.asyncio
    async def test_storage_set_operation_occurs_inside_tab_lock(self, monkeypatch: MonkeyPatch) -> None:
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
    async def test_cookies_set_operation_occurs_inside_tab_lock(self, monkeypatch: MonkeyPatch) -> None:
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
    async def test_cookies_set_operation_occurs_inside_browser_lock(self, monkeypatch: MonkeyPatch) -> None:
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
