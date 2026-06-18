"""JavaScript fragments for active surface detection."""

from __future__ import annotations

from pydoll_mcp_server.tools.surface_group_scripts import GROUPED_FIELDS_SCRIPT


def surface_script(payload_json: str) -> str:
    return f"""
const opts = {payload_json};
const scope = opts.scope;
const maxFields = opts.max_fields;
const maxControls = opts.max_controls;
const includeValues = opts.include_values;
const textMaxChars = opts.text_max_chars;
const IS_SENSITIVE = new Set(['password','ssn','credit','card','token','secret','pin']);
const FIELD_ROLES = new Set(['textbox','combobox','radio','checkbox','switch']);
const ACTION_ROLES = new Set(['button','link','tab','menuitem']);

function norm(v) {{ return (v || '').trim().replace(/\\s+/g, ' '); }}
function clipText(v) {{
    const text = norm(v);
    const max = Math.max(50, Math.min(Number(textMaxChars) || 300, 2000));
    return {{ text: text.slice(0, max), text_length: text.length, truncated: text.length > max }};
}}
function visible(el) {{
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity) > 0;
}}
function inViewport(el) {{
    const rect = el.getBoundingClientRect();
    return rect.right >= 0 && rect.bottom >= 0 && rect.left <= innerWidth && rect.top <= innerHeight;
}}
function selectorHint(el) {{
    if (el.id) return '#' + CSS.escape(el.id);
    if (el.getAttribute('data-testid')) return '[data-testid="' + el.getAttribute('data-testid') + '"]';
    if (el.name && el.value && ['radio','checkbox'].includes(el.type || '')) return el.tagName.toLowerCase() + '[name="' + el.name.replace(/"/g, '\\\\"') + '"][value="' + el.value.replace(/"/g, '\\\\"') + '"]';
    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name.replace(/"/g, '\\\\"') + '"]';
    return '';
}}
function xpathHint(el) {{
    if (el.id) return '//*[@id="' + el.id.replace(/"/g, '&quot;') + '"]';
    if (el.name && el.value && ['radio','checkbox'].includes(el.type || '')) return '//' + el.tagName.toLowerCase() + '[@name="' + el.name.replace(/"/g, '&quot;') + '" and @value="' + el.value.replace(/"/g, '&quot;') + '"]';
    return '';
}}
function isSensitive(el) {{
    const str = (el.name + el.getAttribute('autocomplete') + el.placeholder + (el.getAttribute('aria-label') || '')).toLowerCase();
    for (const word of IS_SENSITIVE) {{ if (str.includes(word)) return true; }}
    return el.tagName === 'INPUT' && el.type === 'password';
}}
function fieldPreview(el) {{
    if (!includeValues) return null;
    if (isSensitive(el)) return {{ redacted: true }};
    const val = (el.value||'').slice(0, 200);
    return {{ value_preview: val, value_length: val.length, redacted: false }};
}}
function fieldMeta(el) {{
    function labelOf(e) {{
        if (e.id) {{
            const lbl = document.querySelector('label[for="' + CSS.escape(e.id) + '"]');
            if (lbl) return norm(lbl.innerText);
        }}
        return norm(e.closest('label')?.innerText || e.getAttribute('aria-label') || e.placeholder || '');
    }}
    const selectedOption = el.tagName === 'SELECT' && el.selectedIndex >= 0 ? el.options?.[el.selectedIndex] : null;
    const optionCount = el.tagName === 'SELECT' ? el.options.length : 0;
    return {{
        tag: el.tagName.toLowerCase(),
        type: el.type || '',
        role: el.getAttribute('role') || '',
        label: labelOf(el),
        name: el.name || '',
        placeholder: el.placeholder || '',
        required: el.required || el.getAttribute('aria-required') === 'true',
        disabled: el.disabled,
        checked: el.checked ?? null,
        selected: selectedOption ? norm(selectedOption.text || '') : null,
        selected_value: selectedOption ? selectedOption.value || '' : null,
        option_count: optionCount,
        hidden_or_collapsed_options_count: optionCount,
        selector_hint: selectorHint(el),
        xpath_hint: xpathHint(el),
        errors: []
    }};
}}
function controlMeta(el) {{
    const role = el.getAttribute('role') || '';
    const clippedName = clipText(el.getAttribute('aria-label') || el.innerText || el.textContent || el.value || el.placeholder || '');
    const clippedText = clipText(el.innerText || el.textContent || el.value || '');
    return {{
        tag: el.tagName.toLowerCase(),
        role,
        name: clippedName.text,
        text: clippedText.text,
        text_length: clippedText.text_length,
        truncated: clippedText.truncated,
        enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
        selector_hint: selectorHint(el),
        xpath_hint: xpathHint(el)
    }};
}}
function actionMeta(el) {{
    const meta = controlMeta(el);
    return {{
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute('role') || 'button',
        name: meta.name,
        text: meta.text,
        text_length: meta.text_length,
        truncated: meta.truncated,
        enabled: true,
        selector_hint: selectorHint(el),
        xpath_hint: xpathHint(el),
        type: el.type || ''
    }};
}}
function compactContainerText(el) {{
    const clone = el.cloneNode(true);
    for (const noisy of clone.querySelectorAll('select, option, input, textarea, button, a, [role="option"], [role="button"], [role="link"]')) {{
        noisy.remove();
    }}
    return clone.innerText || clone.textContent || '';
}}
function containerMeta(el) {{
    const role = el.getAttribute('role') || '';
    const clippedName = clipText(el.getAttribute('aria-label') || '');
    const clippedText = clipText(compactContainerText(el));
    return {{
        tag: el.tagName.toLowerCase(),
        role,
        name: clippedName.text,
        text_excerpt: clippedText.text,
        text_length: clippedText.text_length,
        truncated: clippedText.truncated,
        selector_hint: selectorHint(el),
        xpath_hint: xpathHint(el)
    }};
}}
function isFieldElement(el) {{
    const tag = el.tagName;
    const role = el.getAttribute('role') || '';
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable || FIELD_ROLES.has(role);
}}
function isActionElement(el) {{
    const tag = el.tagName;
    const role = el.getAttribute('role') || '';
    if (tag === 'BUTTON' || tag === 'A') return true;
    if (tag === 'INPUT') return ['button','submit','reset'].includes((el.type || '').toLowerCase());
    return ACTION_ROLES.has(role);
}}
function isContainerElement(el) {{
    const tag = el.tagName;
    const role = el.getAttribute('role') || '';
    if (['DIALOG','FORM','FIELDSET','SECTION','ARTICLE'].includes(tag)) return true;
    if (['dialog','group','region','progressbar','form'].includes(role)) return true;
    return /step|progress|modal|dialog|section|group/i.test(el.className || '');
}}
function findTopmostDialog() {{
    const candidates = [];
    for (const el of document.querySelectorAll('dialog, [role="dialog"], [aria-modal="true"]')) {{
        if (!visible(el)) continue;
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        const zIndex = parseInt(style.zIndex) || 0;
        candidates.push({{ el, zIndex, area: rect.width * rect.height }});
    }}
    candidates.sort((a, b) => b.zIndex - a.zIndex || b.area - a.area);
    return candidates[0]?.el || null;
}}
function findModalOverlay() {{
    for (const el of document.querySelectorAll('[class*="overlay"],[class*="backdrop"],[class*="modal"]')) {{
        const style = getComputedStyle(el);
        if (style.position === 'fixed' && visible(el)) {{
            const modal = el.querySelector('[role="dialog"], dialog, [aria-modal="true"], .modal, [class*="modal"]');
            if (modal && visible(modal)) return modal;
        }}
    }}
    return null;
}}
let surface = null;
let surfaceScope = scope;
let surfaceReason = '';
let surfaceTag = '';
let surfaceRole = '';
let surfaceLabel = '';
let surfaceSelector = '';

if (scope === 'auto' || scope === 'modal' || scope === 'dialog') {{
    const dialog = findTopmostDialog() || findModalOverlay();
    if (dialog) {{
        surface = dialog;
        surfaceScope = dialog.getAttribute('aria-modal') === 'true' ? 'modal' : 'dialog';
        surfaceReason = dialog.getAttribute('aria-modal') === 'true' ? 'topmost aria-modal dialog' : 'topmost visible dialog';
        surfaceTag = dialog.tagName.toLowerCase();
        surfaceRole = dialog.getAttribute('role') || 'dialog';
        surfaceLabel = dialog.getAttribute('aria-label') || '';
        surfaceSelector = selectorHint(dialog);
    }} else if (scope !== 'auto') {{
        return {{ surface_scope: scope, surface_reason: 'no visible ' + scope + ' found', fields: [], controls: [], errors: [], warnings: ['No visible ' + scope + ' element found.'] }};
    }}
}}
if (!surface && (scope === 'auto' || scope === 'form')) {{
    const forms = [...document.querySelectorAll('form')].filter(visible);
    if (forms.length) {{
        surface = forms[0];
        surfaceScope = 'form';
        surfaceReason = 'first visible form';
        surfaceTag = 'form';
        surfaceRole = 'form';
        surfaceLabel = forms[0].getAttribute('aria-label') || '';
        surfaceSelector = selectorHint(forms[0]);
    }} else if (scope !== 'auto') {{
        return {{ surface_scope: scope, surface_reason: 'no visible form found', fields: [], controls: [], errors: [], warnings: ['No visible form element found.'] }};
    }}
}}
if (!surface && (scope === 'auto' || scope === 'main')) {{
    const main = document.querySelector('main, [role="main"]');
    if (main && visible(main)) {{
        surface = main;
        surfaceScope = 'main';
        surfaceReason = 'main element';
        surfaceTag = main.tagName.toLowerCase();
        surfaceRole = 'main';
        surfaceLabel = '';
        surfaceSelector = selectorHint(main);
    }} else if (scope !== 'auto') {{
        return {{ surface_scope: scope, surface_reason: 'no visible main element found', fields: [], controls: [], errors: [], warnings: ['No visible main element found.'] }};
    }}
}}
if (!surface && scope === 'auto') {{
    surface = document.body;
    surfaceScope = 'viewport';
    surfaceReason = 'body fallback';
    surfaceTag = 'body';
    surfaceRole = '';
    surfaceLabel = '';
    surfaceSelector = '';
}}
if (!surface && scope === 'viewport') {{
    surface = document.body;
    surfaceScope = 'viewport';
    surfaceReason = 'viewport scope';
    surfaceTag = 'body';
    surfaceRole = '';
    surfaceLabel = '';
    surfaceSelector = '';
}}
if (!surface && scope === 'active_element_context') {{
    let active = document.activeElement;
    if (active) {{
        surface = active.closest('form, [role="dialog"], fieldset, section, article') || document.body;
        surfaceScope = 'active_element_context';
        surfaceReason = 'active element context';
        surfaceTag = surface.tagName.toLowerCase();
        surfaceRole = surface.getAttribute('role') || '';
        surfaceLabel = surface.getAttribute('aria-label') || '';
        surfaceSelector = selectorHint(surface);
    }}
}}
if (!surface) {{
    return {{ surface_scope: scope, surface_reason: 'unable to determine surface', fields: [], controls: [], errors: [], warnings: ['Unable to determine active surface for scope: ' + scope] }};
}}
{GROUPED_FIELDS_SCRIPT}
function collectControls() {{
    const controls = [];
    const controlNodes = surface.querySelectorAll('button, a[href], [role="button"], [role="link"], [role="tab"], [role="menuitem"], input[type="button"], input[type="submit"], input[type="reset"]');
    for (const el of controlNodes) {{
        if (controls.length >= maxControls) break;
        if (!visible(el)) continue;
        if (surfaceScope === 'viewport' && !inViewport(el)) continue;
        if (el.type === 'hidden') continue;
        if (isFieldElement(el) && !isActionElement(el)) continue;
        controls.push(controlMeta(el));
    }}
    return controls;
}}
function collectContainers() {{
    const containers = [];
    const nodes = surface.querySelectorAll('dialog, form, fieldset, section, article, [role="dialog"], [role="group"], [role="region"], [role="progressbar"], [class*="step"], [class*="progress"]');
    for (const el of nodes) {{
        if (containers.length >= 20) break;
        if (!visible(el)) continue;
        if (surfaceScope === 'viewport' && !inViewport(el)) continue;
        if (isFieldElement(el) || isActionElement(el)) continue;
        containers.push(containerMeta(el));
    }}
    if (containers.length === 0 && isContainerElement(surface)) containers.push(containerMeta(surface));
    return containers;
}}
function findPrimaryAction() {{
    const dismissWords = /^(close|fechar|cancel|cancelar|dismiss|discard|descartar|x)$/i;
    const primarySelectors = [
        'button.primary', 'button.btn-primary', 'button[type="submit"]',
        'input[type="submit"]', '.btn.primary',
    ];
    for (const sel of primarySelectors) {{
        for (const el of surface.querySelectorAll(sel)) {{
            if (!visible(el)) continue;
            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
            if (dismissWords.test(norm(el.innerText || el.value || el.getAttribute('aria-label') || ''))) continue;
            return actionMeta(el);
        }}
    }}
    const fallbackOrder = ['button','input[type="submit"]','input[type="button"]','a[role="button"]','[role="button"]'];
    const primaryWords = /^(next|continue|avançar|avancar|prosseguir|submit|enviar|apply|candidatar-se)$/i;
    for (const sel of fallbackOrder) {{
        for (const el of surface.querySelectorAll(sel)) {{
            if (!visible(el)) continue;
            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
            const text = norm(el.innerText || el.value || '');
            if (dismissWords.test(text)) continue;
            if (!primaryWords.test(text)) continue;
            return actionMeta(el);
        }}
    }}
    for (const sel of fallbackOrder) {{
        for (const el of surface.querySelectorAll(sel)) {{
            if (!visible(el)) continue;
            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
            if (dismissWords.test(norm(el.innerText || el.value || el.getAttribute('aria-label') || ''))) continue;
            return actionMeta(el);
        }}
    }}
    return null;
}}
function findSecondaryActions() {{
    const sec = [];
    for (const el of surface.querySelectorAll('button, a[href], [role="button"]')) {{
        if (sec.length >= 5) break;
        if (!visible(el)) continue;
        if (el.disabled) continue;
        const text = norm(el.innerText || el.value || '');
        const isSecondary = el.classList.contains('secondary') || el.classList.contains('btn-secondary') || el.classList.contains('no-op-btn') || /^(back|voltar|cancel|cancelar|close|fechar)$/i.test(text);
        if (isSecondary) {{
            sec.push(actionMeta(el));
        }}
    }}
    return sec;
}}
function findProgress() {{
    const indicators = surface.querySelectorAll('[class*="step"], [class*="progress"], [role="progressbar"]');
    for (const el of indicators) {{
        if (!visible(el)) continue;
        const t = norm(el.innerText || el.textContent || '');
        const match = t.match(/step\\s*(\\d+)\\s*(of|\\/)\\s*(\\d+)/i);
        if (match) {{
            const clipped = clipText(t);
            return {{ text: clipped.text, text_length: clipped.text_length, truncated: clipped.truncated, current: parseInt(match[1]), total: parseInt(match[3]) }};
        }}
        if (t.includes('Step')) {{
            const clipped = clipText(t);
            return {{ text: clipped.text, text_length: clipped.text_length, truncated: clipped.truncated, current: null, total: null }};
        }}
    }}
    return {{}};
}}
function findErrors() {{
    const errs = [];
    for (const el of surface.querySelectorAll('[class*="error"]:not([style*="display: none"]), [role="alert"]')) {{
        if (!visible(el)) continue;
        const clipped = clipText(el.innerText || '');
        errs.push({{ element: el.tagName.toLowerCase(), text: clipped.text, text_length: clipped.text_length, truncated: clipped.truncated, class: el.className }});
    }}
    return errs;
}}
function findPendingRequired(fields) {{
    const pending = [];
    for (const field of fields) {{
        if ((field.type === 'radio_group' || field.type === 'checkbox_group') && field.required && !field.checked) {{
            pending.push({{ type: field.type, label: field.label, name: field.name, selector_hint: field.selector_hint, xpath_hint: field.xpath_hint }});
        }}
    }}
    for (const el of surface.querySelectorAll('input[required], textarea[required], select[required], [aria-required="true"]')) {{
        if (el.type === 'hidden' || el.type === 'file') continue;
        if (!visible(el)) continue;
        if (el.type === 'radio' || el.type === 'checkbox' || el.getAttribute('role') === 'radio' || el.getAttribute('role') === 'checkbox') continue;
        const val = (el.value || '').trim();
        if (!val) {{
            pending.push({{
                label: norm(el.closest('label')?.innerText || el.getAttribute('aria-label') || el.placeholder || ''),
                selector_hint: selectorHint(el),
                xpath_hint: xpathHint(el)
            }});
        }}
    }}
    return pending;
}}
function findReviewText() {{
    const texts = [];
    for (const el of surface.querySelectorAll('table, .review, [class*="review"]')) {{
        if (!visible(el)) continue;
        const t = norm(el.innerText || el.textContent || '');
        if (t) texts.push(clipText(t).text);
        if (texts.length >= 3) break;
    }}
    return texts;
}}
function activeElementInfo() {{
    const el = document.activeElement;
    if (!el) return {{}};
    return {{
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute('role') || '',
        name: norm(el.getAttribute('aria-label') || el.value || el.innerText || ''),
        type: el.type || ''
    }};
}}
const fields = collectFields();
const controls = collectControls();
const containers = collectContainers();
const primaryAction = findPrimaryAction();
const secondaryActions = findSecondaryActions();
const progress = findProgress();
const errors = findErrors();
const pendingRequired = findPendingRequired(fields);
const reviewText = findReviewText();
const activeElement = activeElementInfo();

return {{
    surface_scope: surfaceScope,
    surface_reason: surfaceReason,
    surface_tag: surfaceTag,
    surface_role: surfaceRole,
    surface_label: surfaceLabel,
    surface_selector: surfaceSelector,
    fields,
    controls,
    containers,
    primary_action: primaryAction,
    secondary_actions: secondaryActions,
    progress,
    errors,
    pending_required: pendingRequired,
    review_text: reviewText,
    active_element: activeElement,
    warnings: []
}};
"""
