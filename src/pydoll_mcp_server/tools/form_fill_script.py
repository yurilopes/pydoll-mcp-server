from __future__ import annotations

from pydoll_mcp_server.dom.reference_scripts import ELEMENT_REFERENCE_HELPERS


def fill_script(payload_json: str) -> str:
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
        const valuePrototype = tag === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const nativeSetter = Object.getOwnPropertyDescriptor(valuePrototype, 'value');
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
