"""Low-level, validated control operations for the Windows picker adapter."""

from __future__ import annotations

import importlib
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from functools import lru_cache

from pydoll_mcp_server.json_types import InvalidJsonValueError, JsonArray, normalize_json_value


class _UnavailablePyWinError(Exception):
    """Fallback type when the optional Windows UI dependency is absent."""


class NativePickerError(RuntimeError):
    """Expected failure while locating or operating a native picker."""

    def __init__(self, reason: str, message: str, retryable: bool = False, stage: str = '') -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.retryable = retryable
        self.stage = stage


def call_native(target: object, method_name: str, *args: object, **kwargs: object) -> object:
    """Call one validated pywinauto or Windows API method."""

    try:
        method: object = object.__getattribute__(target, method_name)
    except AttributeError as exc:
        raise NativePickerError('native_picker_unavailable', f'Native control lacks {method_name}') from exc
    if not callable(method):
        raise NativePickerError('native_picker_unavailable', f'Native control {method_name} is not callable')
    try:
        return method(*args, **kwargs)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise NativePickerError('native_picker_execution_error', str(exc), retryable=True) from exc
    except _pywin_error_type() as exc:
        raise NativePickerError('native_picker_execution_error', str(exc), retryable=True) from exc


def invoke_native_control(control: object) -> None:
    """Activate a validated picker control without targeting arbitrary foreground UI."""

    with suppress(NativePickerError):
        call_native(control, 'set_focus')
    try:
        _send_native_click(control)
        return
    except NativePickerError:
        pass
    try:
        call_native(control, 'invoke')
    except NativePickerError:
        try:
            call_native(control, 'click_input')
        except NativePickerError:
            call_native(control, 'type_keys', '{ENTER}')


def focus_owned_browser_window(browser_process_id: int, timeout_ms: int) -> bool:
    """Activate a visible controlled-browser window when Windows permits it."""

    with _com_initialized():
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            handle = _find_browser_window_handle(browser_process_id)
            if handle is not None:
                win32gui = importlib.import_module('win32gui')
                win32process = importlib.import_module('win32process')
                win32con = importlib.import_module('win32con')
                restore = _constant(win32con, 'SW_RESTORE')
                if restore is not None:
                    call_native(win32gui, 'ShowWindow', handle, restore)
                return _activate_validated_window(handle, win32gui, win32process)
            time.sleep(0.05)
    raise NativePickerError(
        'native_picker_window_not_owned',
        'The controlled browser window could not be brought to the foreground',
        retryable=True,
    )


def find_owned_browser_window(desktop: object, browser_process_id: int) -> object | None:
    """Resolve a UIA wrapper for the controlled Chrome top-level window."""

    try:
        window_factory: object = object.__getattribute__(desktop, 'window')
    except AttributeError:
        return None
    if not callable(window_factory):
        return None
    handle = _find_browser_window_handle(browser_process_id)
    if handle is None:
        return None
    specification = call_native(desktop, 'window', handle=handle)
    return call_native(specification, 'wrapper_object')


def _send_native_click(control: object) -> None:
    handle = _int_property(control, 'handle')
    if handle is None:
        raise NativePickerError('native_picker_unavailable', 'Validated picker control has no native handle')

    rectangle = call_native(control, 'rectangle')
    width = _int_result(call_native(rectangle, 'width'))
    height = _int_result(call_native(rectangle, 'height'))
    if width is None or height is None or width <= 0 or height <= 0:
        raise NativePickerError('native_picker_unavailable', 'Validated picker control has no usable bounds')

    win32api = importlib.import_module('win32api')
    win32con = importlib.import_module('win32con')
    down = _constant(win32con, 'WM_LBUTTONDOWN')
    up = _constant(win32con, 'WM_LBUTTONUP')
    left_button = _constant(win32con, 'MK_LBUTTON')
    if down is None or up is None or left_button is None:
        raise NativePickerError('native_picker_unavailable', 'Windows mouse message constants are unavailable')

    x = width // 2
    y = height // 2
    lparam = (y << 16) | x
    call_native(win32api, 'SendMessage', handle, down, left_button, lparam)
    call_native(win32api, 'SendMessage', handle, up, 0, lparam)


def _find_browser_window_handle(browser_process_id: int) -> int | None:
    win32gui = importlib.import_module('win32gui')
    win32process = importlib.import_module('win32process')
    handles: list[tuple[int, int]] = []

    def collect(handle: int, _extra: int) -> bool:
        process = call_native(win32process, 'GetWindowThreadProcessId', handle)
        normalized_process = _normalize_native_result(process)
        if len(normalized_process) != 2:
            return True
        pid = normalized_process[1]
        if not isinstance(pid, int) or isinstance(pid, bool):
            return True
        class_name = call_native(win32gui, 'GetClassName', handle)
        visible = call_native(win32gui, 'IsWindowVisible', handle)
        if pid == browser_process_id and class_name == 'Chrome_WidgetWin_1' and bool(visible):
            rectangle = call_native(win32gui, 'GetWindowRect', handle)
            area = _window_area(rectangle)
            handles.append((handle, area))
        return True

    call_native(win32gui, 'EnumWindows', collect, None)
    return max(handles, key=lambda candidate: candidate[1])[0] if handles else None


def _activate_validated_window(handle: int, win32gui: object, win32process: object) -> bool:
    """Activate one already validated window across Windows foreground-thread boundaries."""

    win32api = importlib.import_module('win32api')
    current_thread = _int_result(call_native(win32api, 'GetCurrentThreadId'))
    target_thread = _window_thread_id(win32process, handle)
    foreground = _int_result(call_native(win32gui, 'GetForegroundWindow'))
    foreground_thread = _window_thread_id(win32process, foreground) if foreground is not None else None
    if current_thread is None or target_thread is None:
        return False

    attached_threads: list[int] = []
    try:
        for thread_id in (foreground_thread, target_thread):
            if thread_id is None or thread_id == current_thread or thread_id in attached_threads:
                continue
            call_native(win32process, 'AttachThreadInput', current_thread, thread_id, True)
            attached_threads.append(thread_id)
        call_native(win32gui, 'SetForegroundWindow', handle)
        active_handle = _int_result(call_native(win32gui, 'GetForegroundWindow'))
        return active_handle == handle
    except NativePickerError:
        return False
    finally:
        for thread_id in reversed(attached_threads):
            with suppress(NativePickerError):
                call_native(win32process, 'AttachThreadInput', current_thread, thread_id, False)


def _window_thread_id(win32process: object, handle: int) -> int | None:
    result = call_native(win32process, 'GetWindowThreadProcessId', handle)
    normalized_result = _normalize_native_result(result)
    if len(normalized_result) != 2:
        return None
    thread_id = normalized_result[0]
    return thread_id if isinstance(thread_id, int) and not isinstance(thread_id, bool) else None


def _window_area(value: object) -> int:
    normalized = _normalize_native_result(value)
    if len(normalized) != 4:
        return 0
    left, top, right, bottom = normalized
    if not (
        isinstance(left, int)
        and not isinstance(left, bool)
        and isinstance(top, int)
        and not isinstance(top, bool)
        and isinstance(right, int)
        and not isinstance(right, bool)
        and isinstance(bottom, int)
        and not isinstance(bottom, bool)
    ):
        return 0
    return max(0, right - left) * max(0, bottom - top)


@contextmanager
def _com_initialized() -> Generator[None, None, None]:
    pythoncom = importlib.import_module('pythoncom')
    call_native(pythoncom, 'CoInitialize')
    try:
        yield
    finally:
        with suppress(NativePickerError):
            call_native(pythoncom, 'CoUninitialize')


@lru_cache(maxsize=1)
def _pywin_error_type() -> type[BaseException]:
    try:
        module = importlib.import_module('pywintypes')
    except ImportError:
        return _UnavailablePyWinError
    candidate: object = getattr(module, 'error', None)
    if isinstance(candidate, type) and issubclass(candidate, BaseException):
        return candidate
    return _UnavailablePyWinError


def _normalize_native_result(value: object) -> JsonArray:
    try:
        normalized = normalize_json_value(value, 'Windows API result')
    except InvalidJsonValueError:
        return []
    return normalized if isinstance(normalized, list) else []


def _int_property(target: object, name: str) -> int | None:
    try:
        value: object = object.__getattribute__(target, name)
    except AttributeError:
        return None
    return _int_result(value)


def _int_result(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _constant(target: object, name: str) -> int | None:
    try:
        value: object = object.__getattribute__(target, name)
    except AttributeError:
        return None
    return _int_result(value)


__all__ = [
    'NativePickerError',
    'call_native',
    'find_owned_browser_window',
    'focus_owned_browser_window',
    'invoke_native_control',
]
