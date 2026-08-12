"""Reconcile the MCP tab registry with Pydoll's live browser targets."""

from __future__ import annotations

import time
from dataclasses import dataclass

from pydoll.browser.tab import Tab
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.models import ResourceHealth
from pydoll_mcp_server.browser.pydoll_compat import (
    get_opened_tabs,
    get_tab_target_id,
    get_tab_title,
    get_tab_url,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.logging import get_logger


@dataclass(frozen=True)
class TabSyncResult:
    actual_count: int
    managed_count: int
    added: int
    removed: int
    stale: int
    reconciled: bool
    last_sync_at: float
    sync_error: str = ''

    @property
    def untracked_count(self) -> int:
        return self.added

    def summary(self, max_tabs: int) -> JsonObject:
        sync: JsonObject = {
            'added': self.added,
            'removed': self.removed,
            'stale': self.stale,
        }
        result: JsonObject = {
            'actual_count': self.actual_count,
            'managed_count': self.managed_count,
            'untracked_count': self.untracked_count,
            'stale_registry_count': self.stale,
            'max_tabs': max_tabs,
            'limit_exceeded': self.actual_count > max_tabs,
            'reconciled': self.reconciled,
            'last_sync_at': self.last_sync_at,
            'last_sync_error': self.sync_error,
            'sync': sync,
        }
        if self.sync_error:
            result['sync_error'] = self.sync_error
            result['partial'] = True
        return result


async def sync_browser_tabs(client_id: str, browser_id: str) -> TabSyncResult:
    """Make the registry reflect the live page targets for one browser."""

    registry = get_registry()
    logger = get_logger()
    browser_info = registry.get_browser(client_id, browser_id)
    started_at = time.time()
    known_tabs = registry.list_tabs(client_id, browser_id)
    try:
        live_tabs = await get_opened_tabs(browser_info.pydoll_browser)
    except (AttributeError, OSError, PydollException, RuntimeError, TimeoutError) as exc:
        for known_tab in known_tabs:
            known_tab.last_sync_at = started_at
            known_tab.last_sync_error = str(exc)
            known_tab.health = ResourceHealth.DEGRADED
        return TabSyncResult(
            actual_count=len(known_tabs),
            managed_count=len(known_tabs),
            added=0,
            removed=0,
            stale=0,
            reconciled=False,
            last_sync_at=started_at,
            sync_error=str(exc),
        )

    live_by_target: dict[str, Tab] = {}
    target_errors = 0
    for tab in live_tabs:
        target_id = get_tab_target_id(tab)
        if target_id:
            live_by_target[target_id] = tab
        else:
            target_errors += 1
    existing_by_target = {tab.target_id: tab for tab in known_tabs if tab.target_id}
    added = 0
    metadata_errors: list[str] = []

    for target_id, pydoll_tab in live_by_target.items():
        existing = existing_by_target.get(target_id)
        if existing is None:
            try:
                url, title = await _read_metadata(pydoll_tab)
            except (AttributeError, OSError, PydollException, RuntimeError) as exc:
                url, title = '', ''
                metadata_errors.append(str(exc))
            registry.register_tab(
                client_id,
                browser_id,
                pydoll_tab,
                target_id=target_id,
                url=url,
                title=title,
                discovered=True,
            )
            discovered_tab = registry.find_tab_by_target(client_id, browser_id, target_id)
            if discovered_tab is not None:
                discovered_tab.last_sync_at = started_at
            added += 1
            logger.info(f'Discovered browser tab target={target_id} browser={browser_id}')
            continue
        existing.pydoll_tab = pydoll_tab
        existing.health = ResourceHealth.HEALTHY
        existing.last_sync_at = started_at
        existing.last_sync_error = ''
        try:
            existing.url, existing.title = await _read_metadata(pydoll_tab)
        except (AttributeError, OSError, PydollException, RuntimeError) as exc:
            metadata_errors.append(str(exc))
            existing.last_sync_error = str(exc)

    stale_ids = [tab.tab_id for tab in known_tabs if tab.target_id and tab.target_id not in live_by_target]
    for tab_id in stale_ids:
        registry.remove_tab(client_id, tab_id)
        logger.info(f'Removed stale browser tab tab={tab_id} browser={browser_id}')

    current_tabs = registry.list_tabs(client_id, browser_id)
    errors = metadata_errors
    if target_errors:
        errors.append(f'{target_errors} live tab(s) did not expose a target id')
    return TabSyncResult(
        actual_count=len(live_tabs),
        managed_count=len(current_tabs),
        added=added,
        removed=len(stale_ids),
        stale=len(stale_ids),
        reconciled=not errors,
        last_sync_at=started_at,
        sync_error='; '.join(errors),
    )


async def _read_metadata(tab: Tab) -> tuple[str, str]:
    return await get_tab_url(tab), await get_tab_title(tab)
