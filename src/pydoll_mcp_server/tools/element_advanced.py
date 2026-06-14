"""Agent-friendly semantic discovery and advanced element interactions."""

from __future__ import annotations

import json
from typing import Any

from pydoll.constants import Key

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_value
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.security.policy import is_sensitive_field
from pydoll_mcp_server.tools.element_resolver import _resolve_element
from pydoll_mcp_server.tools.elements import element_find


async def element_get_state(client_id: str, tab_id: str, element_id: str) -> dict[str, Any]:
    resolved = await _get(client_id, tab_id, element_id)
    if isinstance(resolved, dict):
        return resolved
    result = await resolved.execute_script(
        """return {visible:!!(this.offsetWidth||this.offsetHeight||this.getClientRects().length),
        enabled:!this.disabled,checked:!!this.checked,selected:!!this.selected,
        editable:!!(this.isContentEditable||['INPUT','TEXTAREA','SELECT'].includes(this.tagName)),
        focused:document.activeElement===this,value:this.value??null,type:this.type||''};""",
        return_by_value=True,
    )
    state = extract_script_value(result) or {}
    if is_sensitive_field(str(state.get('type', ''))) and state.get('value') is not None:
        state['value'] = '[REDACTED]'
        state['redacted'] = True
    return {'success': True, 'element_id': element_id, 'state': state}


async def element_select_option(
    client_id: str, tab_id: str, element_id: str, values: list[str] | None = None,
    labels: list[str] | None = None, indexes: list[int] | None = None,
) -> dict[str, Any]:
    payload = json.dumps({'values': values or [], 'labels': labels or [], 'indexes': indexes or []})
    script = f"""const q={payload};if(this.tagName!=='SELECT')return {{error:'not_select'}};
    const opts=[...this.options];let n=0;for(const o of opts){{const yes=q.values.includes(o.value)||
    q.labels.includes(o.label)||q.indexes.includes(o.index);if(this.multiple)o.selected=yes;else if(yes)o.selected=true;
    if(yes)n++;}}this.dispatchEvent(new Event('input',{{bubbles:true}}));
    this.dispatchEvent(new Event('change',{{bubbles:true}}));return {{selected:n,value:this.value}};"""
    return await _mutate(client_id, tab_id, element_id, script, 'selected')


async def element_check(client_id: str, tab_id: str, element_id: str) -> dict[str, Any]:
    return await _set_checked(client_id, tab_id, element_id, True)


async def element_uncheck(client_id: str, tab_id: str, element_id: str) -> dict[str, Any]:
    return await _set_checked(client_id, tab_id, element_id, False)


async def element_hover(client_id: str, tab_id: str, element_id: str) -> dict[str, Any]:
    return await _mutate(
        client_id, tab_id, element_id,
        """this.scrollIntoView({block:'center'});for(const t of ['mouseover','mouseenter','mousemove'])
        this.dispatchEvent(new MouseEvent(t,{bubbles:true,view:window}));return true;""", 'hovered',
    )


async def element_scroll_into_view(client_id: str, tab_id: str, element_id: str) -> dict[str, Any]:
    return await _mutate(
        client_id, tab_id, element_id,
        "this.scrollIntoView({block:'center',inline:'nearest'});return true;", 'scrolled',
    )


async def element_find_by_role(
    client_id: str, tab_id: str, role: str, name: str = '', find_all: bool = False,
) -> dict[str, Any]:
    selector = f'[role="{_css(role)}"]'
    if name:
        return await element_find(client_id, tab_id, f'//*[@role={_xpath(role)} and contains(normalize-space(.),'
                                  f' {_xpath(name)})]', 'xpath', find_all=find_all)
    return await element_find(client_id, tab_id, selector, find_all=find_all)


async def element_find_by_text(
    client_id: str, tab_id: str, text: str, exact: bool = False, find_all: bool = False,
) -> dict[str, Any]:
    condition = f'normalize-space(.)={_xpath(text)}' if exact else f'contains(normalize-space(.), {_xpath(text)})'
    return await element_find(client_id, tab_id, f'//*[{condition}]', 'xpath', find_all=find_all)


async def element_find_by_label(client_id: str, tab_id: str, label: str) -> dict[str, Any]:
    query = (
        f'//*[@id=//label[contains(normalize-space(.), {_xpath(label)})]/@for]'
        f' | //label[contains(normalize-space(.), {_xpath(label)})]//*[self::input or self::textarea or self::select]'
    )
    return await element_find(client_id, tab_id, query, 'xpath')


async def element_find_by_placeholder(client_id: str, tab_id: str, placeholder: str) -> dict[str, Any]:
    return await element_find(client_id, tab_id, f'[placeholder="{_css(placeholder)}"]')


async def element_find_by_test_id(client_id: str, tab_id: str, test_id: str) -> dict[str, Any]:
    return await element_find(client_id, tab_id, f'[data-testid="{_css(test_id)}"]')


async def keyboard_press(
    client_id: str, tab_id: str, key: str, modifiers: list[str] | None = None, presses: int = 1,
) -> dict[str, Any]:
    try:
        tab = get_registry().get_tab(client_id, tab_id)._pydoll_tab
        target = Key[key.upper()]
        modifier_keys = [Key[item.upper()] for item in modifiers or []]
    except (StructuredError, KeyError) as exc:
        return StructuredError(ErrorCode.INVALID_INPUT, f'Unknown tab or key: {exc}').to_dict()
    try:
        async with tab_operation_lock(tab_id):
            for _ in range(max(1, min(presses, 100))):
                if modifier_keys:
                    if len(modifier_keys) == 1:
                        await tab.keyboard.hotkey(modifier_keys[0], target)
                    else:
                        await tab.keyboard.hotkey(modifier_keys[0], modifier_keys[1], target)
                else:
                    await tab.keyboard.press(target)
        return {'success': True, 'key': key, 'presses': presses}
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Keyboard press failed: {exc}', retryable=True).to_dict()


async def _set_checked(client_id: str, tab_id: str, element_id: str, checked: bool) -> dict[str, Any]:
    script = f"""if(!['checkbox','radio'].includes(this.type))return {{error:'not_checkable'}};
    if(this.checked!=={str(checked).lower()}){{this.checked={str(checked).lower()};
    this.dispatchEvent(new Event('input',{{bubbles:true}}));this.dispatchEvent(new Event('change',{{bubbles:true}}));}}
    return {{checked:this.checked}};"""
    return await _mutate(client_id, tab_id, element_id, script, 'checked')


async def _get(client_id: str, tab_id: str, element_id: str) -> Any:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await _resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
    return element


async def _mutate(client_id: str, tab_id: str, element_id: str, script: str, action: str) -> dict[str, Any]:
    element = await _get(client_id, tab_id, element_id)
    if isinstance(element, dict):
        return element
    try:
        async with tab_operation_lock(tab_id):
            result = extract_script_value(await element.execute_script(script, return_by_value=True))
        if isinstance(result, dict) and result.get('error'):
            return StructuredError(ErrorCode.INVALID_INPUT, str(result['error'])).to_dict()
        return {'success': True, 'element_id': element_id, action: result}
    except Exception as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'{action} failed: {exc}', retryable=True).to_dict()


def _css(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _xpath(value: str) -> str:
    return json.dumps(value)
