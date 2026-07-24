"""Windows UI Automation fallback for browser-native file pickers."""

from __future__ import annotations

import asyncio
import importlib
import sys
import time
import unicodedata
from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import Protocol, TypeGuard

from pydoll_mcp_server.browser.native_file_picker_controls import (
    NativePickerError,
)
from pydoll_mcp_server.browser.native_file_picker_controls import (
    call_native as _call,
)
from pydoll_mcp_server.browser.native_file_picker_controls import (
    find_owned_browser_window as _find_owned_browser_window,
)
from pydoll_mcp_server.browser.native_file_picker_controls import (
    invoke_native_control as _invoke_control,
)
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject


class BrowserIdentity(Protocol):
    """Minimum browser identity required by the native picker boundary."""

    headless: bool
    browser_process_id: int | None


def native_picker_is_available(browser: BrowserIdentity) -> bool:
    """Return whether this browser can safely use the Windows picker adapter."""

    return sys.platform == 'win32' and not browser.headless and browser.browser_process_id is not None


async def native_picker_dialog_present(browser: BrowserIdentity, timeout_ms: int = 250) -> bool:
    """Return whether an owned native file dialog is already visible."""

    if sys.platform != 'win32' or browser.headless or browser.browser_process_id is None:
        return False
    try:
        dialog = await asyncio.to_thread(
            _find_owned_dialog,
            browser.browser_process_id,
            max(1, timeout_ms),
        )
    except (ImportError, NativePickerError, OSError, TypeError, ValueError):
        return False
    return dialog is not None


async def select_native_file(
    browser: BrowserIdentity,
    path: str,
    timeout_ms: int = 30000,
) -> JsonObject:
    """Select one file in an owned Windows common file dialog."""

    if sys.platform != 'win32':
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            'Native file picker automation is only available on Windows',
            details={'reason': 'native_picker_unavailable'},
            retryable=False,
        ).to_dict()
    if browser.headless:
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            'Native file picker automation requires a visible browser',
            details={'reason': 'native_picker_requires_visible_browser'},
            retryable=False,
        ).to_dict()
    if browser.browser_process_id is None:
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            'The browser process could not be associated with a native file picker',
            details={'reason': 'native_picker_window_not_owned'},
            retryable=False,
        ).to_dict()

    try:
        result = await asyncio.to_thread(
            _select_native_file,
            browser.browser_process_id,
            path,
            max(1, timeout_ms),
        )
    except ImportError:
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            'Windows UI Automation is not installed',
            details={'reason': 'native_picker_unavailable', 'dependency': 'pywinauto'},
            retryable=False,
            recovery_hint='Install pydoll-mcp-server[windows] in the active Python environment.',
        ).to_dict()
    except NativePickerError as exc:
        if exc.reason == 'native_picker_timeout':
            error_code = ErrorCode.TIMEOUT
        elif exc.reason == 'native_picker_execution_error':
            error_code = ErrorCode.EXECUTION_ERROR
        else:
            error_code = ErrorCode.UNSUPPORTED
        details: JsonObject = {'reason': exc.reason}
        if exc.stage:
            details['stage'] = exc.stage
        return StructuredError(
            error_code,
            exc.message,
            details=details,
            retryable=exc.retryable,
        ).to_dict()
    except (OSError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Windows native file picker failed: {exc}',
            details={'reason': 'native_picker_execution_error'},
            retryable=True,
        ).to_dict()
    return result


def _select_native_file(browser_process_id: int, path: str, timeout_ms: int) -> JsonObject:
    with _com_initialized():
        return _select_native_file_after_com(browser_process_id, path, timeout_ms)


def _select_native_file_after_com(browser_process_id: int, path: str, timeout_ms: int) -> JsonObject:
    dialog: object | None = None
    stage = 'dialog_open'
    try:
        desktop = _create_browser_surface(browser_process_id)
        deadline = time.monotonic() + timeout_ms / 1000
        dialog = _find_owned_dialog_with_desktop(desktop, browser_process_id, deadline)
        if dialog is None:
            raise NativePickerError(
                'native_picker_timeout',
                f'Owned native file picker did not appear within {timeout_ms}ms',
                retryable=True,
                stage=stage,
            )

        stage = 'file_name_field'
        edit = _find_file_name_edit(dialog)
        stage = 'set_file_name'
        with suppress(NativePickerError):
            _call(edit, 'set_focus')
        _call(edit, 'set_edit_text', path)
        stage = 'confirm_button'
        confirm = _find_confirm_button(dialog)
        stage = 'confirm_selection'
        _invoke_control(confirm)
        stage = 'dialog_close'
        _wait_for_dialog_close(dialog, desktop, browser_process_id, deadline)
    except NativePickerError as exc:
        if not exc.stage:
            exc.stage = stage
        if dialog is not None:
            _close_validated_dialog(dialog, browser_process_id)
        raise
    return {
        'success': True,
        'uploaded_via': 'desktop_picker',
        'native_dialog_used': True,
        'filename': path.rsplit('\\', 1)[-1].rsplit('/', 1)[-1],
    }


def _create_desktop() -> object:
    module = importlib.import_module('pywinauto')
    factory: object = getattr(module, 'Desktop', None)
    if not callable(factory):
        raise NativePickerError('native_picker_unavailable', 'pywinauto.Desktop is unavailable')
    return factory(backend='uia')


class _BrowserWindowDesktop:
    def __init__(self, window: object) -> None:
        self._window = window

    def windows(self, visible_only: bool = True) -> list[object]:
        return [self._window]


def _create_browser_surface(browser_process_id: int) -> object:
    desktop = _create_desktop()
    window = _find_owned_browser_window(desktop, browser_process_id)
    return _BrowserWindowDesktop(window) if window is not None else desktop


def _find_owned_dialog(browser_process_id: int, timeout_ms: int) -> object | None:
    with _com_initialized():
        desktop = _create_browser_surface(browser_process_id)
        deadline = time.monotonic() + timeout_ms / 1000
        return _find_owned_dialog_with_desktop(desktop, browser_process_id, deadline)


@contextmanager
def _com_initialized() -> Generator[None, None, None]:
    pythoncom = importlib.import_module('pythoncom')
    _call(pythoncom, 'CoInitialize')
    try:
        yield
    finally:
        with suppress(NativePickerError):
            _call(pythoncom, 'CoUninitialize')


def _find_owned_dialog_with_desktop(desktop: object, browser_process_id: int, deadline: float) -> object | None:
    unowned_dialog_seen = False
    while time.monotonic() < deadline:
        for window in _windows(desktop):
            if _window_process_id(window) == browser_process_id:
                for dialog in _owned_dialog_candidates(window):
                    if _is_visible(dialog) and _is_file_dialog(dialog):
                        return dialog
            elif _is_visible(window) and _optional_string(window, 'class_name') == '#32770':
                # Do not traverse unrelated desktop windows. Their UIA trees can block
                # while another application owns a modal dialog.
                unowned_dialog_seen = True
        time.sleep(0.05)
    if unowned_dialog_seen:
        raise NativePickerError(
            'native_picker_window_not_owned',
            'A visible native file picker could not be associated with the controlled browser',
            retryable=False,
        )
    return None


def _wait_for_dialog_close(
    dialog: object,
    desktop: object,
    browser_process_id: int,
    deadline: float,
) -> None:
    while time.monotonic() < deadline:
        if not _is_visible(dialog):
            return
        if _find_owned_dialog_with_desktop(desktop, browser_process_id, time.monotonic() + 0.05) is None:
            return
    raise NativePickerError(
        'native_picker_timeout',
        'Native file picker did not close after confirming the file',
        retryable=True,
    )


def _close_validated_dialog(dialog: object, browser_process_id: int) -> None:
    """Close only the dialog identity already validated against the browser PID."""

    if not _is_owned_by_browser(dialog, browser_process_id) or not _is_visible(dialog) or not _is_file_dialog(dialog):
        return
    try:
        _call(dialog, 'close')
    except NativePickerError:
        return


def _windows(desktop: object) -> list[object]:
    windows = _call(desktop, 'windows', visible_only=True)
    if not _is_object_list(windows):
        raise NativePickerError('native_picker_unavailable', 'pywinauto returned an invalid window list')
    return windows


def _is_file_dialog(window: object) -> bool:
    class_name = _optional_string(window, 'class_name')
    try:
        edits = _descendants(window, 'Edit')
        buttons = _descendants(window, 'Button')
    except NativePickerError:
        return False
    return class_name == '#32770' and bool(edits and buttons)


def _owned_dialog_candidates(window: object) -> list[object]:
    if _optional_string(window, 'class_name') == '#32770':
        return [window]
    try:
        return _window_descendants(window)
    except NativePickerError:
        return []


def _window_descendants(window: object) -> list[object]:
    descendants = _call(window, 'descendants')
    if not _is_object_list(descendants):
        raise NativePickerError('native_picker_unavailable', 'pywinauto returned invalid window descendants')
    return descendants


def _find_file_name_edit(dialog: object) -> object:
    edits = _descendants(dialog, 'Edit')
    for edit in edits:
        if _optional_string(edit, 'automation_id') in {'1148', '1001'}:
            return edit
    for edit in reversed(edits):
        if _is_enabled_and_visible(edit):
            return edit
    raise NativePickerError('native_picker_unavailable', 'File name field was not found in the native picker')


def _find_confirm_button(dialog: object) -> object:
    accepted = {'open', 'abrir', 'select', 'selecionar', 'choose', 'escolher'}
    split_buttons = _descendants(dialog, 'SplitButton')
    for button in split_buttons:
        if _optional_string(button, 'automation_id') == '1':
            return button
    for button in split_buttons:
        text = _normalize(_optional_string(button, 'window_text'))
        if text in accepted:
            return button
    buttons = _descendants(dialog, 'Button')
    for button in buttons:
        if _optional_string(button, 'automation_id') == '1':
            return button
    for button in buttons:
        text = _normalize(_optional_string(button, 'window_text'))
        if text in accepted:
            return button
    raise NativePickerError('native_picker_unavailable', 'Open button was not found in the native picker')


def _descendants(window: object, control_type: str) -> list[object]:
    descendants = _call(window, 'descendants', control_type=control_type)
    if not _is_object_list(descendants):
        raise NativePickerError('native_picker_unavailable', 'pywinauto returned invalid dialog controls')
    return descendants


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_owned_by_browser(dialog: object, browser_process_id: int) -> bool:
    current: object | None = dialog
    for _ in range(8):
        if current is None:
            return False
        if _window_process_id(current) == browser_process_id:
            return True
        try:
            current = _call(current, 'parent')
        except NativePickerError:
            return False
    return False


def _is_enabled_and_visible(control: object) -> bool:
    try:
        enabled = _call(control, 'is_enabled')
        visible = _call(control, 'is_visible')
    except NativePickerError:
        return False
    return enabled is True and visible is True


def _is_visible(window: object) -> bool:
    try:
        return _call(window, 'is_visible') is True
    except NativePickerError:
        return False


def _window_process_id(window: object) -> int | None:
    try:
        value = _call(window, 'process_id')
    except NativePickerError:
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_string(target: object, method_name: str) -> str:
    try:
        value = _call(target, method_name)
    except NativePickerError:
        return ''
    return value if isinstance(value, str) else ''


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize('NFD', value.casefold())
    return ''.join(char for char in decomposed if unicodedata.category(char) != 'Mn').strip()


__all__ = ['native_picker_dialog_present', 'native_picker_is_available', 'select_native_file']
