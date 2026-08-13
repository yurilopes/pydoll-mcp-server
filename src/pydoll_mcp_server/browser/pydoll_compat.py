"""Pydoll API compatibility helpers. Use ONLY these to access Pydoll objects."""

from __future__ import annotations

import asyncio
import importlib
import unicodedata
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeGuard

from pydoll.browser.chromium.base import Browser
from pydoll.browser.options import ChromiumOptions
from pydoll.browser.tab import Tab
from pydoll.commands.dom_commands import DomCommands
from pydoll.commands.network_commands import NetworkCommands
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.script_utils import extract_script_bool
from pydoll_mcp_server.json_types import get_object, get_string, require_json_object


def _is_object_awaitable(value: object) -> TypeGuard[Awaitable[object]]:
    return isinstance(value, Awaitable)


def _is_chromium_options_factory(value: object) -> TypeGuard[Callable[[], ChromiumOptions]]:
    return callable(value)


def create_chromium_options() -> ChromiumOptions:
    """Create Pydoll options at the single untyped third-party boundary."""
    options_module = importlib.import_module('pydoll.browser.options')
    factory: object = options_module.ChromiumOptions
    if not _is_chromium_options_factory(factory):
        raise TypeError('Pydoll ChromiumOptions factory is not callable')
    return factory()


def install_browser_process_manager(browser: Browser, process_manager: object) -> None:
    """Install a managed process manager before Pydoll starts the browser."""
    object.__setattr__(browser, '_browser_process_manager', process_manager)


async def get_tab_url(tab: Tab) -> str:
    url = await tab.current_url
    return str(url) if url else ''


async def get_tab_title(tab: Tab) -> str:
    title = await tab.title
    return str(title) if title else ''


def get_tab_target_id(tab: Tab) -> str:
    """Read the stable Pydoll target identifier at the compatibility boundary."""

    try:
        target_id: object = object.__getattribute__(tab, '_target_id')
    except AttributeError:
        return ''
    return target_id if isinstance(target_id, str) else ''


async def get_opened_tabs(browser: Browser) -> list[Tab]:
    """Return live page targets currently exposed by Pydoll."""

    return await browser.get_opened_tabs()


async def get_element_text(element: WebElement) -> str:
    try:
        text = await element.text
    except (KeyError, PydollException, OSError, TypeError, ValueError):
        # Hidden native controls can disappear between query and outerHTML
        # retrieval. Text is diagnostic only, so keep the element usable for
        # a subsequent fingerprinted action instead of failing discovery.
        return ''
    return unicodedata.normalize('NFC', str(text)) if text else ''


def get_element_attribute(element: WebElement, name: str) -> str | None:
    result = element.get_attribute(name)
    return str(result) if result is not None else None


async def is_element_visible(element: WebElement) -> bool:
    try:
        response = await element.execute_script(
            """
            const rect = this.getBoundingClientRect();
            const style = window.getComputedStyle(this);
            return rect.width > 0 && rect.height > 0
                && style.display !== 'none'
                && style.visibility !== 'hidden';
            """,
            return_by_value=True,
        )
        return extract_script_bool(response)
    except (KeyError, PydollException, OSError, TypeError, ValueError):
        return False


async def enable_network_events(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.enable_network_events
    await operation()


async def disable_network_events(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.disable_network_events
    await operation()


async def enable_runtime_events(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.enable_runtime_events
    await operation()


async def enable_page_events(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.enable_page_events
    await operation()


async def disable_page_events(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.disable_page_events
    await operation()


async def enable_intercept_file_chooser_dialog(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.enable_intercept_file_chooser_dialog
    await operation()


async def disable_intercept_file_chooser_dialog(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.disable_intercept_file_chooser_dialog
    await operation()


async def bring_tab_to_front(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.bring_to_front
    await operation()


async def close_tab(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.close
    await operation()


async def tab_has_dialog(tab: Tab) -> bool:
    """Check for a browser dialog without exposing the Pydoll object to tools."""

    await enable_page_events(tab)
    return await tab.has_dialog()


async def try_close_tab(tab: Tab) -> bool:
    # Closing the replaced tab is best-effort because the recovered tab must remain usable.
    try:
        await close_tab(tab)
    except (PydollException, OSError):
        return False
    return True


async def refresh_tab(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.refresh
    await operation()


async def stop_browser(browser: Browser) -> None:
    operation: Callable[[], Awaitable[object]] = browser.stop
    await operation()


def get_browser_process_id(browser: Browser) -> int | None:
    """Read the launched browser PID through one isolated Pydoll compatibility boundary."""

    try:
        process_manager: object = object.__getattribute__(browser, '_browser_process_manager')
        process: object = object.__getattribute__(process_manager, '_process')
        if process is None:
            return None
        process_id: object = object.__getattribute__(process, 'pid')
    except AttributeError:
        return None
    return process_id if isinstance(process_id, int) and not isinstance(process_id, bool) else None


def get_browser_connection_port(browser: Browser) -> int | None:
    """Read the Pydoll connection port at the isolated compatibility boundary."""

    try:
        port: object = object.__getattribute__(browser, '_connection_port')
    except AttributeError:
        return None
    return port if isinstance(port, int) and not isinstance(port, bool) and port > 0 else None


async def get_browser_ws_address(connection_port: int) -> str:
    """Resolve a browser websocket endpoint through Pydoll's supported helper."""

    from pydoll.utils.general import get_browser_ws_address

    return await get_browser_ws_address(connection_port)


async def register_runtime_callback(
    tab: Tab,
    event_name: str,
    callback: Callable[[object], Awaitable[None]],
) -> int:
    async def normalized_callback(event: dict[object, object]) -> None:
        await callback(event)

    method: object = object.__getattribute__(tab, 'on')
    if not callable(method):
        raise TypeError('Pydoll tab does not expose a callable event registration method')
    registration: object = method(event_name, normalized_callback)
    if not _is_object_awaitable(registration):
        raise TypeError('Pydoll event registration did not return an awaitable')
    result: object = await asyncio.ensure_future(registration)
    if not isinstance(result, int):
        raise TypeError('Pydoll event registration did not return a callback id')
    return result


async def register_network_callback(
    tab: Tab,
    event_name: str,
    callback: Callable[[object], Awaitable[None]],
) -> int:
    return await register_runtime_callback(tab, event_name, callback)


async def remove_tab_callback(tab: Tab, callback_id: int) -> None:
    await tab.remove_callback(callback_id)


async def get_request_post_data(tab: Tab, request_id: str) -> str:
    method: object = object.__getattribute__(tab, '_execute_command')
    if not callable(method):
        raise TypeError('Pydoll tab does not expose command execution')
    pending: object = method(NetworkCommands.get_request_post_data(request_id))
    if not _is_object_awaitable(pending):
        raise TypeError('Pydoll command execution did not return an awaitable')
    response = require_json_object(await asyncio.ensure_future(pending), 'getRequestPostData response')
    return get_string(get_object(response, 'result', {}), 'postData')


async def set_input_files(element: WebElement, paths: list[str]) -> None:
    file_paths: list[str | Path] = list(paths)
    method = element.set_input_files
    upload: object = method(file_paths)
    if not _is_object_awaitable(upload):
        raise TypeError('Pydoll file upload did not return an awaitable')
    await asyncio.ensure_future(upload)


async def set_input_files_by_backend_node(tab: Tab, backend_node_id: int, paths: list[str]) -> None:
    """Set files for a CDP file chooser event without exposing arbitrary CDP commands."""

    method: object = object.__getattribute__(tab, '_execute_command')
    if not callable(method):
        raise TypeError('Pydoll tab does not expose command execution')
    pending: object = method(
        DomCommands.set_file_input_files(
            files=list(paths),
            backend_node_id=backend_node_id,
        )
    )
    if not _is_object_awaitable(pending):
        raise TypeError('Pydoll command execution did not return an awaitable')
    await asyncio.ensure_future(pending)
