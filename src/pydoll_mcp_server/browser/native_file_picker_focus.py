"""Safe foreground activation for the controlled browser window."""

from __future__ import annotations

import asyncio
import sys
from typing import Protocol

from pydoll_mcp_server.browser.native_file_picker_controls import (
    NativePickerError,
    focus_owned_browser_window,
)
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject


class BrowserIdentity(Protocol):
    """Minimum browser identity required by the foreground boundary."""

    headless: bool
    browser_process_id: int | None


async def focus_native_browser_window(browser: BrowserIdentity, timeout_ms: int = 5000) -> JsonObject:
    """Bring only the controlled browser window to the foreground before a native click."""

    if sys.platform != 'win32' or browser.headless:
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            'Native picker automation requires a visible browser',
            details={'reason': 'native_picker_requires_visible_browser'},
            retryable=False,
        ).to_dict()
    if browser.browser_process_id is None:
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            'The browser process could not be associated with its native window',
            details={'reason': 'native_picker_window_not_owned'},
            retryable=False,
        ).to_dict()
    try:
        focused = await asyncio.to_thread(
            focus_owned_browser_window,
            browser.browser_process_id,
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
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            exc.message,
            details={'reason': exc.reason},
            retryable=exc.retryable,
        ).to_dict()
    return {'success': True, 'browser_window_focused': focused}


__all__ = ['focus_native_browser_window']
