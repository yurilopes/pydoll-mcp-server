"""Interactive page summaries for agent observation."""

from __future__ import annotations

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_array
from pydoll_mcp_server.dom.element_cache import cache_observed_element, get_element_cache
from pydoll_mcp_server.dom.reference_scripts import ELEMENT_REFERENCE_HELPERS
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, require_json_object


async def page_get_interactive_summary(
    client_id: str,
    tab_id: str,
    max_items: int = 120,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
        result = await tab_info.pydoll_tab.execute_script(_summary_script(max_items), return_by_value=True)
        raw_items = extract_script_array(result)
    except StructuredError as exc:
        return exc.to_dict()
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Interactive summary failed: {exc}',
            retryable=True,
        ).to_dict()

    cache = get_element_cache()
    items: JsonArray = []
    for value in raw_items:
        item = require_json_object(value, 'interactive item')
        element_id = cache_observed_element(
            cache,
            tab_id,
            tab_info.document_generation,
            item,
        )
        item['element_id'] = element_id
        items.append(item)
    return {'success': True, 'items': items, 'count': len(items), 'partial': len(items) >= max_items}


def _summary_script(max_items: int) -> str:
    limit = max(1, min(max_items, 500))
    return f"""
    {ELEMENT_REFERENCE_HELPERS}
    const out = [];
    const selectors = [
        'button','a[href]','input','textarea','select','label',
        '[role="button"]','[role="link"]','[role="tab"]','[role="checkbox"]',
        '[role="radio"]','[role="combobox"]','[role="textbox"]','[tabindex]'
    ].join(',');
    function norm(value) {{ return (value || '').trim().replace(/\\s+/g, ' '); }}
    function visible(el) {{
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }}
    function roleOf(el) {{
        if (el.getAttribute('role')) return el.getAttribute('role');
        if (el.tagName === 'BUTTON') return 'button';
        if (el.tagName === 'A') return 'link';
        if (el.tagName === 'SELECT') return 'combobox';
        if (el.tagName === 'TEXTAREA') return 'textbox';
        if (el.tagName === 'INPUT') {{
            if (el.type === 'checkbox' || el.type === 'radio') return el.type;
            return 'textbox';
        }}
        return '';
    }}
    function labelsFor(el) {{
        const labels = [];
        if (el.id) {{
            for (const label of document.querySelectorAll(`label[for="${{CSS.escape(el.id)}}"]`)) {{
                labels.push(norm(label.innerText));
            }}
        }}
        const parent = el.closest('label');
        if (parent) labels.push(norm(parent.innerText));
        return [...new Set(labels.filter(Boolean))];
    }}
    function nameOf(el) {{
        return norm(el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('title') ||
            labelsFor(el).join(' ') || el.value || el.innerText || el.textContent || el.placeholder || '');
    }}
    function nearestHeading(el) {{
        const section = el.closest('section, form, article, main, aside, nav');
        const heading = section ? section.querySelector('h1,h2,h3,h4,h5,h6,[role="heading"]') : null;
        return heading ? norm(heading.innerText) : '';
    }}
    function selectorHint(el) {{
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.getAttribute('data-testid')) return '[data-testid="' + el.getAttribute('data-testid') + '"]';
        if (el.name && el.value && ['radio','checkbox'].includes(el.type || ''))
            return el.tagName.toLowerCase() + '[name="' + el.name.replace(/"/g, '\\\\"') +
                '"][value="' + el.value.replace(/"/g, '\\\\"') + '"]';
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name.replace(/"/g, '\\\\"') + '"]';
        if (el.placeholder) {{
            return el.tagName.toLowerCase() + '[placeholder="' + el.placeholder.replace(/"/g, '\\\\"') + '"]';
        }}
        return el.tagName.toLowerCase();
    }}
    function xpathHint(el) {{
        if (el.id) return '//*[@id="' + el.id.replace(/"/g, '&quot;') + '"]';
        if (el.name && el.value && ['radio','checkbox'].includes(el.type || ''))
            return '//' + el.tagName.toLowerCase() + '[@name="' +
                el.name.replace(/"/g, '&quot;') + '" and @value="' +
                el.value.replace(/"/g, '&quot;') + '"]';
        if (el.name) return '//' + el.tagName.toLowerCase() + '[@name="' + el.name.replace(/"/g, '&quot;') + '"]';
        return '';
    }}
    for (const el of document.querySelectorAll(selectors)) {{
        if (out.length >= {limit}) break;
        if (!visible(el)) continue;
        const rect = el.getBoundingClientRect();
        const labels = labelsFor(el);
        const role = roleOf(el);
        const name = nameOf(el);
        const text = norm(el.innerText || el.textContent || '');
        const enabled = !el.disabled && el.getAttribute('aria-disabled') !== 'true';
        const editable = el.isContentEditable || ['INPUT','TEXTAREA','SELECT'].includes(el.tagName);
        const score = (enabled ? 100 : 0) + (role ? 40 : 0) + (name ? 20 : 0);
        const reference = elementReference(el);
        out.push({{
            tag: el.tagName.toLowerCase(),
            role,
            name,
            text,
            labels,
            nearest_heading: nearestHeading(el),
            section_label: el.closest('section, form, article')?.getAttribute('aria-label') || '',
            bounds: {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}},
            enabled,
            editable,
            checked: el.checked ?? null,
            selected: el.selected ?? null,
            form: el.form ? (el.form.id || el.form.getAttribute('aria-label') || '') : '',
            selector_hint: reference.selector_hint,
            xpath_hint: reference.xpath_hint,
            match_index: reference.match_index,
            fingerprint: reference.fingerprint,
            score
        }});
    }}
    out.sort((a, b) => b.score - a.score);
    return out;
    """
