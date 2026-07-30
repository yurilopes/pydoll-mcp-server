"""Intent-driven form filling tool."""

from __future__ import annotations

import json
import time
from typing import Annotated, TypedDict

from pydantic import Field
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.dom.reference_scripts import ELEMENT_REFERENCE_HELPERS
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_string, normalize_json_value
from pydoll_mcp_server.tools.form_input_modes import (
    keyboard_fallback_allowed,
    keyboard_fill,
    read_filled_state,
    wait_expected_enabled,
)


class FormFillField(TypedDict, total=False):
    label_contains: str
    question_contains: str
    placeholder_contains: str
    selector: str
    role: str
    name: str
    value: str | int | float | bool | None
    checked: bool
    option_text: str
    mode: str


async def form_fill_fields(
    client_id: str,
    tab_id: str,
    fields: Annotated[
        list[FormFillField],
        Field(
            description='Explicit field mappings. Use one or more label, question, placeholder, selector, role, or name hints per field.'
        ),
    ],
    scope: Annotated[
        str,
        Field(
            description='Form scope hint: auto, modal, dialog, form, or main.',
            json_schema_extra={'enum': ['auto', 'modal', 'dialog', 'form', 'main']},
        ),
    ] = 'auto',
    validate: Annotated[bool, Field(description='Run validation and return validation_errors after filling.')] = True,
    include_values: Annotated[bool, Field(description='Include values in field evidence when true.')] = False,
    mode: Annotated[
        str,
        Field(
            description='Default fill mode: auto, framework_safe, keyboard, or blur.',
            json_schema_extra={'enum': ['auto', 'framework_safe', 'keyboard', 'blur']},
        ),
    ] = 'auto',
    validation_timeout: Annotated[
        float,
        Field(description='Timeout for dependent validation and enabled controls.'),
    ] = 3.0,
    expected_enabled_element_id: Annotated[
        str,
        Field(description='Optional cached control expected to become enabled after filling.'),
    ] = '',
) -> JsonObject:
    if mode not in {'auto', 'framework_safe', 'keyboard', 'blur'}:
        return StructuredError(ErrorCode.INVALID_INPUT, f'Unsupported fill mode: {mode}').to_dict()
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    try:
        normalized_fields = [_field_to_json(field) for field in fields]
    except (TypeError, ValueError, AttributeError) as exc:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            f'fields contains non-serializable values: {exc}',
        ).to_dict()

    payload = json.dumps(
        {
            'fields': normalized_fields,
            'scope': scope,
            'validate': validate,
            'include_values': include_values,
            'mode': mode,
        }
    )

    fallback_used = False
    dependent_control_enabled: bool | None = None
    try:
        async with tab_operation_lock(tab_id):
            result = await tab_info.pydoll_tab.execute_script(_fill_script(payload), return_by_value=True)
            data = extract_script_object(result)
            if expected_enabled_element_id:
                dependent_control_enabled = await wait_expected_enabled(
                    tab_info,
                    expected_enabled_element_id,
                    min(max(validation_timeout, 0.1), 30.0),
                )
            keyboard_requests: list[JsonObject] = []
            for item in get_array(data, 'filled', []):
                if isinstance(item, dict) and (
                    str(item.get('mode_requested', mode)) == 'keyboard' or mode == 'keyboard'
                ):
                    keyboard_requests.append(item)
            if mode == 'auto' and dependent_control_enabled is False:
                keyboard_requests = []
                for item in get_array(data, 'filled', [])[:1]:
                    if isinstance(item, dict):
                        keyboard_requests.append(item)
            for item_value in keyboard_requests:
                selector = str(item_value.get('selector_hint', ''))
                if not selector:
                    continue
                element = await tab_info.pydoll_tab.query(selector, timeout=1, find_all=False, raise_exc=False)
                if element is None or not await keyboard_fallback_allowed(element):
                    continue
                request_value = str(item_value.get('requested_value', ''))
                await keyboard_fill(tab_info.pydoll_tab, element, request_value)
                state = await read_filled_state(element)
                item_value['mode_used'] = 'keyboard'
                item_value['fallback_used'] = True
                item_value['verified'] = get_string(state, 'value', '') == request_value
                item_value['field_valid'] = item_value['verified']
                fallback_used = True
            if expected_enabled_element_id and fallback_used:
                dependent_control_enabled = await wait_expected_enabled(
                    tab_info,
                    expected_enabled_element_id,
                    min(max(validation_timeout, 0.1), 30.0),
                )
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Form fill failed: {exc}',
            retryable=True,
        ).to_dict()

    filled: JsonArray = []
    unfilled: JsonArray = []
    ambiguous: JsonArray = []
    validation_errors: JsonArray = []

    for item in get_array(data, 'filled', []):
        if isinstance(item, dict):
            if 'field_valid' not in item:
                item['field_valid'] = bool(item.get('verified', item.get('selected', item.get('checked', True))))
            filled.append(item)
    for item in get_array(data, 'unfilled', []):
        if isinstance(item, dict):
            unfilled.append(item)
    for item in get_array(data, 'ambiguous', []):
        if isinstance(item, dict):
            ambiguous.append(item)
    for item in get_array(data, 'validation_errors', []):
        if isinstance(item, dict):
            validation_errors.append(item)

    evidence: JsonObject = {
        'timestamp': time.time(),
        'filled_count': len(filled),
        'unfilled_count': len(unfilled),
        'ambiguous_count': len(ambiguous),
    }

    warnings: list[str] = []
    if ambiguous:
        warnings.append(f'{len(ambiguous)} field(s) had ambiguous matches.')
    if unfilled:
        warnings.append(f'{len(unfilled)} field(s) could not be filled.')
    if dependent_control_enabled is False:
        warnings.append('The expected dependent control remained disabled after validation.')

    used_modes = {str(item.get('mode_used', mode)) for item in filled if isinstance(item, dict)}
    mode_used = next(iter(used_modes)) if len(used_modes) == 1 else ('mixed' if used_modes else mode)

    return {
        'success': len(unfilled) == 0 and len(ambiguous) == 0,
        'filled': filled,
        'unfilled': unfilled,
        'ambiguous': ambiguous,
        'validation_errors': validation_errors,
        'security_controls': get_array(data, 'security_controls', []),
        'pending_required': data.get('pending_required', []),
        'mode_requested': mode,
        'mode_used': mode_used,
        'fallback_used': fallback_used,
        'field_valid': len(validation_errors) == 0 and not data.get('pending_required', []),
        'dependent_control_enabled': dependent_control_enabled,
        'validation_timeout': min(max(validation_timeout, 0.1), 30.0),
        'warnings': list(warnings),
        'evidence': evidence,
    }


def _field_to_json(field: FormFillField) -> JsonObject:
    return {str(key): normalize_json_value(value, f'fields.{key}') for key, value in field.items()}


def _fill_script(payload_json: str) -> str:
    return (
        'const opts = '
        + payload_json
        + """;
const results = { filled: [], unfilled: [], ambiguous: [], validation_errors: [], pending_required: [], security_controls: [] };

function norm(v) { return String(v || '').normalize('NFC').trim().replace(/\\s+/g, ' '); }
function fold(v) { return norm(v).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase(); }
"""
        + ELEMENT_REFERENCE_HELPERS
        + """
function visible(el) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none'
        && style.visibility !== 'hidden' && parseFloat(style.opacity) > 0;
}

function findField(request) {
    let candidates = [];
    const inputs = document.querySelectorAll(
        'input:not([type="hidden"]):not([type="file"]):not([type="submit"]):not([type="button"]),'
        + 'textarea, select, [contenteditable="true"]'
    );
    for (const el of inputs) {
        if (!visible(el)) continue;
        let score = 0;
        const label = norm(
            (el.id ? (document.querySelector('label[for="' + CSS.escape(el.id) + '"]')?.innerText || '') : '')
            || el.closest('label')?.innerText
            || el.getAttribute('aria-label')
            || el.placeholder || el.name || ''
        );
        const foldedLabel = fold(label);
        if (request.label_contains && foldedLabel.includes(fold(request.label_contains)))
            score += 100;
        if (request.question_contains) {
            const parent = el.closest('.form-group, fieldset, .field, div');
            const parentText = parent ? fold(parent.innerText || '') : '';
            if (parentText.includes(fold(request.question_contains))) score += 50;
        }
        if (request.placeholder_contains
            && fold(el.placeholder || '').includes(fold(request.placeholder_contains)))
            score += 80;
        if (request.selector && (el.matches(request.selector) || el.id === request.selector))
            score += 200;
        if (request.role && (el.getAttribute('role') || '') === request.role) score += 70;
        if (request.name && el.name === request.name) score += 150;
        if (score > 0) {
            candidates.push({ el, score, label });
        }
    }
    if (candidates.length === 0) return null;
    candidates.sort((a, b) => b.score - a.score);
    if (candidates.length > 1 && candidates[0].score - candidates[1].score < 15
        && !request.selector) {
        return { ambiguous: candidates.slice(0, 3).map(c => ({
            label: c.label, score: c.score, tag: c.el.tagName.toLowerCase(), type: c.el.type || ''
        })) };
    }
    return { el: candidates[0].el, label: candidates[0].label };
}

function setValue(el, request) {
    const tag = el.tagName;
    const type = (el.type || '').toLowerCase();
    const value = String(request.value ?? '');

    if (tag === 'INPUT' && type === 'checkbox') {
        const shouldCheck = request.checked === true
            || value === 'true' || value === '1';
        el.checked = shouldCheck;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return { checked: shouldCheck };
    }

    if (tag === 'INPUT' && type === 'radio') {
        const radioGroup = document.querySelectorAll(
            'input[name="' + (el.name || '') + '"][type="radio"]'
        );
        for (const radio of radioGroup) {
            const radioText = norm(radio.closest('label')?.innerText || radio.value || '');
            const match = fold(radioText) === fold(request.option_text || value || '')
                || fold(radio.value || '') === fold(value || '');
            if (match && visible(radio)) {
                radio.checked = true;
                radio.dispatchEvent(new Event('change', { bubbles: true }));
                return { selected: true };
            }
        }
        el.checked = true;
        return { selected: true };
    }

    if (tag === 'SELECT') {
        for (const opt of el.options) {
            const optText = norm(opt.text || '');
            const optVal = (opt.value || '');
            const target = fold(request.option_text || value || '');
            if (fold(optText) === target || fold(optVal) === target) {
                el.value = opt.value;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return { selected: optText };
            }
        }
        return { error: 'option_not_found' };
    }

    if (tag === 'TEXTAREA' || (tag === 'INPUT' && (
        type === 'text' || type === 'email' || type === 'number'
        || type === 'tel' || type === 'url'))) {
        const nativeSetter = Object.getOwnPropertyDescriptor(
            HTMLInputElement.prototype, 'value'
        ) || Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
        if (nativeSetter && nativeSetter.set) {
            nativeSetter.set.call(el, value);
        } else {
            el.value = value;
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        return { value_length: value.length, verified: el.value === value };
    }

    if (el.isContentEditable) {
        el.textContent = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        return { value_length: value.length };
    }

    return { error: 'unsupported_control' };
}

for (const request of opts.fields) {
    const match = findField(request);
    if (!match) {
        results.unfilled.push({ label_contains: request.label_contains || '(none)', reason: 'no_match' });
        continue;
    }
    if (match.ambiguous) {
        results.ambiguous.push({ candidates: match.ambiguous });
        continue;
    }
    const el = match.el;
    const context = norm(el.closest('label, fieldset, .form-group, .field, div')?.innerText || '') + ' '
        + [el.getAttribute('name'), el.getAttribute('aria-label'), el.getAttribute('placeholder')].filter(Boolean).join(' ');
    if (/captcha|recaptcha|hcaptcha|turnstile|one[- ]time|otp|2fa|two[- ]factor|payment|credit card|cvv|cvc|biometric|identity verification/i.test(context)) {
        results.security_controls.push({ label: match.label, kind: 'security_control', automation_allowed: false });
        results.unfilled.push({ label: match.label, tag: el.tagName.toLowerCase(), type: el.type || '', reason: 'security_control_present' });
        continue;
    }
    const result = setValue(el, request);
    if (result.error) {
        results.unfilled.push({
            label: match.label,
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            reason: result.error,
        });
        continue;
    }
    results.filled.push({
        label: match.label,
        tag: el.tagName.toLowerCase(),
        type: el.type || '',
        value_length: (request.value || '').length,
        requested_value: String(request.value ?? ''),
        selector_hint: structuralSelector(el),
        mode_requested: request.mode || opts.mode || 'auto',
        mode_used: request.mode === 'keyboard' || opts.mode === 'keyboard' ? 'keyboard' : 'framework_safe',
        fallback_used: false,
        ...result,
    });
}

if (opts.validate) {
    const pending = [];
    const required = document.querySelectorAll(
        'input[required], textarea[required], select[required], [aria-required="true"]'
    );
    for (const el of required) {
        if (!visible(el)) continue;
        if (el.type === 'hidden' || el.type === 'file') continue;
        if (!el.value.trim()) {
            const lbl = norm(
                el.closest('label')?.innerText
                || el.getAttribute('aria-label')
                || el.placeholder || ''
            );
            if (lbl) pending.push(lbl);
        }
    }
    if (pending.length) results.pending_required = pending;
}

return results;
"""
    )
