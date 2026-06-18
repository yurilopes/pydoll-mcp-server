"""JavaScript fragment for grouped fields on active surfaces."""

from __future__ import annotations

GROUPED_FIELDS_SCRIPT = r"""
function collectFields() {
    const fields = [];
    const choiceGroups = new Map();
    const nodes = surface.querySelectorAll(
        'input, textarea, select, [contenteditable="true"], [role="textbox"], ' +
        '[role="combobox"], [role="radio"], [role="checkbox"], [role="switch"]'
    );
    for (const el of nodes) {
        if (!visible(el) || (surfaceScope === 'viewport' && !inViewport(el))) continue;
        if (['hidden','file','button','submit','reset'].includes((el.type || '').toLowerCase())) continue;
        const role = el.getAttribute('role') || '';
        const isRadio = el.type === 'radio' || role === 'radio';
        const isCheckbox = el.type === 'checkbox' || role === 'checkbox';
        const choiceType = isRadio ? 'radio' : (isCheckbox ? 'checkbox' : '');
        if (choiceType) {
            const container = el.closest(
                'fieldset, [role="radiogroup"], [role="group"], ' +
                '.form-group, .radio-group, .checkbox-group'
            );
            const key = choiceType + ':' + (el.name || container?.id || selectorHint(container || el));
            const group = choiceGroups.get(key) || { type: choiceType, container, elements: [] };
            group.elements.push(el);
            choiceGroups.set(key, group);
            continue;
        }
        if (fields.length >= maxFields) continue;
        const meta = fieldMeta(el);
        const preview = fieldPreview(el);
        const entry = { ...meta, value_length: (el.value||'').length };
        if (preview) Object.assign(entry, preview);
        const error = el.closest('[class*="field"]')?.querySelector('[class*="error"], [role="alert"]');
        if (error && visible(error)) entry.errors = [norm(error.innerText || '')];
        fields.push(entry);
    }
    for (const group of choiceGroups.values()) {
        if (fields.length >= maxFields) break;
        const first = group.elements[0];
        const optionLabel = (el) => norm(
            (el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]')?.innerText : '') ||
            el.closest('label')?.innerText || el.getAttribute('aria-label') || el.value || ''
        );
        if (group.type === 'checkbox' && group.elements.length === 1 && !first.name) {
            const meta = fieldMeta(first);
            meta.label = optionLabel(first);
            fields.push(meta);
            continue;
        }
        const directHeading = ':scope > legend, :scope > h1, :scope > h2, :scope > h3, ' +
            ':scope > h4, :scope > label';
        const parentHeading = ':scope > label, :scope > legend, :scope > h1, :scope > h2, ' +
            ':scope > h3, :scope > h4';
        const heading = group.container?.querySelector(directHeading) ||
            group.container?.parentElement?.querySelector(parentHeading);
        const options = group.elements.map(el => ({
            tag: el.tagName.toLowerCase(),
            type: group.type,
            role: el.getAttribute('role') || group.type,
            label: optionLabel(el),
            value: el.value || '',
            checked: el.checked === true || el.getAttribute('aria-checked') === 'true',
            disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
            selector_hint: selectorHint(el),
            xpath_hint: xpathHint(el)
        }));
        const selected = options.find(option => option.checked) || null;
        const required = group.elements.some(
            el => el.required || el.getAttribute('aria-required') === 'true'
        ) || group.container?.getAttribute('aria-required') === 'true';
        fields.push({
            tag: group.container?.tagName.toLowerCase() || 'div',
            type: group.type + '_group',
            role: group.container?.getAttribute('role') ||
                (group.type === 'radio' ? 'radiogroup' : 'group'),
            label: norm(heading?.innerText || group.container?.getAttribute('aria-label') || first.name || ''),
            name: first.name || '',
            required,
            checked: selected !== null,
            selected_option: selected?.label || null,
            options,
            selector_hint: selectorHint(group.container || first),
            xpath_hint: xpathHint(group.container || first),
            errors: []
        });
    }
    return fields;
}
"""
