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
function rootOf(el) {
    const root = el && typeof el.getRootNode === 'function' ? el.getRootNode() : document;
    return root && typeof root.querySelectorAll === 'function' ? root : document;
}
function allControls(root) {
    const result = [];
    const seen = new Set();
    function walk(current) {
        if (!current || typeof current.querySelectorAll !== 'function') return;
        for (const node of current.querySelectorAll(
            'input:not([type="hidden"]):not([type="file"]):not([type="submit"]):not([type="button"]),'
            + 'textarea, select, [contenteditable="true"]'
        )) {
            if (!seen.has(node)) { seen.add(node); result.push(node); }
        }
        for (const host of current.querySelectorAll('*')) {
            if (host.shadowRoot) walk(host.shadowRoot);
        }
    }
    walk(root);
    return result;
}
function labelText(el) {
    const root = rootOf(el);
    if (el.id) {
        const label = [...root.querySelectorAll('label')].find(
            (candidate) => candidate.htmlFor === el.id || candidate.getAttribute('for') === el.id
        );
        if (label) return norm(label.innerText || label.textContent || '');
    }
    const parent = el.closest('label');
    return norm(parent?.innerText || el.getAttribute('aria-label') || el.placeholder || el.name || '');
}
function contextText(el) {
    const parts = [];
    for (let current = el; current;) {
        parts.push(current.innerText || current.textContent || '');
        if (current.parentElement) current = current.parentElement;
        else current = current.getRootNode()?.host || null;
        if (parts.join(' ').length > 2000) break;
    }
    return norm(parts.join(' '));
}
function shadowPathFor(el) {
    const path = [];
    let current = el;
    while (current && typeof current.getRootNode === 'function') {
        const root = current.getRootNode();
        if (!root || !root.host) break;
        path.unshift(structuralSelector(root.host));
        current = root.host;
    }
    return path;
}

function visible(el) {
    for (let current = el; current;) {
        const rect = current.getBoundingClientRect();
        const style = getComputedStyle(current);
        if (rect.width <= 0 || rect.height <= 0 || style.display === 'none'
            || style.visibility === 'hidden' || parseFloat(style.opacity || '1') <= 0) return false;
        if (current.parentElement) current = current.parentElement;
        else current = current.getRootNode()?.host || null;
    }
    return true;
}

function findField(request) {
    let candidates = [];
    const inputs = allControls(document);
    for (const el of inputs) {
        if (!visible(el)) continue;
        let score = 0;
        const label = labelText(el);
        const foldedLabel = fold(label);
        if (request.label_contains && foldedLabel.includes(fold(request.label_contains)))
            score += 100;
        if (request.question_contains) {
            const parentText = fold(contextText(el));
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
        return { checked: shouldCheck, framework_event: true, blurred: document.activeElement !== el };
    }

    if (tag === 'INPUT' && type === 'radio') {
        const radioGroup = allControls(rootOf(el)).filter(
            (radio) => radio.tagName === 'INPUT' && radio.type === 'radio'
                && radio.name === (el.name || '')
        );
        for (const radio of radioGroup) {
            const radioText = labelText(radio) || norm(radio.value || '');
            const match = fold(radioText) === fold(request.option_text || value || '')
                || fold(radio.value || '') === fold(value || '');
            if (match && visible(radio)) {
                radio.checked = true;
                radio.dispatchEvent(new Event('change', { bubbles: true }));
                return { selected: true, framework_event: true, blurred: document.activeElement !== radio };
            }
        }
        el.checked = true;
        return { selected: true, framework_event: true, blurred: document.activeElement !== el };
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
        if (typeof el.blur === 'function') el.blur();
        else el.dispatchEvent(new Event('blur', { bubbles: true }));
        return {
            value_length: value.length,
            verified: el.value === value,
            framework_event: true,
            event_names: ['input', 'change', 'blur'],
            controlled_value_survived: el.value === value,
            blurred: document.activeElement !== el
        };
    }

    if (el.isContentEditable) {
        el.textContent = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        if (typeof el.blur === 'function') el.blur();
        return {
            value_length: value.length,
            verified: el.textContent === value,
            framework_event: true,
            event_names: ['input', 'blur'],
            controlled_value_survived: el.textContent === value,
            blurred: document.activeElement !== el
        };
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
    const context = contextText(el) + ' '
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
        shadow_path: shadowPathFor(el),
        mode_requested: request.mode || opts.mode || 'auto',
        mode_used: request.mode === 'keyboard' || opts.mode === 'keyboard' ? 'keyboard' : 'framework_safe',
        fallback_used: false,
        ...result,
    });
}

if (opts.validate) {
    const pending = [];
    const required = allControls(document).filter((el) => el.required
        || el.getAttribute('aria-required') === 'true');
    for (const el of required) {
        if (!visible(el)) continue;
        if (el.type === 'hidden' || el.type === 'file') continue;
        if (!el.value.trim()) {
            const lbl = labelText(el);
            if (lbl) pending.push(lbl);
        }
    }
    if (pending.length) results.pending_required = pending;
}

return results;
"""
    )


def read_states_script(payload_json: str) -> str:
    """Read all batch targets after one short render-stabilization window."""

    return f"""
const requests = {payload_json};
function resolveTarget(request) {{
    let root = document;
    for (const hostSelector of request.shadow_path || []) {{
        try {{
            const host = root.querySelector(hostSelector);
            if (!host || !host.shadowRoot) return null;
            root = host.shadowRoot;
        }} catch (error) {{ return null; }}
    }}
    try {{ return root.querySelector(request.selector_hint || ''); }} catch (error) {{ return null; }}
}}
function readState(request) {{
    const target = resolveTarget(request);
    if (!target) return {{error: 'stale_element'}};
    const value = target.type === 'password' ? '' : String(target.value ?? target.textContent ?? '');
    const selected = target.tagName === 'SELECT' && target.selectedIndex >= 0
        ? target.options[target.selectedIndex] : null;
    const errors = [];
    for (const id of (target.getAttribute('aria-describedby') || '').split(/\\s+/).filter(Boolean)) {{
        const node = (target.getRootNode?.() || document).querySelector?.('#' + CSS.escape(id));
        if (node && (node.innerText || node.textContent || '').trim()) errors.push(
            (node.innerText || node.textContent || '').trim()
        );
    }}
    return {{
        value,
        value_length: value.length,
        value_present: value.trim().length > 0,
        selected_text: selected ? selected.text : '',
        selected_value: selected ? selected.value : '',
        checked: target.checked === true,
        indeterminate: target.indeterminate === true,
        validity: typeof target.checkValidity === 'function'
            ? (target.checkValidity() ? 'valid' : 'invalid') : 'not_yet_validated',
        errors,
        blurred: document.activeElement !== target,
        enabled: !target.disabled && target.getAttribute('aria-disabled') !== 'true'
    }};
}}
return requests.map(readState);
"""
