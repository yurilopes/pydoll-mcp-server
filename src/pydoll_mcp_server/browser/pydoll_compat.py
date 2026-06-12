"""Pydoll API compatibility helpers. Use ONLY these to access Pydoll objects."""

from __future__ import annotations

from typing import Any


async def get_tab_url(tab: Any) -> str:
    try:
        url = await tab.current_url
        return str(url) if url else ''
    except Exception:
        return ''


async def get_tab_title(tab: Any) -> str:
    try:
        title = await tab.title
        return str(title) if title else ''
    except Exception:
        return ''


async def get_element_text(element: Any) -> str:
    try:
        text = await element.text
        return str(text) if text else ''
    except Exception:
        return ''


def get_element_attribute(element: Any, name: str) -> str | None:
    try:
        result = element.get_attribute(name)
        return str(result) if result is not None else None
    except Exception:
        return None


async def is_element_visible(element: Any) -> bool:
    try:
        result = await element.is_visible()
        return bool(result)
    except Exception:
        return False
