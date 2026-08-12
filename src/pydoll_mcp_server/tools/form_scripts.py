"""JavaScript snippets for form control tools."""

from __future__ import annotations

import json
from urllib.parse import quote


def fill_script(payload: str) -> str:
    encoded_payload = json.dumps(quote(payload, safe=''))
    return f"""
    function(){{
    const payload = JSON.parse(decodeURIComponent({encoded_payload}));
    const value = String(payload.value ?? '');
    const events = payload.events || [];
    const tag = this.tagName || '';
    const observedEvents = [];
    for (const eventName of events) this.addEventListener(
        eventName, () => observedEvents.push(eventName), {{once: true}}
    );
    if (payload.mode === 'blur' && typeof this.focus === 'function') this.focus();
    function nativeSet(el, proto, prop, next) {{
        const descriptor = Object.getOwnPropertyDescriptor(proto, prop);
        if (descriptor && descriptor.set) descriptor.set.call(el, next);
        else el[prop] = next;
    }}
    function fire(el, name) {{
        if (name === 'blur' && typeof el.blur === 'function') el.blur();
        el.dispatchEvent(new Event(name, {{bubbles: true}}));
    }}
    let selectedText = '';
    if (tag === 'INPUT') nativeSet(this, HTMLInputElement.prototype, 'value', value);
    else if (tag === 'TEXTAREA') nativeSet(this, HTMLTextAreaElement.prototype, 'value', value);
    else if (tag === 'SELECT') {{
        const options = [...this.options];
        const match = options.find((option) =>
            option.value === value || option.label === value || option.text === value
        );
        if (!match && value) return {{error: 'option_not_found', tag, value: this.value || ''}};
        for (const option of options) option.selected = option === match;
        selectedText = match ? match.text : '';
    }} else if (this.isContentEditable) {{
        this.textContent = value;
    }} else {{
        return {{error: 'not_editable', tag, value: ''}};
    }}
    for (const eventName of events) fire(this, eventName);
    return {{
        tag,
        value: this.value ?? this.textContent ?? '',
        selected_text: selectedText,
        selected_value: tag === 'SELECT' && this.selectedIndex >= 0 ? this.options[this.selectedIndex].value : '',
        framework_event: observedEvents.length > 0,
        event_names: observedEvents,
        blurred: events.includes('blur'),
        validity: typeof this.checkValidity === 'function'
            ? (this.checkValidity() ? 'valid' : 'invalid') : 'not_yet_validated',
        errors: [],
        changed: this.dataset ? this.dataset.changed === 'true' : false,
        controlled_value_survived: false
    }};
    }}
    """


def fill_reference_script(reference: str, payload: str) -> str:
    """Fill an exact page reference when a cached WebElement cannot be trusted."""

    reference_literal = json.dumps(reference)
    return f"""
    (() => {{
        const reference = {reference_literal};
        let target = null;
        if (reference.startsWith('/')) {{
            target = document.evaluate(
                reference, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
            ).singleNodeValue;
        }} else {{
            try {{ target = document.querySelector(reference); }} catch (error) {{ target = null; }}
        }}
        if (!target) return {{error: 'stale_element'}};
        if (typeof target.scrollIntoView === 'function') target.scrollIntoView({{block: 'center'}});
        return ({fill_script(payload)}).call(target);
    }})()
    """


def read_filled_state_reference_script(reference: str) -> str:
    """Read observable state from the same exact page reference used for filling."""

    reference_literal = json.dumps(reference)
    return f"""
    (() => {{
        const reference = {reference_literal};
        let target = null;
        if (reference.startsWith('/')) {{
            target = document.evaluate(
                reference, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
            ).singleNodeValue;
        }} else {{
            try {{ target = document.querySelector(reference); }} catch (error) {{ target = null; }}
        }}
        if (!target) return {{error: 'stale_element'}};
        const value = target.type === 'password' ? '' : (target.value ?? target.textContent ?? '');
        const errors = [];
        const described = (target.getAttribute('aria-describedby') || '').split(/\\s+/).filter(Boolean);
        for (const id of described) {{
            const node = document.getElementById(id);
            if (node && (node.innerText || node.textContent || '').trim())
                errors.push((node.innerText || node.textContent || '').trim());
        }}
        const selected = target.tagName === 'SELECT' && target.selectedIndex >= 0
            ? target.options[target.selectedIndex] : null;
        return {{
            tag: target.tagName || '', input_type: target.type || '', value,
            selected_text: selected ? selected.text : '', selected_value: selected ? selected.value : '',
            checked: target.checked === true, indeterminate: target.indeterminate === true,
            aria_checked: target.getAttribute('aria-checked') || '',
            aria_selected: target.getAttribute('aria-selected') || '',
            aria_pressed: target.getAttribute('aria-pressed') || '',
            validity: typeof target.checkValidity === 'function'
                ? (target.checkValidity() ? 'valid' : 'invalid') : 'not_yet_validated',
            errors, disabled: !!target.disabled,
            enabled: !target.disabled && target.getAttribute('aria-disabled') !== 'true',
            read_only: !!target.readOnly || target.getAttribute('aria-readonly') === 'true',
            visible: Boolean(target.getClientRects().length),
            value_present: String(value).trim().length > 0,
            framework_value: String(value).trim().length > 0 ? 'present' : 'absent',
            blurred: document.activeElement !== target,
            ready_for_submission: false
        }};
    }})()
    """


def combobox_options_script(max_options: int) -> str:
    return f"""
    const roots = [];
    for (const attr of ['aria-controls', 'aria-owns']) {{
        const ids = (this.getAttribute(attr) || '').split(/\\s+/).filter(Boolean);
        for (const id of ids) {{
            const root = document.getElementById(id);
            if (root) roots.push(root);
        }}
    }}
    roots.push(document);
    const seen = new Set();
    const out = [];
    function visible(el) {{
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }}
    for (const root of roots) {{
        for (const option of root.querySelectorAll('[role="option"]')) {{
            if (seen.has(option) || !visible(option)) continue;
            seen.add(option);
            const rect = option.getBoundingClientRect();
            out.push({{
                text: (option.innerText || option.textContent || '').trim(),
                value: option.getAttribute('data-value') || option.getAttribute('value') || option.id || '',
                selected: option.getAttribute('aria-selected') === 'true'
                    || option.getAttribute('data-state') === 'selected'
                    || option.classList.contains('selected'),
                disabled: option.getAttribute('aria-disabled') === 'true',
                id: option.id || '',
                bounds: {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}}
            }});
            if (out.length >= {max(1, min(max_options, 200))}) return out;
        }}
    }}
    return out;
    """


def select_options_script(max_options: int) -> str:
    return f"""
    if (this.tagName !== 'SELECT') {{
        return {{error: 'not_select', tag: this.tagName || ''}};
    }}
    const limit = {max(1, min(max_options, 200))};
    const options = [...this.options];
    const out = [];
    for (const option of options) {{
        out.push({{
            text: (option.text || '').trim(),
            value: option.value || '',
            label: option.label || '',
            selected: option.selected,
            disabled: option.disabled
        }});
        if (out.length >= limit) break;
    }}
    return {{
        options: out,
        count: options.length,
        partial: options.length > out.length,
        hidden_or_collapsed_options_count: Math.max(0, options.length - out.length)
    }};
    """


def form_snapshot_script(max_fields: int) -> str:
    return f"""
    const fields = [];
    const selectors = 'input, textarea, select, [contenteditable="true"], [role="combobox"]';
    function visible(el) {{
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }}
    function labelFor(el) {{
        const labels = [];
        if (el.id) {{
            for (const label of document.querySelectorAll(`label[for="${{CSS.escape(el.id)}}"]`)) {{
                labels.push(label.innerText.trim());
            }}
        }}
        const parent = el.closest('label');
        if (parent) labels.push(parent.innerText.trim());
        if (el.getAttribute('aria-label')) labels.push(el.getAttribute('aria-label'));
        return [...new Set(labels.filter(Boolean))];
    }}
    function nearestHeading(el) {{
        const section = el.closest('section, form, article, main');
        const heading = section ? section.querySelector('h1,h2,h3,h4,h5,h6,[role="heading"]') : null;
        return heading ? heading.innerText.trim() : '';
    }}
    function selectorHint(el) {{
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name.replace(/"/g, '\\\\"') + '"]';
        if (el.placeholder) {{
            return el.tagName.toLowerCase() + '[placeholder="' + el.placeholder.replace(/"/g, '\\\\"') + '"]';
        }}
        return el.tagName.toLowerCase();
    }}
    function errorsFor(el) {{
        const errors = [];
        const ids = (el.getAttribute('aria-describedby') || '').split(/\\s+/).filter(Boolean);
        for (const id of ids) {{
            const described = document.getElementById(id);
            if (described && visible(described)) errors.push(described.innerText.trim());
        }}
        let next = el.nextElementSibling;
        for (let i = 0; next && i < 3; i++, next = next.nextElementSibling) {{
            const marker = `${{next.className || ''}} ${{next.getAttribute('role') || ''}}`;
            if (visible(next) && /error|alert|invalid|required/i.test(marker)) errors.push(next.innerText.trim());
        }}
        return [...new Set(errors.filter(Boolean))];
    }}
    function valueFor(el) {{
        if (el.type === 'password') return '';
        return String(el.value ?? el.textContent ?? '');
    }}
    function optionLabels(el) {{
        if (el.tagName !== 'SELECT') return [];
        return [...el.options].slice(0, 100).map(option => ({{
            label: (option.text || option.label || '').trim(),
            value: option.value || '',
            selected: option.selected,
            disabled: option.disabled
        }}));
    }}
    function validityFor(el, errors) {{
        if (errors.length) return 'invalid';
        if (typeof el.checkValidity === 'function') return el.checkValidity() ? 'valid' : 'invalid';
        return 'not_yet_validated';
    }}
    for (const el of document.querySelectorAll(selectors)) {{
        if (fields.length >= {max(1, min(max_fields, 500))}) break;
        if (!visible(el)) continue;
        const rect = el.getBoundingClientRect();
        const value = valueFor(el);
        const errors = errorsFor(el);
        const selectedOption = el.tagName === 'SELECT' && el.selectedIndex >= 0
            ? el.options[el.selectedIndex] : null;
        const labels = labelFor(el);
        fields.push({{
            field_key: selectorHint(el) + '|' + (labels[0] || el.name || el.type || ''),
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            role: el.getAttribute('role') || '',
            name: el.name || '',
            visible: true,
            enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
            labels,
            placeholder: el.getAttribute('placeholder') || '',
            value_length: value.length,
            value_present: value.trim().length > 0,
            empty: value.trim().length === 0,
            value: '',
            required: !!el.required || el.getAttribute('aria-required') === 'true',
            disabled: !!el.disabled,
            read_only: !!el.readOnly || el.getAttribute('aria-readonly') === 'true',
            framework_value: 'unknown',
            framework_event: false,
            controlled_value_survived: false,
            blurred: false,
            checked: el.checked ?? null,
            indeterminate: el.indeterminate ?? false,
            selected_label: selectedOption ? (selectedOption.text || selectedOption.label || '').trim() : '',
            selected_value: selectedOption ? selectedOption.value || '' : '',
            option_labels: optionLabels(el),
            aria_checked: el.getAttribute('aria-checked') || '',
            aria_selected: el.getAttribute('aria-selected') || '',
            aria_pressed: el.getAttribute('aria-pressed') || '',
            validity: validityFor(el, errors),
            errors,
            blocker: ((el.required || el.getAttribute('aria-required') === 'true') && !value.trim())
                ? 'missing_required' : (errors.length ? 'invalid' : ''),
            ready_for_submission: ((!el.required && el.getAttribute('aria-required') !== 'true')
                || value.trim().length > 0)
                && errors.length === 0 && !el.disabled,
            nearest_heading: nearestHeading(el),
            selector_hint: selectorHint(el),
            bounds: {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}}
        }});
    }}
    return fields;
    """
