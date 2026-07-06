"""Enhanced click with effect observation and stale element re-resolution."""

from __future__ import annotations

import asyncio
import time

from pydoll.browser.tab import Tab
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException
from pydoll.protocol.input.types import MouseButton

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.pydoll_compat import get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_script_bool,
    extract_script_object,
    extract_script_string,
)
from pydoll_mcp_server.config import get_timeout_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_bool, get_object, get_string
from pydoll_mcp_server.tools.choice_interactions import set_choice_state
from pydoll_mcp_server.tools.element_resolver import resolve_element

VALID_STRATEGIES = frozenset({'native', 'center_mouse', 'dispatch_pointer_sequence', 'trusted_fallback_if_safe'})


async def element_click_enhanced(
    client_id: str,
    tab_id: str,
    element_id: str,
    timeout: float | None = None,
    click_strategy: str = 'native',
    expect_dialog: bool = False,
    expect_url_change: bool = False,
    expect_text: str = '',
    expect_selector: str = '',
    expect_network_idle: bool = False,
    effect_timeout: float | None = None,
) -> JsonObject:
    config = get_timeout_config()
    timeout = timeout or config.click
    timeout = min(timeout, config.max_timeout)

    if click_strategy not in VALID_STRATEGIES:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            f'Unsupported click_strategy: {click_strategy}. Use: {", ".join(sorted(VALID_STRATEGIES))}',
        ).to_dict()

    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            ErrorCode.STALE_ELEMENT,
            f'Element {element_id} is stale or not found',
            retryable=False,
            recovery_hint='Re-find the element using element_find or page_get_tree.',
        ).to_dict()

    pre_click_url = await get_tab_url(tab_info.pydoll_tab) or ''
    fallbacks_attempted: list[str] = []
    strategy_used = click_strategy
    clicked = False

    async with tab_operation_lock(tab_id):
        choice_result = await set_choice_state(element, True)
    choice_error = get_string(choice_result, 'error', '')
    if not choice_error:
        clicked = get_bool(choice_result, 'verified')
        strategy_used = get_string(choice_result, 'strategy_used')
    elif choice_error != 'not_checkable':
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Choice click failed: {choice_error}',
            retryable=True,
            details=get_object(choice_result, 'diagnostic', {}),
        ).to_dict()

    strategy_order = [] if clicked else _strategy_order(click_strategy)
    last_error: str | None = None

    for strategy in strategy_order:
        try:
            clicked = await _execute_click(tab_id, client_id, element, strategy)
            strategy_used = strategy
            if strategy != 'native' and strategy != click_strategy:
                fallbacks_attempted.append(strategy)
            break
        except (PydollException, ValueError, TypeError) as exc:
            last_error = str(exc)
            if strategy != 'native':
                fallbacks_attempted.append(strategy)
            continue

    if not clicked:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Click failed after all strategies: {last_error or "unknown"}',
            retryable=True,
            details={'strategies_attempted': [click_strategy, *fallbacks_attempted]},
        ).to_dict()

    effect_observed = False
    matched_effects: JsonArray = []
    effect_limit = effect_timeout or 5.0
    effect_limit = min(effect_limit, 30.0)

    has_effect_request = expect_dialog or expect_url_change or expect_text or expect_selector or expect_network_idle

    if has_effect_request:
        effect_observed, effect_list = await _observe_effects(
            tab_id,
            tab_info.pydoll_tab,
            pre_click_url,
            expect_dialog,
            expect_url_change,
            expect_text,
            expect_selector,
            expect_network_idle,
            effect_limit,
        )
        matched_effects = list(effect_list)

    evidence: JsonObject = {
        'timestamp': time.time(),
        'strategy': strategy_used,
        'before': {'url': pre_click_url},
    }

    warnings: JsonArray = (
        ['Requested effect was not observed before timeout.'] if has_effect_request and not effect_observed else []
    )

    return {
        'success': True,
        'element_id': element_id,
        'clicked': clicked,
        'effect_observed': effect_observed,
        'strategy_used': strategy_used,
        'fallbacks_attempted': list(fallbacks_attempted),
        'matched_effects': matched_effects,
        'warnings': warnings,
        'evidence': evidence,
    }


async def _execute_click(tab_id: str, client_id: str, element: WebElement, strategy: str) -> bool:
    async with tab_operation_lock(tab_id):
        await element.execute_script("this.scrollIntoView({block:'center'}); return true;", return_by_value=True)
        if strategy == 'native':
            await element.click()
            return True
        if strategy == 'center_mouse':
            tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
            result = await element.execute_script(
                'const r=this.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};',
                return_by_value=True,
            )
            pos = extract_script_object(result)
            x = float(str(pos.get('x', 0)))
            y = float(str(pos.get('y', 0)))
            await tab.mouse.click(x, y, button=MouseButton.LEFT)
            return True
        if strategy == 'dispatch_pointer_sequence':
            await element.execute_script(
                '(function(){const r=this.getBoundingClientRect();'
                'const cx=r.x+r.width/2,cy=r.y+r.height/2;'
                "['mousedown','mouseup','click'].forEach(t=>"
                'this.dispatchEvent(new MouseEvent(t,'
                '{bubbles:true,cancelable:true,clientX:cx,clientY:cy})));'
                'return true;}).call(this)',
                return_by_value=True,
            )
            return True
        if strategy == 'trusted_fallback_if_safe':
            await element.click()
            return True
    return False


async def _observe_effects(
    tab_id: str,
    pydoll_tab: Tab,
    pre_click_url: str,
    expect_dialog: bool,
    expect_url_change: bool,
    expect_text: str,
    expect_selector: str,
    expect_network_idle: bool,
    timeout_val: float,
) -> tuple[bool, list[str]]:
    deadline = time.monotonic() + timeout_val
    matched: list[str] = []

    while time.monotonic() < deadline:
        if expect_dialog and 'expect_dialog' not in matched:
            try:
                script = (
                    'const d=document.querySelector(\'[role="dialog"]:not([style*="display: none"])'
                    ', dialog[open], [aria-modal="true"]\');'
                    "return d ? d.getAttribute('aria-label') || d.tagName : '';"
                )
                result = await pydoll_tab.execute_script(script, return_by_value=True)
                dialog_text = extract_script_string(result)
                if dialog_text:
                    matched.append('expect_dialog')
            except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                pass

        if expect_url_change and 'expect_url_change' not in matched:
            try:
                current_url = await get_tab_url(pydoll_tab) or ''
                if current_url and current_url != pre_click_url:
                    matched.append('expect_url_change')
            except (PydollException, Exception):
                pass

        if expect_text and 'expect_text' not in matched:
            try:
                script = f'return document.body.innerText.indexOf({expect_text!r}) >= 0;'
                result = await pydoll_tab.execute_script(script, return_by_value=True)
                if extract_script_bool(result):
                    matched.append('expect_text')
            except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                pass

        if expect_selector and 'expect_selector' not in matched:
            try:
                elements = await pydoll_tab.query(expect_selector, timeout=1, find_all=False, raise_exc=False)
                if elements is not None:
                    matched.append('expect_selector')
            except PydollException:
                pass

        if expect_network_idle and 'expect_network_idle' not in matched:
            matched.append('expect_network_idle')

        if _all_effects_satisfied(
            expect_dialog, expect_url_change, expect_text, expect_selector, expect_network_idle, matched
        ):
            return True, matched

        await asyncio.sleep(0.15)

    return len(matched) > 0, matched


def _all_effects_satisfied(
    expect_dialog: bool,
    expect_url_change: bool,
    expect_text: str,
    expect_selector: str,
    expect_network_idle: bool,
    matched: list[str],
) -> bool:
    if expect_dialog and 'expect_dialog' not in matched:
        return False
    if expect_url_change and 'expect_url_change' not in matched:
        return False
    if expect_text and 'expect_text' not in matched:
        return False
    return not (
        (expect_selector and 'expect_selector' not in matched)
        or (expect_network_idle and 'expect_network_idle' not in matched)
    )


def _strategy_order(requested: str) -> list[str]:
    if requested == 'trusted_fallback_if_safe':
        return ['native', 'center_mouse', 'dispatch_pointer_sequence']
    return [requested]
