"""JavaScript snippets for form control tools."""

from __future__ import annotations


def fill_script(payload: str) -> str:
    return f"""
    const payload = {payload};
    const value = String(payload.value ?? '');
    const events = payload.events || [];
    const tag = this.tagName || '';
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
        changed: this.dataset ? this.dataset.changed === 'true' : false,
        blurred: this.dataset ? this.dataset.blurred === 'true' : false
    }};
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
                selected: option.getAttribute('aria-selected') === 'true',
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
    for (const el of document.querySelectorAll(selectors)) {{
        if (fields.length >= {max(1, min(max_fields, 500))}) break;
        if (!visible(el)) continue;
        const rect = el.getBoundingClientRect();
        fields.push({{
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            role: el.getAttribute('role') || '',
            name: el.name || '',
            labels: labelFor(el),
            placeholder: el.getAttribute('placeholder') || '',
            value_length: String(el.value ?? el.textContent ?? '').length,
            required: !!el.required || el.getAttribute('aria-required') === 'true',
            disabled: !!el.disabled,
            checked: el.checked ?? null,
            errors: errorsFor(el),
            nearest_heading: nearestHeading(el),
            selector_hint: selectorHint(el),
            bounds: {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}}
        }});
    }}
    return fields;
    """
