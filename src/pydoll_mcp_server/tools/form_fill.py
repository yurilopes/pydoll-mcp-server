"""Intent-driven form filling tool."""

from __future__ import annotations

import json
import time

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array


async def form_fill_fields(
    client_id: str,
    tab_id: str,
    fields: list[dict[str, object]],
    scope: str = 'auto',
    validate: bool = True,
    include_values: bool = False,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    try:
        normalized_fields: list[dict[str, object]] = [{str(k): v for k, v in field.items()} for field in fields]
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
        }
    )

    try:
        async with tab_operation_lock(tab_id):
            result = await tab_info.pydoll_tab.execute_script(_fill_script(payload), return_by_value=True)
            data = extract_script_object(result)
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

    return {
        'success': len(unfilled) == 0 and len(ambiguous) == 0,
        'filled': filled,
        'unfilled': unfilled,
        'ambiguous': ambiguous,
        'validation_errors': validation_errors,
        'pending_required': data.get('pending_required', []),
        'warnings': list(warnings),
        'evidence': evidence,
    }


def _fill_script(payload_json: str) -> str:
    return (
        'const opts = '
        + payload_json
        + """;
const results = { filled: [], unfilled: [], ambiguous: [], validation_errors: [], pending_required: [] };

function norm(v) { return (v || '').trim().replace(/\\s+/g, ' '); }
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
        const upperLabel = label.toLowerCase();
        if (request.label_contains && upperLabel.includes(request.label_contains.toLowerCase()))
            score += 100;
        if (request.question_contains) {
            const parent = el.closest('.form-group, fieldset, .field, div');
            const parentText = parent ? norm(parent.innerText || '').toLowerCase() : '';
            if (parentText.includes(request.question_contains.toLowerCase())) score += 50;
        }
        if (request.placeholder_contains
            && (el.placeholder || '').toLowerCase().includes(request.placeholder_contains.toLowerCase()))
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
    const value = request.value;

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
            const match = radioText.toLowerCase() === (request.option_text || value || '').toLowerCase()
                || (radio.value || '').toLowerCase() === (value || '').toLowerCase();
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
            const target = (request.option_text || value || '').toLowerCase();
            if (optText.toLowerCase() === target || optVal.toLowerCase() === target) {
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
