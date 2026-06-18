"""Verified interactions for native and ARIA choice controls."""

from __future__ import annotations

from pydoll.elements.web_element import WebElement

from pydoll_mcp_server.browser.script_utils import extract_script_object
from pydoll_mcp_server.json_types import JsonObject


async def set_choice_state(element: WebElement, checked: bool) -> JsonObject:
    desired = 'true' if checked else 'false'
    result = await element.execute_script(
        f"""
        const target = this;
        const type = (target.type || '').toLowerCase();
        const role = (target.getAttribute('role') || '').toLowerCase();
        const nativeChoice = target.tagName === 'INPUT' && ['radio','checkbox'].includes(type);
        const ariaChoice = ['radio','checkbox'].includes(role);
        const state = () => nativeChoice ? target.checked === true :
            target.getAttribute('aria-checked') === 'true';
        const visible = el => {{
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.display !== 'none' &&
                style.visibility !== 'hidden' && style.pointerEvents !== 'none';
        }};
        const diagnostic = {{
            tag: target.tagName.toLowerCase(), type, role, visible: visible(target),
            has_associated_label: false, strategies_attempted: [], observed_checked: state()
        }};
        if (!nativeChoice && !ariaChoice) return {{error:'not_checkable', diagnostic}};
        if (!{desired} && (type === 'radio' || role === 'radio'))
            return {{error:'radio_cannot_be_unchecked', diagnostic}};
        if (state() === {desired}) return {{checked:state(), verified:true, strategy_used:'already_selected'}};
        let label = target.closest('label');
        if (!label && target.id) label = document.querySelector('label[for="' + CSS.escape(target.id) + '"]');
        diagnostic.has_associated_label = Boolean(label);
        const attempt = (name, node) => {{
            if (!node || !visible(node)) return false;
            diagnostic.strategies_attempted.push(name);
            node.click();
            return state() === {desired};
        }};
        if (attempt('input', target)) return {{checked:state(), verified:true, strategy_used:'input'}};
        if (attempt('associated_label', label))
            return {{checked:state(), verified:true, strategy_used:'associated_label'}};
        const group = target.closest(
            'fieldset, [role="radiogroup"], [role="group"], ' +
            '.form-group, .radio-group, .checkbox-group'
        );
        const wanted = (label?.innerText || target.getAttribute('aria-label') || target.value || '').trim();
        if (group && wanted) {{
            const candidates = [...group.querySelectorAll('label, [role="radio"], [role="checkbox"]')]
                .filter(node => visible(node) &&
                    (node.innerText || node.getAttribute('aria-label') || '').trim() === wanted);
            if (candidates.length > 1) return {{error:'ambiguous_group_option', diagnostic}};
            if (attempt('group_text', candidates[0]))
                return {{checked:state(), verified:true, strategy_used:'group_text'}};
        }}
        diagnostic.observed_checked = state();
        return {{error:'choice_state_not_verified', diagnostic}};
        """,
        return_by_value=True,
    )
    return extract_script_object(result)
