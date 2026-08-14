"""Passive, privacy-preserving signals exposed by the current web page."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol

from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject


class ScriptExecutor(Protocol):
    """Minimal Pydoll-compatible script boundary used by passive diagnostics."""

    def execute_script(self, script: str, *, return_by_value: bool = False) -> Awaitable[object]: ...


def security_control_error(control: JsonObject, subject: str = 'target') -> JsonObject:
    """Build the stable response used when an action targets a security control."""

    response = StructuredError(
        ErrorCode.SECURITY_CONTROL_PRESENT,
        f'The {subject} is a security control that requires user action.',
        details={'security_control': control},
        recovery_hint='Ask the user to complete the security control, then re-observe the page.',
    ).to_dict()
    response['failure_origin'] = 'security'
    return response


def site_diagnostics_script(compact: bool = False) -> str:
    if compact:
        return compact_site_diagnostics_script()
    return r"""
(() => {
    function normalize(value) {
        return String(value || '').normalize('NFC').trim().replace(/\s+/g, ' ');
    }
    function visible(element) {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none'
            && style.visibility !== 'hidden' && parseFloat(style.opacity || '1') > 0;
    }
    function safeUrl(value) {
        try {
            const url = new URL(value, location.href);
            url.search = '';
            url.hash = '';
            return url.href;
        } catch (error) {
            return '';
        }
    }
    function selectorFor(element) {
        if (element.id) return '#' + (CSS.escape ? CSS.escape(element.id) : element.id);
        return element.tagName.toLowerCase();
    }
    const patterns = [
        {kind: 'captcha', confidence: 0.98,
            pattern: /captcha|recaptcha|hcaptcha|turnstile|human verification|i am not a robot|are you human/i},
        {kind: 'two_factor', confidence: 0.95, pattern: /two[- ]factor|2fa|otp|verification code|authentication code/i},
        {kind: 'payment', confidence: 0.94, pattern: /payment|credit card|card number|billing|cvv|cvc|paypal/i},
        {kind: 'biometric', confidence: 0.96, pattern: /biometric|face id|facial recognition|fingerprint|selfie/i},
        {kind: 'identity_verification', confidence: 0.92,
            pattern: /identity verification|verify identity|government id|passport|license/i},
    ];
    const controls = [];
    const seen = new Set();
    function addSignal(kind, confidence, source, element, frameUrl) {
        const key = kind + '|' + source;
        if (seen.has(key)) return;
        seen.add(key);
        controls.push({
            kind,
            confidence,
            automation_allowed: false,
            requires_user_action: true,
            source: normalize(source).slice(0, 240),
            selector_hint: element ? selectorFor(element) : '',
            frame_url: frameUrl || ''
        });
    }
    const visibleNodes = document.querySelectorAll('body *');
    for (const element of visibleNodes) {
        if (!visible(element)) continue;
        const safeAttrs = [
            element.getAttribute('aria-label'), element.getAttribute('title'),
            element.getAttribute('name'), element.getAttribute('placeholder'),
            element.getAttribute('alt'), element.getAttribute('role'),
            element.getAttribute('id'), element.getAttribute('class')
        ].filter(Boolean).join(' ');
        const directText = [...element.childNodes]
            .filter((node) => node.nodeType === Node.TEXT_NODE)
            .map((node) => node.textContent || '')
            .join(' ');
        const source = normalize(directText + ' ' + safeAttrs);
        if (!source) continue;
        for (const item of patterns) {
            if (item.pattern.test(source)) addSignal(item.kind, item.confidence, source, element, '');
        }
    }
    for (const frame of document.querySelectorAll('iframe, frame')) {
        if (!visible(frame)) continue;
        const source = normalize([
            frame.getAttribute('title'), frame.getAttribute('name'), frame.getAttribute('aria-label'),
            frame.getAttribute('src')
        ].filter(Boolean).join(' '));
        for (const item of patterns) {
            if (item.pattern.test(source)) {
                addSignal(item.kind, item.confidence, source, frame, safeUrl(frame.getAttribute('src') || ''));
            }
        }
    }
    const frameworkHints = [];
    if (document.querySelector('[data-reactroot], [data-reactid]')
        || Object.keys(document.documentElement).some((key) => key.toLowerCase().includes('react'))) {
        frameworkHints.push('react');
    }
    if (document.querySelector('[ng-version], [ng-app], [ng-model], [formcontrolname]')) {
        frameworkHints.push('angular_like');
    }
    if (document.querySelector('[data-v-], [v-cloak]')) frameworkHints.push('vue_like');
    if ([...document.querySelectorAll('*')].some((element) => element.tagName.includes('-'))) {
        frameworkHints.push('custom_elements');
    }
    if ([...document.querySelectorAll('*')].some((element) => Boolean(element.shadowRoot))) {
        frameworkHints.push('open_shadow_root');
    }
    const validationErrors = [...document.querySelectorAll('[aria-invalid="true"], [role="alert"], [class*="error"]')]
        .filter(visible).length;
    const requiredPending = [...document.querySelectorAll(
        'input[required], textarea[required], select[required], [aria-required="true"]'
    )].filter((element) => visible(element) && !element.value
        && element.type !== 'hidden' && element.type !== 'file').length;
    const primary = [...document.querySelectorAll('button, input[type="submit"], [role="button"]')]
        .find((element) => visible(element) && !element.disabled && element.getAttribute('aria-disabled') !== 'true');
    return {
        framework_hints: [...new Set(frameworkHints)],
        security_controls: controls,
        validation_state: {
            invalid_count: validationErrors,
            pending_required_count: requiredPending,
            valid: validationErrors === 0 && requiredPending === 0
        },
        primary_action_enabled: Boolean(primary)
    };
})()
"""


def compact_site_diagnostics_script() -> str:
    """Return a focused signal probe for high-frequency workflow operations."""

    return r"""
(() => {
    function normalize(value) {
        return String(value || '').normalize('NFC').trim().replace(/\s+/g, ' ');
    }
    function visible(element) {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none'
            && style.visibility !== 'hidden' && parseFloat(style.opacity || '1') > 0;
    }
    function selectorFor(element) {
        if (element.id) return '#' + (CSS.escape ? CSS.escape(element.id) : element.id);
        return element.tagName.toLowerCase();
    }
    const patterns = [
        {kind: 'captcha', confidence: 0.98,
            pattern: /captcha|recaptcha|hcaptcha|turnstile|human verification|i am not a robot|are you human/i},
        {kind: 'two_factor', confidence: 0.95, pattern: /two[- ]factor|2fa|otp|verification code|authentication code/i},
        {kind: 'payment', confidence: 0.94, pattern: /payment|credit card|card number|billing|cvv|cvc|paypal/i},
        {kind: 'biometric', confidence: 0.96, pattern: /biometric|face id|facial recognition|fingerprint|selfie/i},
        {kind: 'identity_verification', confidence: 0.92,
            pattern: /identity verification|verify identity|government id|passport|license/i},
    ];
    const controls = [];
    const seen = new Set();
    function addSignal(kind, confidence, source, element) {
        const key = kind + '|' + source;
        if (seen.has(key)) return;
        seen.add(key);
        controls.push({kind, confidence, automation_allowed: false, requires_user_action: true,
            source: normalize(source).slice(0, 240), selector_hint: element ? selectorFor(element) : ''});
    }
    const nodes = document.querySelectorAll(
        'input,textarea,select,button,[role],iframe,frame,form,fieldset,'
        + '[aria-label],[title],[placeholder],[class*="captcha" i],[id*="captcha" i]'
    );
    for (const element of nodes) {
        if (!visible(element)) continue;
        const source = normalize([
            element.innerText || '', element.getAttribute('aria-label'), element.getAttribute('title'),
            element.getAttribute('name'), element.getAttribute('placeholder'), element.getAttribute('role'),
            element.getAttribute('id'), element.getAttribute('class'), element.getAttribute('src')
        ].filter(Boolean).join(' '));
        for (const item of patterns) {
            if (item.pattern.test(source)) addSignal(item.kind, item.confidence, source, element);
        }
    }
    const frameworkHints = [];
    if (document.querySelector('[data-reactroot], [data-reactid]')) frameworkHints.push('react');
    if (document.querySelector('[ng-version], [ng-app], [ng-model], [formcontrolname]')) {
        frameworkHints.push('angular_like');
    }
    if (document.querySelector('[data-v-], [v-cloak]')) frameworkHints.push('vue_like');
    const allNodes = document.querySelectorAll('*');
    if ([...allNodes].some((element) => element.tagName.includes('-'))) frameworkHints.push('custom_elements');
    if ([...allNodes].some((element) => Boolean(element.shadowRoot))) frameworkHints.push('open_shadow_root');
    const invalid = document.querySelectorAll('[aria-invalid="true"], [role="alert"], [class*="error" i]');
    const required = document.querySelectorAll(
        'input[required], textarea[required], select[required], [aria-required="true"]'
    );
    const pending = [...required].filter((element) => visible(element) && !element.value
        && element.type !== 'hidden' && element.type !== 'file').length;
    const primary = [...document.querySelectorAll('button,input[type="submit"],[role="button"]')]
        .find((element) => visible(element) && !element.disabled && element.getAttribute('aria-disabled') !== 'true');
    return {
        framework_hints: [...new Set(frameworkHints)], security_controls: controls,
        validation_state: {invalid_count: [...invalid].filter(visible).length,
            pending_required_count: pending, valid: invalid.length === 0 && pending === 0},
        primary_action_enabled: Boolean(primary)
    };
})()
"""


async def inspect_site_diagnostics(
    tab: ScriptExecutor | None,
    active_surface: str = '',
    compact: bool = False,
) -> JsonObject:
    if tab is None:
        return {
            'framework_hints': [],
            'security_controls': [],
            'validation_state': {},
            'active_surface': active_surface,
            'diagnostics_unavailable': True,
        }
    try:
        response = await tab.execute_script(site_diagnostics_script(compact), return_by_value=True)
        result = extract_script_object(response)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        return {
            'framework_hints': [],
            'security_controls': [],
            'validation_state': {},
            'active_surface': active_surface,
            'diagnostics_unavailable': True,
        }
    result['active_surface'] = active_surface
    return result


async def inspect_element_security(element: WebElement) -> JsonObject:
    script = """
    const tag = String(this.tagName || '').toLowerCase();
    const formControl = ['input', 'textarea', 'select', 'option'].includes(tag)
        || this.isContentEditable === true;
    const text = formControl ? '' : String(this.innerText || this.textContent || '').normalize('NFC');
    const attrs = [this.getAttribute('aria-label'), this.getAttribute('title'), this.getAttribute('name'),
        this.getAttribute('placeholder'), this.getAttribute('role'), this.getAttribute('autocomplete')]
        .filter(Boolean).join(' ');
    const source = (text + ' ' + attrs).trim();
    const patterns = [
        ['captcha', /captcha|recaptcha|hcaptcha|turnstile|i am not a robot|verify you are human/i],
        ['two_factor', /two[- ]factor|2fa|one[- ]time password|otp|verification code|authentication code/i],
        ['payment', /payment|credit card|card number|billing|cvv|cvc/i],
        ['biometric', /biometric|face id|facial recognition|fingerprint|selfie/i],
        ['identity_verification', /identity verification|verify identity|government id|passport|driver.?s license/i]
    ];
    for (const [kind, pattern] of patterns) {
        if (pattern.test(source)) return {
            kind, confidence: 0.95, automation_allowed: false,
            requires_user_action: true, source: source.slice(0, 240)
        };
    }
    return {};
    """
    try:
        response = await element.execute_script(script, return_by_value=True)
        return extract_script_object(response)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        return {}
