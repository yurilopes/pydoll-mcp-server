"""Browser, tab, window, profile and context models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

from pydoll.browser.chromium.base import Browser
from pydoll.browser.tab import Tab

from pydoll_mcp_server.json_types import JsonObject


class ProfileMode(str, Enum):
    PERSISTENT = 'persistent'
    TEMPORARY = 'temporary'


class ResourceHealth(str, Enum):
    HEALTHY = 'healthy'
    DEGRADED = 'degraded'
    UNHEALTHY = 'unhealthy'
    CLOSED = 'closed'


def generate_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:12]}'


@dataclass
class ProfileInfo:
    profile_id: str
    client_id: str
    mode: ProfileMode
    path: str
    is_locked: bool = False
    locked_by: str = ''

    def summary(self) -> JsonObject:
        return {
            'profile_id': self.profile_id,
            'mode': self.mode.value,
            'is_locked': self.is_locked,
        }


@dataclass
class WindowInfo:
    window_id: str
    browser_id: str
    bounds: dict[str, int] = field(default_factory=lambda: {})
    state: str = 'normal'

    def summary(self) -> JsonObject:
        bounds: JsonObject = dict(self.bounds)
        return {
            'window_id': self.window_id,
            'browser_id': self.browser_id,
            'bounds': bounds,
            'state': self.state,
        }


@dataclass
class TabInfo:
    tab_id: str
    browser_id: str
    client_id: str
    pydoll_tab: Tab = field(repr=False)
    url: str = ''
    title: str = ''
    health: ResourceHealth = ResourceHealth.HEALTHY
    document_generation: int = 0

    def summary(self) -> JsonObject:
        return {
            'tab_id': self.tab_id,
            'browser_id': self.browser_id,
            'url': self.url,
            'title': self.title,
            'health': self.health.value,
        }

    def mark_navigated(self) -> None:
        self.document_generation += 1


@dataclass
class BrowserInfo:
    browser_id: str
    client_id: str
    pydoll_browser: Browser = field(repr=False)
    profile: ProfileInfo | None = None
    health: ResourceHealth = ResourceHealth.HEALTHY
    headless: bool = False
    proxy_server: str = ''
    proxy_scheme: str = ''
    proxy_has_credentials: bool = False
    proxy_bypass_list: str = ''
    tabs: dict[str, TabInfo] = field(default_factory=lambda: {})
    windows: dict[str, WindowInfo] = field(default_factory=lambda: {})

    def summary(self) -> JsonObject:
        return {
            'browser_id': self.browser_id,
            'client_id': self.client_id,
            'headless': self.headless,
            'health': self.health.value,
            'tabs': len(self.tabs),
            'profile': self.profile.summary() if self.profile else None,
            'proxy_enabled': bool(self.proxy_server),
            'proxy_scheme': self.proxy_scheme,
            'proxy_server': self.proxy_server,
            'proxy_has_credentials': self.proxy_has_credentials,
            'proxy_bypass_list': self.proxy_bypass_list,
        }


@dataclass
class ClientSession:
    client_id: str
    browsers: dict[str, BrowserInfo] = field(default_factory=lambda: {})
    created_at: float = 0.0

    def summary(self) -> JsonObject:
        return {
            'client_id': self.client_id,
            'browsers': len(self.browsers),
        }
