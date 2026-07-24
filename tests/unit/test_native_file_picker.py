"""Tests for the Windows native file picker boundary."""

from __future__ import annotations

import sys

import pytest

from pydoll_mcp_server.browser import native_file_picker

pytestmark = pytest.mark.unit


class _FakeBrowser:
    headless: bool
    browser_process_id: int | None

    def __init__(self, headless: bool = False, browser_process_id: int | None = 123) -> None:
        self.headless = headless
        self.browser_process_id = browser_process_id


class _FakeEdit:
    def __init__(self) -> None:
        self.value = ''

    def automation_id(self) -> str:
        return '1148'

    def is_enabled(self) -> bool:
        return True

    def is_visible(self) -> bool:
        return True

    def set_edit_text(self, value: str) -> None:
        self.value = value


class _FakeDialog:
    def __init__(self, process_id: int, close_on_invoke: bool = True) -> None:
        self._process_id = process_id
        self._visible = True
        self.edit = _FakeEdit()
        self.button = _FakeButton(self, close_on_invoke)

    def process_id(self) -> int:
        return self._process_id

    def is_visible(self) -> bool:
        return self._visible

    def class_name(self) -> str:
        return '#32770'

    def descendants(self, control_type: str) -> list[object]:
        if control_type == 'Edit':
            return [self.edit]
        if control_type == 'Button':
            return [self.button]
        return []

    def close(self) -> None:
        self._visible = False


class _FakeButton:
    def __init__(self, dialog: _FakeDialog, close_on_invoke: bool) -> None:
        self.dialog = dialog
        self.close_on_invoke = close_on_invoke

    def automation_id(self) -> str:
        return '1'

    def window_text(self) -> str:
        return 'Open'

    def invoke(self) -> None:
        if self.close_on_invoke:
            self.dialog.close()


class _FakeDesktop:
    def __init__(self, dialog: _FakeDialog) -> None:
        self.dialog = dialog

    def windows(self, visible_only: bool = True) -> list[object]:
        return [self.dialog] if self.dialog.is_visible() else []


@pytest.mark.asyncio
async def test_select_native_file_uses_owned_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = _FakeDialog(123)
    desktop = _FakeDesktop(dialog)
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(native_file_picker, '_create_desktop', lambda: desktop)

    result = await native_file_picker.select_native_file(_FakeBrowser(), r'C:\uploads\resume.pdf', timeout_ms=1000)

    assert result['success'] is True
    assert result['native_dialog_used'] is True
    assert result['filename'] == 'resume.pdf'
    assert dialog.edit.value == r'C:\uploads\resume.pdf'
    assert dialog.is_visible() is False


@pytest.mark.asyncio
async def test_select_native_file_rejects_unowned_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    desktop = _FakeDesktop(_FakeDialog(999))
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(native_file_picker, '_create_desktop', lambda: desktop)

    result = await native_file_picker.select_native_file(_FakeBrowser(), r'C:\uploads\resume.pdf', timeout_ms=100)

    assert result['error_code'] == 'UNSUPPORTED'
    details = result.get('details', {})
    assert isinstance(details, dict)
    assert details['reason'] == 'native_picker_window_not_owned'


@pytest.mark.asyncio
async def test_select_native_file_refuses_headless_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, 'platform', 'win32')

    def fail_if_called() -> object:
        raise AssertionError('desktop adapter must not load for headless browsers')

    monkeypatch.setattr(native_file_picker, '_create_desktop', fail_if_called)
    result = await native_file_picker.select_native_file(
        _FakeBrowser(headless=True),
        r'C:\uploads\resume.pdf',
    )

    assert result['error_code'] == 'UNSUPPORTED'
    details = result.get('details', {})
    assert isinstance(details, dict)
    assert details['reason'] == 'native_picker_requires_visible_browser'


@pytest.mark.asyncio
async def test_select_native_file_closes_validated_dialog_after_close_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = _FakeDialog(123, close_on_invoke=False)
    desktop = _FakeDesktop(dialog)
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(native_file_picker, '_create_desktop', lambda: desktop)

    result = await native_file_picker.select_native_file(_FakeBrowser(), r'C:\uploads\resume.pdf', timeout_ms=100)

    assert result['error_code'] == 'TIMEOUT'
    assert dialog.is_visible() is False
