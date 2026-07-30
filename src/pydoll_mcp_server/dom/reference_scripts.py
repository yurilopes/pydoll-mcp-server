"""Shared browser-side helpers for stable, non-sensitive element references."""

from __future__ import annotations

ELEMENT_REFERENCE_HELPERS = r"""
function normalizeVisibleText(value) {
    return String(value || '').normalize('NFC').trim().replace(/\s+/g, ' ');
}
function cssQuote(value) {
    return String(value || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}
function roleForReference(element) {
    const explicit = element.getAttribute('role');
    if (explicit) return explicit;
    const tag = element.tagName.toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a') return 'link';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
        const type = (element.type || '').toLowerCase();
        if (['checkbox', 'radio', 'button', 'submit'].includes(type)) return type;
        return 'textbox';
    }
    return '';
}
function labelForReference(element) {
    const doc = element.ownerDocument || document;
    const labels = [];
    if (element.id) {
        for (const label of doc.querySelectorAll('label[for="' + cssQuote(element.id) + '"]')) {
            labels.push(normalizeVisibleText(label.innerText || label.textContent));
        }
    }
    const parent = element.closest('label');
    if (parent) labels.push(normalizeVisibleText(parent.innerText || parent.textContent));
    const aria = element.getAttribute('aria-label');
    if (aria) labels.push(normalizeVisibleText(aria));
    return [...new Set(labels.filter(Boolean))].join(' | ');
}
function uniqueAttributeSelector(element) {
    const doc = element.ownerDocument || document;
    const tag = element.tagName.toLowerCase();
    const candidates = [];
    if (element.id) candidates.push('#' + (CSS.escape ? CSS.escape(element.id) : cssQuote(element.id)));
    const testId = element.getAttribute('data-testid');
    if (testId) candidates.push('[data-testid="' + cssQuote(testId) + '"]');
    if (element.name) {
        candidates.push(tag + '[name="' + cssQuote(element.name) + '"]');
        if (element.value && ['radio', 'checkbox'].includes((element.type || '').toLowerCase())) {
            candidates.unshift(
                tag + '[name="' + cssQuote(element.name) + '"][value="' + cssQuote(element.value) + '"]'
            );
        }
    }
    if (element.placeholder) candidates.push(tag + '[placeholder="' + cssQuote(element.placeholder) + '"]');
    for (const selector of candidates) {
        try {
            if (doc.querySelectorAll(selector).length === 1) return selector;
        } catch (error) {
            continue;
        }
    }
    return '';
}
function structuralSelector(element) {
    const unique = uniqueAttributeSelector(element);
    if (unique) return unique;
    const parts = [];
    let current = element;
    const doc = element.ownerDocument || document;
    while (current && current.nodeType === 1) {
        const tag = current.tagName.toLowerCase();
        let position = 1;
        let sibling = current.previousElementSibling;
        while (sibling) {
            if (sibling.tagName === current.tagName) position += 1;
            sibling = sibling.previousElementSibling;
        }
        parts.unshift(tag + ':nth-of-type(' + position + ')');
        if (current === doc.body) break;
        current = current.parentElement;
    }
    return parts.join(' > ') || element.tagName.toLowerCase();
}
function structuralXPath(element) {
    const doc = element.ownerDocument || document;
    if (element.id) {
        const id = '//*[@id="' + String(element.id).replace(/"/g, '&quot;') + '"]';
        try {
            const snapshot = doc.evaluate(
                id, doc, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
            );
            if (snapshot.snapshotLength === 1) {
                return id;
            }
        } catch (error) {
            return '';
        }
    }
    const parts = [];
    let current = element;
    while (current && current.nodeType === 1) {
        const tag = current.tagName.toLowerCase();
        let position = 1;
        let sibling = current.previousElementSibling;
        while (sibling) {
            if (sibling.tagName === current.tagName) position += 1;
            sibling = sibling.previousElementSibling;
        }
        parts.unshift(tag + '[' + position + ']');
        current = current.parentElement;
    }
    return '/' + parts.join('/');
}
function referenceMatchIndex(element) {
    const doc = element.ownerDocument || document;
    const base = uniqueAttributeSelector(element);
    if (!base) return 0;
    try {
        return [...doc.querySelectorAll(base)].indexOf(element);
    } catch (error) {
        return 0;
    }
}
function referenceFingerprint(element) {
    const rect = element.getBoundingClientRect();
    return {
        tag: element.tagName.toLowerCase(),
        role: roleForReference(element),
        label: labelForReference(element).slice(0, 160),
        name: String(element.getAttribute('name') || '').slice(0, 120),
        type: String(element.getAttribute('type') || '').slice(0, 40),
        text: normalizeVisibleText(element.innerText || element.textContent || '').slice(0, 160),
        parent_tag: element.parentElement ? element.parentElement.tagName.toLowerCase() : '',
        parent_role: element.parentElement ? String(element.parentElement.getAttribute('role') || '') : '',
        bounds: {
            x: Math.round(rect.x), y: Math.round(rect.y),
            width: Math.round(rect.width), height: Math.round(rect.height)
        }
    };
}
function elementReference(element) {
    return {
        selector_hint: structuralSelector(element),
        xpath_hint: structuralXPath(element),
        match_index: referenceMatchIndex(element),
        role: roleForReference(element),
        label: labelForReference(element),
        fingerprint: referenceFingerprint(element)
    };
}
"""


def reference_metadata_script() -> str:
    return f"""
{ELEMENT_REFERENCE_HELPERS}
return elementReference(this);
"""
