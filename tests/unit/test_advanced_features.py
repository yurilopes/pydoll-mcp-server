"""Focused contracts for the v0.2 agent-friendly tools."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, patch

from pydoll_mcp_server.browser.operations import OperationManager
from pydoll_mcp_server.browser.snapshots import SnapshotManager
from pydoll_mcp_server.browser.watches import WatchManager
from pydoll_mcp_server.tools.element_advanced import element_check, element_get_state
from pydoll_mcp_server.tools.page_advanced import page_diff


def test_snapshot_manager_isolates_clients_and_bounds_retention() -> None:
    manager = SnapshotManager(per_tab_limit=2)
    first = manager.store('a', 'tab', {'text': 'one'})
    manager.store('a', 'tab', {'text': 'two'})
    manager.store('a', 'tab', {'text': 'three'})
    try:
        manager.get('a', 'tab', first)
    except Exception as exc:
        assert exc.error_code.value == 'RESOURCE_NOT_FOUND'
    else:
        raise AssertionError('Old snapshot should have been evicted')


def test_watch_manager_isolates_clients() -> None:
    manager = WatchManager()
    watch = manager.create('a', 'tab', 'popup')
    try:
        manager.get('b', watch.watch_id, 'popup')
    except Exception as exc:
        assert exc.error_code.value == 'RESOURCE_NOT_FOUND'
    else:
        raise AssertionError('Cross-client watch access should fail')


def test_operation_manager_cancels_only_owned_operation() -> None:
    async def run() -> None:
        manager = OperationManager()

        async def slow() -> None:
            await asyncio.sleep(10)

        task = asyncio.create_task(manager.run('a', 'op', slow()))
        await asyncio.sleep(0)
        assert manager.cancel('b', 'op') is False
        assert manager.cancel('a', 'op') is True
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())


def test_element_state_redacts_password_value() -> None:
    async def run() -> None:
        element = AsyncMock()
        element.execute_script.return_value = {'result': {'result': {'value': {
            'visible': True, 'enabled': True, 'value': 'secret', 'type': 'password',
        }}}}
        with patch(
            'pydoll_mcp_server.tools.element_advanced._get',
            AsyncMock(return_value=element),
        ):
            result = await element_get_state('client', 'tab', 'element')
        assert result['state']['value'] == '[REDACTED]'

    asyncio.run(run())


def test_element_check_is_idempotent_scripted_mutation() -> None:
    async def run() -> None:
        with patch(
            'pydoll_mcp_server.tools.element_advanced._mutate',
            AsyncMock(return_value={'success': True, 'checked': {'checked': True}}),
        ) as mutate:
            result = await element_check('client', 'tab', 'element')
        assert result['success'] is True
        assert 'this.checked!==' in mutate.await_args.args[3]

    asyncio.run(run())


def test_page_diff_reports_added_and_removed_nodes() -> None:
    async def run() -> None:
        manager = SnapshotManager()
        old_id = manager.store('client', 'tab', {'url': 'a', 'title': 'a', 'text': 'old', 'nodes': [{'tag': 'a'}]})
        with (
            patch('pydoll_mcp_server.tools.page_advanced.get_snapshot_manager', return_value=manager),
            patch('pydoll_mcp_server.tools.page_advanced.page_snapshot', AsyncMock(return_value={
                'success': True, 'snapshot_id': 'new', 'url': 'b', 'title': 'b',
                'text': 'new', 'nodes': [{'tag': 'button'}],
            })),
        ):
            result = await page_diff('client', 'tab', old_id)
        assert result['url_changed'] is True
        assert result['added'][0]['tag'] == 'button'
        assert result['removed'][0]['tag'] == 'a'

    asyncio.run(run())


def test_tool_catalog_contains_new_agent_friendly_tools() -> None:
    from pydoll_mcp_server.tool_catalog import TOOLS

    names = {tool.__name__ for tool in TOOLS}
    expected = {
        'tab_new', 'element_get_state', 'page_snapshot', 'page_diff',
        'operation_cancel', 'console_enable', 'popup_prepare', 'download_prepare',
        'page_print_pdf', 'tab_health_check', 'tab_recreate',
    }
    assert expected <= names
