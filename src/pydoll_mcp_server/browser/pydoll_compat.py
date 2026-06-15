"""Pydoll API compatibility helpers. Use ONLY these to access Pydoll objects."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeGuard

from pydoll.browser.chromium.base import Browser
from pydoll.browser.options import ChromiumOptions
from pydoll.browser.tab import Tab
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.script_utils import extract_script_bool


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


async def get_tab_url(tab: Tab) -> str:
    url = await tab.current_url
    return str(url) if url else ''


async def get_tab_title(tab: Tab) -> str:
    title = await tab.title
    return str(title) if title else ''


async def get_element_text(element: WebElement) -> str:
    text = await element.text
    return str(text) if text else ''


def get_element_attribute(element: WebElement, name: str) -> str | None:
    result = element.get_attribute(name)
    return str(result) if result is not None else None


async def is_element_visible(element: WebElement) -> bool:
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


async def bring_tab_to_front(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.bring_to_front
    await operation()


async def close_tab(tab: Tab) -> None:
    operation: Callable[[], Awaitable[object]] = tab.close
    await operation()


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


async def set_input_files(element: WebElement, paths: list[str]) -> None:
    file_paths: list[str | Path] = list(paths)
    method = element.set_input_files
    upload: object = method(file_paths)
    if not _is_object_awaitable(upload):
        raise TypeError('Pydoll file upload did not return an awaitable')
    await asyncio.ensure_future(upload)
