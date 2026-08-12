"""Unit tests for live browser tab reconciliation and tab limits."""

from __future__ import annotations

import asyncio
from typing import cast

import pytest
from pydoll.browser.chromium.base import Browser
from pydoll.browser.tab import Tab

from pydoll_mcp_server.browser.models import ProfileInfo, ProfileMode
from pydoll_mcp_server.browser.registry import BrowserRegistry
from pydoll_mcp_server.browser.tab_reconciliation import TabSyncResult
from tests.typing_helpers import object_at

pytestmark = [pytest.mark.unit]


class FakeTab:
    def __init__(self, target_id: str) -> None:
        self.target_id = target_id


class FakeBrowser:
    def __init__(self, tabs: list[FakeTab]) -> None:
        self.tabs = tabs

    async def get_opened_tabs(self) -> list[FakeTab]:
        return list(self.tabs)

    async def new_tab(self, url: str = '') -> FakeTab:
        tab = FakeTab(f'target-{len(self.tabs) + 1}')
        self.tabs.append(tab)
        return tab


def _registry_with_browser(tabs: list[FakeTab]) -> tuple[BrowserRegistry, FakeBrowser, str]:
    registry = BrowserRegistry()
    browser = FakeBrowser(tabs)
    profile = ProfileInfo(
        profile_id='profile-test',
        client_id='client-test',
        mode=ProfileMode.PERSISTENT,
        path='C:/profile-test',
    )
    info = registry.register_browser('client-test', cast(Browser, browser), profile)
    return registry, browser, info.browser_id


async def _sync_with_fakes(
    monkeypatch: pytest.MonkeyPatch,
    registry: BrowserRegistry,
    browser: FakeBrowser,
    browser_id: str,
) -> TabSyncResult:
    import pydoll_mcp_server.browser.tab_reconciliation as reconciliation

    async def opened_tabs(current: Browser) -> list[Tab]:
        return cast(list[Tab], await browser.get_opened_tabs())

    def target_id(tab: Tab) -> str:
        return cast(FakeTab, tab).target_id

    async def empty_url(tab: Tab) -> str:
        return ''

    async def empty_title(tab: Tab) -> str:
        return ''

    monkeypatch.setattr(reconciliation, 'get_registry', lambda: registry)
    monkeypatch.setattr(reconciliation, 'get_opened_tabs', opened_tabs)
    monkeypatch.setattr(reconciliation, 'get_tab_target_id', target_id)
    monkeypatch.setattr(reconciliation, 'get_tab_url', empty_url)
    monkeypatch.setattr(reconciliation, 'get_tab_title', empty_title)
    return await reconciliation.sync_browser_tabs('client-test', browser_id)


def test_sync_discovers_all_live_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    tabs = [FakeTab(f'target-{index}') for index in range(1, 7)]
    registry, browser, browser_id = _registry_with_browser(tabs)
    registry.register_tab('client-test', browser_id, cast(Tab, tabs[0]), target_id='target-1')

    result = asyncio.run(_sync_with_fakes(monkeypatch, registry, browser, browser_id))

    assert result.actual_count == 6
    assert result.added == 5
    assert result.managed_count == 6
    assert len(registry.list_tabs('client-test', browser_id)) == 6


def test_sync_is_idempotent_and_removes_closed_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    tabs = [FakeTab('target-1'), FakeTab('target-2')]
    registry, browser, browser_id = _registry_with_browser(tabs)
    registry.register_tab('client-test', browser_id, cast(Tab, tabs[0]), target_id='target-1')

    first = asyncio.run(_sync_with_fakes(monkeypatch, registry, browser, browser_id))
    second = asyncio.run(_sync_with_fakes(monkeypatch, registry, browser, browser_id))
    browser.tabs = [tabs[0]]
    third = asyncio.run(_sync_with_fakes(monkeypatch, registry, browser, browser_id))

    assert first.added == 1
    assert second.added == 0
    assert second.removed == 0
    assert third.removed == 1
    assert [tab.target_id for tab in registry.list_tabs('client-test', browser_id)] == ['target-1']


def test_tab_new_rejects_sixth_live_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    import pydoll_mcp_server.tools.tab_advanced as tab_tools

    tabs = [FakeTab(f'target-{index}') for index in range(1, 6)]
    registry, browser, browser_id = _registry_with_browser(tabs)
    monkeypatch.setattr(tab_tools, 'get_registry', lambda: registry)
    monkeypatch.setattr(
        tab_tools,
        'sync_browser_tabs',
        _full_sync_for_tabs,
    )

    result = asyncio.run(tab_tools.tab_new('client-test', browser_id))

    assert result['error_code'] == 'TAB_LIMIT_REACHED'
    assert len(browser.tabs) == 5


async def _full_sync_for_tabs(client_id: str, current_browser_id: str) -> TabSyncResult:
    return TabSyncResult(5, 5, 0, 0, 0, True, 1.0)


def test_tab_close_timeout_keeps_registry_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    import pydoll_mcp_server.tools.tabs as tab_tools

    tabs = [FakeTab('target-1'), FakeTab('target-2')]
    registry, browser, browser_id = _registry_with_browser(tabs)
    tab_info = registry.register_tab('client-test', browser_id, cast(Tab, tabs[0]), target_id='target-1')
    registry.register_tab('client-test', browser_id, cast(Tab, tabs[1]), target_id='target-2')
    monkeypatch.setattr(tab_tools, 'get_registry', lambda: registry)
    monkeypatch.setattr(tab_tools, 'sync_browser_tabs', _sync_two_tabs)
    monkeypatch.setattr(tab_tools, 'close_tab', _close_noop)

    async def opened_tabs(current: Browser) -> list[Tab]:
        return cast(list[Tab], await browser.get_opened_tabs())

    def target_id(tab: Tab) -> str:
        return cast(FakeTab, tab).target_id

    monkeypatch.setattr(tab_tools, 'get_opened_tabs', opened_tabs)
    monkeypatch.setattr(tab_tools, 'get_tab_target_id', target_id)
    monkeypatch.setattr(tab_tools, 'tab_has_dialog', _false_dialog)

    result = asyncio.run(tab_tools.tab_close('client-test', tab_info.tab_id))

    assert result['error_code'] == 'TIMEOUT'
    assert object_at(result, 'details')['confirmed_closed'] is False
    assert registry.get_tab('client-test', tab_info.tab_id).close_pending is True


def test_tab_close_blocks_only_managed_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    import pydoll_mcp_server.tools.tabs as tab_tools

    tabs = [FakeTab('target-1')]
    registry, _browser, browser_id = _registry_with_browser(tabs)
    tab_info = registry.register_tab('client-test', browser_id, cast(Tab, tabs[0]), target_id='target-1')
    monkeypatch.setattr(tab_tools, 'get_registry', lambda: registry)
    monkeypatch.setattr(tab_tools, 'sync_browser_tabs', _sync_noop)
    monkeypatch.setattr(tab_tools, '_dialog_present', _false_dialog)

    result = asyncio.run(tab_tools.tab_close('client-test', tab_info.tab_id))

    assert result['error_code'] == 'TIMEOUT'
    details = object_at(result, 'details')
    assert details['one_tab_safety'] is True
    assert details['close_attempted'] is False
    assert registry.get_tab('client-test', tab_info.tab_id).one_tab_safety_blocked is True


def test_tab_close_dialog_keeps_registry_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    import pydoll_mcp_server.tools.tabs as tab_tools

    tabs = [FakeTab('target-1')]
    registry, _browser, browser_id = _registry_with_browser(tabs)
    tab_info = registry.register_tab('client-test', browser_id, cast(Tab, tabs[0]), target_id='target-1')
    monkeypatch.setattr(tab_tools, 'get_registry', lambda: registry)
    monkeypatch.setattr(tab_tools, 'sync_browser_tabs', _sync_noop)
    monkeypatch.setattr(tab_tools, '_dialog_present', _true_dialog)

    result = asyncio.run(tab_tools.tab_close('client-test', tab_info.tab_id))

    assert result['error_code'] == 'DIALOG_PRESENT'
    assert registry.get_tab('client-test', tab_info.tab_id).close_pending is True


def test_repeated_close_after_confirmed_close_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    tabs = [FakeTab('target-1')]
    registry, _browser, browser_id = _registry_with_browser(tabs)
    tab_info = registry.register_tab('client-test', browser_id, cast(Tab, tabs[0]), target_id='target-1')
    registry.mark_tab_closed('client-test', tab_info.tab_id)
    registry.remove_tab('client-test', tab_info.tab_id)

    import pydoll_mcp_server.tools.tabs as tab_tools

    monkeypatch.setattr(tab_tools, 'get_registry', lambda: registry)
    result = asyncio.run(tab_tools.tab_close('client-test', tab_info.tab_id))

    assert result == {
        'success': True,
        'tab_id': tab_info.tab_id,
        'closed': True,
        'already_closed': True,
    }


async def _sync_noop(client_id: str, browser_id: str) -> TabSyncResult:
    return TabSyncResult(1, 1, 0, 0, 0, True, 1.0)


async def _sync_two_tabs(client_id: str, browser_id: str) -> TabSyncResult:
    return TabSyncResult(2, 2, 0, 0, 0, True, 1.0)


async def _close_noop(tab: object) -> None:
    return None


async def _false_dialog(tab: object) -> bool:
    return False


async def _true_dialog(tab: object) -> bool:
    return True
