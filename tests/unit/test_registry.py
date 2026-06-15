"""Tests for browser registry."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydoll.browser import Chrome
from pydoll.browser.chromium.base import Browser
from pydoll.browser.tab import Tab

from pydoll_mcp_server.browser.models import (
    ProfileInfo,
    ProfileMode,
    ResourceHealth,
    generate_id,
)
from pydoll_mcp_server.browser.registry import BrowserRegistry


def _browser_handle() -> Browser:
    return Chrome()


def _tab_handle() -> Tab:
    return object.__new__(Tab)


class TestIDGeneration:
    def test_generate_browser_id(self) -> None:
        bid = generate_id('br')
        assert bid.startswith('br_')
        assert len(bid) > 3

    def test_generate_tab_id(self) -> None:
        tid = generate_id('tab')
        assert tid.startswith('tab_')

    def test_generate_unique_ids(self) -> None:
        ids = {generate_id('br') for _ in range(100)}
        assert len(ids) == 100


class TestBrowserRegistry:
    def setup_method(self) -> None:
        self.registry = BrowserRegistry()

    def test_get_or_create_client(self) -> None:
        client = self.registry.get_or_create_client('test-client')
        assert client.client_id == 'test-client'
        assert len(client.browsers) == 0

    def test_same_client_returned(self) -> None:
        c1 = self.registry.get_or_create_client('client-a')
        c2 = self.registry.get_or_create_client('client-a')
        assert c1 is c2

    def test_different_clients_isolated(self) -> None:
        self.registry.get_or_create_client('client-a')
        self.registry.get_or_create_client('client-b')
        browsers_a = self.registry.list_browsers('client-a')
        browsers_b = self.registry.list_browsers('client-b')
        assert isinstance(browsers_a, list)
        assert isinstance(browsers_b, list)

    def test_register_browser_adds_to_client(self) -> None:
        profile = ProfileInfo(
            profile_id='prof_test',
            client_id='test-client',
            mode=ProfileMode.PERSISTENT,
            path='/tmp/test-profile',
        )
        info = self.registry.register_browser(
            client_id='test-client',
            browser=_browser_handle(),
            profile=profile,
        )
        assert info.browser_id.startswith('br_')
        assert info.client_id == 'test-client'
        browsers = self.registry.list_browsers('test-client')
        assert len(browsers) == 1

    def test_register_tab(self) -> None:
        profile = ProfileInfo(
            profile_id='prof_test',
            client_id='test-client',
            mode=ProfileMode.PERSISTENT,
            path='/tmp/test',
        )
        browser_info = self.registry.register_browser(
            client_id='test-client',
            browser=_browser_handle(),
            profile=profile,
        )
        tab_info = self.registry.register_tab(
            client_id='test-client',
            browser_id=browser_info.browser_id,
            pydoll_tab=_tab_handle(),
        )
        assert tab_info.tab_id.startswith('tab_')
        assert tab_info.browser_id == browser_info.browser_id

    def test_get_browser_not_found(self) -> None:
        from pydoll_mcp_server.errors import StructuredError

        with pytest.raises(StructuredError) as exc:
            self.registry.get_browser('test-client', 'br_nonexistent')
        assert 'not found' in str(exc.value.message).lower()

    def test_get_tab_not_found(self) -> None:
        from pydoll_mcp_server.errors import StructuredError

        with pytest.raises(StructuredError) as exc:
            self.registry.get_tab('test-client', 'tab_nonexistent')
        assert 'not found' in str(exc.value.message).lower()

    def test_list_browsers_empty(self) -> None:
        browsers = self.registry.list_browsers('no-client')
        assert browsers == []

    def test_list_tabs_empty(self) -> None:
        tabs = self.registry.list_tabs('no-client')
        assert tabs == []

    def test_remove_browser_cleans_up(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            profile = ProfileInfo(
                profile_id='prof_test',
                client_id='test-client',
                mode=ProfileMode.PERSISTENT,
                path='/tmp/test',
            )
            info = self.registry.register_browser(
                client_id='test-client',
                browser=_browser_handle(),
                profile=profile,
            )
            self.registry.remove_browser('test-client', info.browser_id)
            assert self.registry.list_browsers('test-client') == []

    def test_remove_tab(self) -> None:
        profile = ProfileInfo(
            profile_id='prof_test',
            client_id='test-client',
            mode=ProfileMode.PERSISTENT,
            path='/tmp/test',
        )
        browser = self.registry.register_browser(
            client_id='test-client',
            browser=_browser_handle(),
            profile=profile,
        )
        tab = self.registry.register_tab(
            client_id='test-client',
            browser_id=browser.browser_id,
            pydoll_tab=_tab_handle(),
        )
        self.registry.remove_tab('test-client', tab.tab_id)
        tabs = self.registry.list_tabs('test-client')
        assert len(tabs) == 0

    def test_update_tab_health(self) -> None:
        profile = ProfileInfo(
            profile_id='prof_test',
            client_id='test-client',
            mode=ProfileMode.PERSISTENT,
            path='/tmp/test',
        )
        browser = self.registry.register_browser(
            client_id='test-client',
            browser=_browser_handle(),
            profile=profile,
        )
        tab = self.registry.register_tab(
            client_id='test-client',
            browser_id=browser.browser_id,
            pydoll_tab=_tab_handle(),
        )
        assert tab.health == ResourceHealth.HEALTHY
        self.registry.update_tab_health('test-client', tab.tab_id, ResourceHealth.UNHEALTHY)
        updated = self.registry.get_tab('test-client', tab.tab_id)
        assert updated.health == ResourceHealth.UNHEALTHY

    def test_list_clients(self) -> None:
        self.registry.get_or_create_client('client-a')
        self.registry.get_or_create_client('client-b')
        clients = self.registry.list_clients()
        assert len(clients) == 2

    def test_client_isolation(self) -> None:
        profile = ProfileInfo(
            profile_id='prof_a',
            client_id='client-a',
            mode=ProfileMode.PERSISTENT,
            path='/tmp/a',
        )
        info = self.registry.register_browser(
            client_id='client-a',
            browser=_browser_handle(),
            profile=profile,
        )
        from pydoll_mcp_server.errors import StructuredError

        with pytest.raises(StructuredError):
            self.registry.get_browser('client-b', info.browser_id)

    def test_tab_marks_navigated(self) -> None:
        profile = ProfileInfo(
            profile_id='prof_test',
            client_id='test-client',
            mode=ProfileMode.PERSISTENT,
            path='/tmp/test',
        )
        browser = self.registry.register_browser(
            client_id='test-client',
            browser=_browser_handle(),
            profile=profile,
        )
        tab = self.registry.register_tab(
            client_id='test-client',
            browser_id=browser.browser_id,
            pydoll_tab=_tab_handle(),
        )
        gen = tab.document_generation
        tab.mark_navigated()
        assert tab.document_generation == gen + 1
