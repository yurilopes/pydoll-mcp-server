"""Interactive page summaries for agent observation."""

from __future__ import annotations

import uuid

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_array
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.dom.models import ElementBounds
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_float, get_object, get_string, require_json_object


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
        selector_hint = get_string(item, 'selector_hint', '')
        xpath_hint = get_string(item, 'xpath_hint', '')
        element_id = f'el_{uuid.uuid4().hex[:12]}'
        cache.store(
            ElementCacheEntry(
                element_id=element_id,
                tab_id=tab_id,
                document_generation=tab_info.document_generation,
                tag_name=get_string(item, 'tag', ''),
                text_summary=get_string(item, 'text', '')[:100],
                bounding_box=_bounds(item),
                selector_hint=selector_hint,
                xpath_hint=xpath_hint,
            )
        )
        item['element_id'] = element_id
        items.append(item)
    return {'success': True, 'items': items, 'count': len(items), 'partial': len(items) >= max_items}


def _bounds(item: JsonObject) -> ElementBounds:
    bounds = get_object(item, 'bounds', {})
    return {key: get_float(bounds, key, 0.0) for key in ('x', 'y', 'width', 'height')}


def _summary_script(max_items: int) -> str:
    limit = max(1, min(max_items, 500))
    return f"""
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
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name.replace(/"/g, '\\\\"') + '"]';
        if (el.placeholder) {{
            return el.tagName.toLowerCase() + '[placeholder="' + el.placeholder.replace(/"/g, '\\\\"') + '"]';
        }}
        return el.tagName.toLowerCase();
    }}
    function xpathHint(el) {{
        if (el.id) return '//*[@id="' + el.id.replace(/"/g, '&quot;') + '"]';
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
            selector_hint: selectorHint(el),
            xpath_hint: xpathHint(el),
            score
        }});
    }}
    out.sort((a, b) => b.score - a.score);
    return out;
    """
