"""Tests for generic upload trigger orchestration."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydoll.browser.tab import Tab

from pydoll_mcp_server.json_types import JsonObject, get_array, get_string, require_json_object

pytestmark = pytest.mark.unit


class _FakeElement:
    def __init__(self, surface: JsonObject, verification: JsonObject | None = None) -> None:
        self.surface = surface
        self.verification = verification or {'upload_confirmed': True, 'filename_visible': True}
        self.clicked = False

    async def execute_script(self, script: str, *, return_by_value: bool | None = None) -> JsonObject:
        if 'file_input_count' in script:
            return {'result': {'result': {'value': self.surface}}}
        return {'result': {'result': {'value': self.verification}}}

    async def click(self) -> None:
        self.clicked = True


def _configure_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('PYDOLL_MCP_RUNTIME_DIR', str(tmp_path))
    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    from pydoll_mcp_server.config import get_config

    get_config.cache_clear()
    artifact = tmp_path / 'artifacts' / 'client'
    artifact.mkdir(parents=True, exist_ok=True)
    resume = artifact / 'resume.pdf'
    resume.write_bytes(b'%PDF-1.4 fixture')
    return resume


@pytest.mark.asyncio
async def test_upload_files_from_trigger_uses_unique_direct_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pydoll_mcp_server.tools import upload_trigger, upload_trigger_helpers

    resume = _configure_runtime(monkeypatch, tmp_path)
    trigger = _FakeElement({'file_input_count': 1, 'trigger_is_file_input': False})
    tab_info = SimpleNamespace(pydoll_tab=object())
    browser_info = SimpleNamespace(headless=True, browser_process_id=None)

    def resolve_tab_with_browser(client_id: str, tab_id: str) -> tuple[SimpleNamespace, SimpleNamespace]:
        return tab_info, browser_info

    registry = SimpleNamespace(resolve_tab_with_browser=resolve_tab_with_browser)
    upload = AsyncMock(return_value={'success': True, 'accepted': []})
    find = AsyncMock(return_value={'success': True, 'element_id': 'input-id'})

    monkeypatch.setattr(upload_trigger, 'get_registry', lambda: registry)
    monkeypatch.setattr(upload_trigger, 'resolve_element', AsyncMock(return_value=trigger))
    monkeypatch.setattr(upload_trigger_helpers, 'element_find', find)
    monkeypatch.setattr(upload_trigger_helpers, 'upload_files', upload)

    result = await upload_trigger.upload_files_from_trigger(
        'client',
        'tab',
        'trigger-id',
        [str(resume)],
    )

    assert result['success'] is True
    assert result['strategy_used'] == 'direct_input'
    assert result['native_dialog_used'] is False
    upload.assert_awaited_once()
    assert upload.await_args is not None
    assert upload.await_args.args[2] == 'input-id'


@pytest.mark.asyncio
async def test_upload_files_from_trigger_rejects_path_outside_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pydoll_mcp_server.tools import upload_trigger

    _configure_runtime(monkeypatch, tmp_path)
    outside = tmp_path.parent / 'outside-resume.pdf'
    outside.write_bytes(b'%PDF-1.4 fixture')

    result = await upload_trigger.upload_files_from_trigger(
        'client',
        'tab',
        'trigger-id',
        [str(outside)],
    )

    assert result['error_code'] == 'PERMISSION_DENIED'
    assert result['recovery_hint'] == 'Use artifact_prepare_upload or configure an explicit upload allowlist.'


@pytest.mark.asyncio
async def test_intercept_result_accepts_backend_node(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.tools import upload_trigger

    observation = upload_trigger.ChooserObservation(event_seen=True, backend_node_id=42)

    @asynccontextmanager
    async def fake_interceptor(tab: Tab, paths: list[str]) -> AsyncGenerator[upload_trigger.ChooserObservation, None]:
        yield observation

    monkeypatch.setattr(upload_trigger, '_file_chooser_interceptor', fake_interceptor)
    monkeypatch.setattr(upload_trigger, '_click_trigger', AsyncMock(return_value={'success': True, 'clicked': True}))

    tab = object.__new__(Tab)
    result = await upload_trigger.upload_with_intercept(tab, _FakeElement({}), ['resume.pdf'], 1000)

    assert result['success'] is True
    assert result['strategy_used'] == 'chooser_intercept'


@pytest.mark.asyncio
async def test_intercept_result_identifies_file_system_access_picker(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.tools import upload_trigger

    observation = upload_trigger.ChooserObservation(event_seen=True, error_reason='file_system_access_picker')

    @asynccontextmanager
    async def fake_interceptor(tab: Tab, paths: list[str]) -> AsyncGenerator[upload_trigger.ChooserObservation, None]:
        yield observation

    monkeypatch.setattr(upload_trigger, '_file_chooser_interceptor', fake_interceptor)
    monkeypatch.setattr(upload_trigger, '_click_trigger', AsyncMock(return_value={'success': True, 'clicked': True}))

    tab = object.__new__(Tab)
    result = await upload_trigger.upload_with_intercept(tab, _FakeElement({}), ['resume.pdf'], 1000)

    assert result['error_code'] == 'UNSUPPORTED'
    details = result.get('details', {})
    assert isinstance(details, dict)
    assert details['reason'] == 'file_system_access_picker'
    assert details['backend_node_id_available'] is False


@pytest.mark.asyncio
async def test_auto_falls_back_to_desktop_only_for_file_system_access_picker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pydoll_mcp_server.tools import upload_trigger

    resume = _configure_runtime(monkeypatch, tmp_path)
    trigger = _FakeElement({'file_input_count': 0, 'local_file_input_count': 0})
    tab_info = SimpleNamespace(pydoll_tab=SimpleNamespace(bring_to_front=AsyncMock()))
    browser_info = _FakeBrowser(headless=False, browser_process_id=123)

    def resolve_tab_with_browser(client_id: str, tab_id: str) -> tuple[SimpleNamespace, _FakeBrowser]:
        return tab_info, browser_info

    registry = SimpleNamespace(resolve_tab_with_browser=resolve_tab_with_browser)
    monkeypatch.setattr(upload_trigger, 'get_registry', lambda: registry)
    monkeypatch.setattr(upload_trigger, 'resolve_element', AsyncMock(return_value=trigger))
    monkeypatch.setattr(
        upload_trigger,
        'upload_with_intercept',
        AsyncMock(
            return_value={
                'success': False,
                'error_code': 'UNSUPPORTED',
                'details': {'reason': 'file_system_access_picker'},
            }
        ),
    )

    def native_picker_available(_browser: object) -> bool:
        return True

    monkeypatch.setattr(upload_trigger, 'native_picker_is_available', native_picker_available)
    monkeypatch.setattr(
        upload_trigger,
        'focus_native_browser_window',
        AsyncMock(return_value={'success': True, 'browser_window_focused': True}),
    )
    monkeypatch.setattr(upload_trigger, 'native_picker_dialog_present', AsyncMock(return_value=False))
    monkeypatch.setattr(upload_trigger, '_click_trigger', AsyncMock(return_value={'success': True, 'clicked': True}))
    monkeypatch.setattr(
        upload_trigger,
        'select_native_file',
        AsyncMock(
            return_value={
                'success': True,
                'filename': resume.name,
                'native_dialog_used': True,
            }
        ),
    )

    result = await upload_trigger.upload_files_from_trigger(
        'client',
        'tab',
        'trigger-id',
        [str(resume)],
    )

    assert result['success'] is True
    assert result['strategy_requested'] == 'auto'
    assert result['strategy_used'] == 'desktop_picker'
    attempts = get_array(result, 'strategy_attempts', [])
    first_attempt: JsonObject = require_json_object(attempts[0], 'first upload strategy attempt')
    assert get_string(first_attempt, 'strategy_requested') == 'auto'


class _FakeBrowser:
    headless: bool
    browser_process_id: int | None

    def __init__(self, headless: bool, browser_process_id: int | None) -> None:
        self.headless = headless
        self.browser_process_id = browser_process_id


@pytest.mark.asyncio
async def test_desktop_strategy_does_not_click_headless_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydoll_mcp_server.tools import upload_trigger

    trigger = _FakeElement({})
    monkeypatch.setattr(
        upload_trigger,
        'select_native_file',
        AsyncMock(
            return_value={
                'error_code': 'UNSUPPORTED',
                'details': {'reason': 'native_picker_requires_visible_browser'},
            }
        ),
    )
    click = AsyncMock()
    monkeypatch.setattr(upload_trigger, '_click_trigger', click)

    result = await upload_trigger.upload_with_desktop(
        object.__new__(Tab),
        _FakeBrowser(headless=True, browser_process_id=None),
        trigger,
        'resume.pdf',
        1000,
    )

    assert result['error_code'] == 'UNSUPPORTED'
    click.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_result_reports_explicit_page_rejection() -> None:
    from pydoll_mcp_server.tools.upload_trigger_helpers import finish_upload_result

    trigger = _FakeElement(
        {},
        verification={
            'failure_detected': True,
            'failure_text': 'Upload failed',
            'status_text': 'Upload failed',
            'upload_confirmed': False,
        },
    )
    result = await finish_upload_result(
        trigger,
        {'success': True, 'strategy_used': 'desktop_picker'},
        ['resume.pdf'],
        1000,
    )

    assert result['success'] is False
    assert result['error_code'] == 'EXECUTION_ERROR'
    details = result.get('details', {})
    assert isinstance(details, dict)
    assert details['reason'] == 'native_file_rejected_by_page'
