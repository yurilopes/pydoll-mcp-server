"""Keyboard fallback and validation helpers shared by form tools."""

from __future__ import annotations

import asyncio
import re
import time

from pydoll.constants import Key
from pydoll.elements.web_element import WebElement

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.script_utils import extract_script_object, extract_script_value
from pydoll_mcp_server.json_types import JsonObject, get_string
from pydoll_mcp_server.tools.element_resolver import resolve_element


async def keyboard_fill(tab: object, element: WebElement, value: str) -> None:
    await element.execute_script('this.focus(); return true;', return_by_value=True)
    keyboard = getattr(tab, 'keyboard', None)
    if keyboard is None:
        raise TypeError('Pydoll tab does not expose keyboard input')
    await keyboard.hotkey(Key.CONTROL, Key.A)
    await keyboard.type_text(value)
    await keyboard.press(Key.TAB)


async def read_filled_state(element: WebElement) -> JsonObject:
    result = await element.execute_script(
        """
        return {tag:this.tagName || '', value:this.value ?? this.textContent ?? '', selected_text:
            this.tagName === 'SELECT' && this.selectedIndex >= 0 ? this.options[this.selectedIndex].text : ''};
        """,
        return_by_value=True,
    )
    return extract_script_object(result)


async def keyboard_fallback_allowed(element: WebElement) -> bool:
    result = await element.execute_script(
        """
        return {tag:this.tagName || '', type:this.type || '', name:this.name || '',
            autocomplete:this.getAttribute('autocomplete') || '', aria:this.getAttribute('aria-label') || ''};
        """,
        return_by_value=True,
    )
    data = extract_script_object(result)
    descriptor = ' '.join(get_string(data, key, '') for key in ('type', 'name', 'autocomplete', 'aria'))
    blocked = re.compile(
        r'captcha|recaptcha|hcaptcha|turnstile|otp|one[- ]time|2fa|two[- ]factor|'
        r'payment|card|cvv|cvc|biometric|identity',
        re.I,
    )
    return not blocked.search(descriptor) and get_string(data, 'type', '').lower() not in {'password'}


async def wait_expected_enabled(tab_info: TabInfo, element_id: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        element = await resolve_element(tab_info, element_id)
        if element is not None:
            result = await element.execute_script(
                "return !this.disabled && this.getAttribute('aria-disabled') !== 'true';",
                return_by_value=True,
            )
            value = extract_script_value(result)
            if value is True:
                return True
        await asyncio.sleep(0.1)
    return False
