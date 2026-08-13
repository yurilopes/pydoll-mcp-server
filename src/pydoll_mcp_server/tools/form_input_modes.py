"""Keyboard fallback and validation helpers shared by form tools."""

from __future__ import annotations

import asyncio
import re
import time

from pydoll.constants import Key
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.pydoll_compat import get_element_attribute
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_normalized_bool,
    extract_normalized_object,
)
from pydoll_mcp_server.json_types import JsonObject, get_array, get_bool, get_string
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
        const value = this.type === 'password' ? '' : (this.value ?? this.textContent ?? '');
        const errors = [];
        const described = (this.getAttribute('aria-describedby') || '').split(/\\s+/).filter(Boolean);
        for (const id of described) {
            const node = document.getElementById(id);
            if (node && (node.innerText || node.textContent || '').trim())
                errors.push((node.innerText || node.textContent || '').trim());
        }
        const selected = this.tagName === 'SELECT' && this.selectedIndex >= 0
            ? this.options[this.selectedIndex] : null;
        return {
            tag:this.tagName || '', input_type:this.type || '', value, selected_text:selected ? selected.text : '',
            selected_value:selected ? selected.value : '',
            checked:this.checked === true, indeterminate:this.indeterminate === true,
            aria_checked:this.getAttribute('aria-checked') || '',
            aria_selected:this.getAttribute('aria-selected') || '',
            aria_pressed:this.getAttribute('aria-pressed') || '',
            validity: typeof this.checkValidity === 'function'
                ? (this.checkValidity() ? 'valid' : 'invalid') : 'not_yet_validated',
            errors, disabled:!!this.disabled,
            enabled:!this.disabled && this.getAttribute('aria-disabled') !== 'true',
            read_only:!!this.readOnly || this.getAttribute('aria-readonly') === 'true',
            visible: Boolean(this.getClientRects().length),
            value_present: String(value).trim().length > 0,
            framework_value: String(value).trim().length > 0 ? 'present' : 'absent',
            blurred: false,
            ready_for_submission: false
        };
        """,
        return_by_value=True,
    )
    return extract_normalized_object(result, 'read_filled_state')


def verification_satisfied(state: JsonObject, expected: str, level: str) -> bool:
    """Evaluate observable field signals without claiming access to framework internals."""

    selected_text = get_string(state, 'selected_text', '')
    value_matches = value_equivalent(state, expected) or selected_text == expected
    if not value_matches:
        return False
    if level == 'dom':
        return True
    framework_event = get_bool(state, 'framework_event', False)
    survived = get_bool(state, 'controlled_value_survived', False)
    if level == 'framework_event':
        return framework_event and survived
    blurred = get_bool(state, 'blurred', False)
    if level == 'blurred':
        return framework_event and survived and blurred
    validity = get_string(state, 'validity', 'not_yet_validated')
    errors = get_array(state, 'errors', [])
    return framework_event and survived and blurred and validity != 'invalid' and not errors


def value_equivalent(state: JsonObject, expected: str) -> bool:
    actual = get_string(state, 'value', '')
    if actual == expected:
        return True
    if get_string(state, 'input_type', '').casefold() != 'tel':
        return False
    actual_digits = re.sub(r'\D', '', actual)
    expected_digits = re.sub(r'\D', '', expected)
    return bool(expected_digits) and actual_digits == expected_digits


def classify_keyboard_fallback(data: JsonObject) -> JsonObject:
    """Classify a keyboard fallback without inspecting field values."""

    descriptor = ' '.join(get_string(data, key, '') for key in ('type', 'name', 'autocomplete', 'aria', 'placeholder'))
    blocked = re.compile(
        r'captcha|recaptcha|hcaptcha|turnstile|otp|one[- ]time|2fa|two[- ]factor|'
        r'payment|card|cvv|cvc|biometric|identity verification|government id|passport|driver.?s license',
        re.I,
    )
    input_type = get_string(data, 'type', '').lower()
    if input_type == 'password':
        return {'allowed': False, 'known': True, 'reason': 'password_control'}
    if blocked.search(descriptor):
        return {'allowed': False, 'known': True, 'reason': 'security_control'}
    return {'allowed': True, 'known': True, 'reason': 'ordinary_form_control'}


async def keyboard_fallback_decision(element: WebElement) -> JsonObject:
    """Inspect whether keyboard fallback is safe, preserving unknown state."""

    try:
        data: JsonObject = {
            'tag': str(element.tag_name or ''),
            'type': get_element_attribute(element, 'type') or '',
            'name': get_element_attribute(element, 'name') or '',
            'autocomplete': get_element_attribute(element, 'autocomplete') or '',
            'aria': get_element_attribute(element, 'aria-label') or '',
            'placeholder': get_element_attribute(element, 'placeholder') or '',
        }
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        return {'allowed': False, 'known': False, 'reason': 'inspection_unavailable'}
    return classify_keyboard_fallback(data)


async def keyboard_fallback_allowed(element: WebElement) -> bool:
    decision = await keyboard_fallback_decision(element)
    return get_bool(decision, 'allowed', False)


async def wait_expected_enabled(tab_info: TabInfo, element_id: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        element = await resolve_element(tab_info, element_id)
        if element is not None:
            result = await element.execute_script(
                "return !this.disabled && this.getAttribute('aria-disabled') !== 'true';",
                return_by_value=True,
            )
            value = extract_normalized_bool(result, 'wait_expected_enabled')
            if value is True:
                return True
        await asyncio.sleep(0.1)
    return False
