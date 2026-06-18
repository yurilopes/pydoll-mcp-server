"""Central registry for browsers, tabs, and client sessions."""

from __future__ import annotations

import time

from pydoll.browser.chromium.base import Browser
from pydoll.browser.tab import Tab

from pydoll_mcp_server.browser.models import (
    BrowserInfo,
    ClientSession,
    ProfileInfo,
    ProfileMode,
    ResourceHealth,
    TabInfo,
    generate_id,
)
from pydoll_mcp_server.browser.profiles import get_profile_manager
from pydoll_mcp_server.errors import ErrorCode, ResourceState, StructuredError
from pydoll_mcp_server.json_types import JsonObject


class BrowserRegistry:
    def __init__(self) -> None:
        self._clients: dict[str, ClientSession] = {}

    def get_or_create_client(self, client_id: str) -> ClientSession:
        if client_id not in self._clients:
            self._clients[client_id] = ClientSession(
                client_id=client_id,
                created_at=time.time(),
            )
        return self._clients[client_id]

    def register_browser(
        self,
        client_id: str,
        browser: Browser,
        profile: ProfileInfo,
        headless: bool = False,
        proxy_server: str = '',
        proxy_launch_url: str = '',
        proxy_scheme: str = '',
        proxy_has_credentials: bool = False,
        proxy_bypass_list: str = '',
    ) -> BrowserInfo:
        client = self.get_or_create_client(client_id)
        browser_id = generate_id('br')
        info = BrowserInfo(
            browser_id=browser_id,
            client_id=client_id,
            profile=profile,
            headless=headless,
            proxy_server=proxy_server,
            proxy_launch_url=proxy_launch_url,
            proxy_scheme=proxy_scheme,
            proxy_has_credentials=proxy_has_credentials,
            proxy_bypass_list=proxy_bypass_list,
            pydoll_browser=browser,
        )
        client.browsers[browser_id] = info
        return info

    def register_tab(
        self,
        client_id: str,
        browser_id: str,
        pydoll_tab: Tab,
        url: str = '',
        title: str = '',
    ) -> TabInfo:
        client = self._clients.get(client_id)
        if not client:
            raise ValueError(f'Client {client_id} not found')
        if browser_id not in client.browsers:
            raise ValueError(f'Browser {browser_id} not found')
        tab_id = generate_id('tab')
        info = TabInfo(
            tab_id=tab_id,
            browser_id=browser_id,
            client_id=client_id,
            url=url,
            title=title,
            pydoll_tab=pydoll_tab,
        )
        client.browsers[browser_id].tabs[tab_id] = info
        return info

    def get_browser(self, client_id: str, browser_id: str) -> BrowserInfo:
        client = self._clients.get(client_id)
        if not client:
            raise error_not_found('client', client_id)
        if browser_id not in client.browsers:
            raise error_not_found('browser', browser_id)
        return client.browsers[browser_id]

    def get_tab(self, client_id: str, tab_id: str) -> TabInfo:
        for client in self._clients.values():
            if client.client_id != client_id:
                continue
            for browser in client.browsers.values():
                if tab_id in browser.tabs:
                    return browser.tabs[tab_id]
        raise error_not_found('tab', tab_id)

    def resolve_tab_with_browser(
        self,
        client_id: str,
        tab_id: str,
    ) -> tuple[TabInfo, BrowserInfo]:
        tab = self.get_tab(client_id, tab_id)
        browser = self.get_browser(client_id, tab.browser_id)
        return tab, browser

    def list_browsers(self, client_id: str) -> list[BrowserInfo]:
        client = self._clients.get(client_id)
        if not client:
            return []
        return list(client.browsers.values())

    def list_tabs(
        self,
        client_id: str,
        browser_id: str | None = None,
    ) -> list[TabInfo]:
        client = self._clients.get(client_id)
        if not client:
            return []
        tabs: list[TabInfo] = []
        for browser in client.browsers.values():
            if browser_id and browser.browser_id != browser_id:
                continue
            tabs.extend(browser.tabs.values())
        return tabs

    def list_clients(self) -> list[JsonObject]:
        return [{'client_id': cid, 'browsers': len(cs.browsers)} for cid, cs in self._clients.items()]

    def remove_browser(self, client_id: str, browser_id: str, cleanup_profile: bool = True) -> None:
        client = self._clients.get(client_id)
        if not client:
            return
        if browser_id in client.browsers:
            browser = client.browsers[browser_id]
            if browser.profile and cleanup_profile:
                profile_mgr = get_profile_manager()
                if browser.profile.mode == ProfileMode.TEMPORARY:
                    profile_mgr.cleanup_temporary(browser.profile.profile_id)
                else:
                    profile_mgr.unlock(browser.profile.profile_id)
            del client.browsers[browser_id]

    def remove_tab(self, client_id: str, tab_id: str) -> None:
        for browser in self._clients.get(client_id, ClientSession('')).browsers.values():
            if tab_id in browser.tabs:
                del browser.tabs[tab_id]
                return

    def update_tab_health(
        self,
        client_id: str,
        tab_id: str,
        health: ResourceHealth,
    ) -> None:
        try:
            tab = self.get_tab(client_id, tab_id)
            tab.health = health
        except StructuredError:
            return

    def update_browser_health(
        self,
        client_id: str,
        browser_id: str,
        health: ResourceHealth,
    ) -> None:
        try:
            browser = self.get_browser(client_id, browser_id)
            browser.health = health
        except StructuredError:
            return

    def get_pydoll_browser(self, client_id: str, browser_id: str) -> Browser:
        return self.get_browser(client_id, browser_id).pydoll_browser

    def get_pydoll_tab(self, client_id: str, tab_id: str) -> Tab:
        return self.get_tab(client_id, tab_id).pydoll_tab


def error_not_found(resource_type: str, resource_id: str) -> StructuredError:
    return StructuredError(
        error_code=ErrorCode.RESOURCE_NOT_FOUND,
        message=f'{resource_type} not found: {resource_id}',
        retryable=False,
        resource_state=ResourceState.CLOSED,
        recovery_hint=f'Verify the {resource_type}_id and ensure it belongs to your client.',
    )


_registry: BrowserRegistry | None = None


def get_registry() -> BrowserRegistry:
    global _registry
    if _registry is None:
        _registry = BrowserRegistry()
    return _registry
