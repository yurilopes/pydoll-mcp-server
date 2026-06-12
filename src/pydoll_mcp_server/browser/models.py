"""Browser, tab, window, profile and context models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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

    def summary(self) -> dict[str, Any]:
        return {
            'profile_id': self.profile_id,
            'mode': self.mode.value,
            'is_locked': self.is_locked,
        }


@dataclass
class WindowInfo:
    window_id: str
    browser_id: str
    bounds: dict[str, int] = field(default_factory=dict)
    state: str = 'normal'

    def summary(self) -> dict[str, Any]:
        return {
            'window_id': self.window_id,
            'browser_id': self.browser_id,
            'bounds': self.bounds,
            'state': self.state,
        }


@dataclass
class TabInfo:
    tab_id: str
    browser_id: str
    client_id: str
    url: str = ''
    title: str = ''
    health: ResourceHealth = ResourceHealth.HEALTHY
    document_generation: int = 0
    _pydoll_tab: Any = field(default=None, repr=False)

    def summary(self) -> dict[str, Any]:
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
    profile: ProfileInfo | None = None
    health: ResourceHealth = ResourceHealth.HEALTHY
    headless: bool = False
    tabs: dict[str, TabInfo] = field(default_factory=dict)
    windows: dict[str, WindowInfo] = field(default_factory=dict)
    _pydoll_browser: Any = field(default=None, repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            'browser_id': self.browser_id,
            'client_id': self.client_id,
            'headless': self.headless,
            'health': self.health.value,
            'tabs': len(self.tabs),
            'profile': self.profile.summary() if self.profile else None,
        }


@dataclass
class ClientSession:
    client_id: str
    browsers: dict[str, BrowserInfo] = field(default_factory=dict)
    created_at: float = 0.0

    def summary(self) -> dict[str, Any]:
        return {
            'client_id': self.client_id,
            'browsers': len(self.browsers),
        }
