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
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_string, require_json_object
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

    strategy_order = _strategy_order(click_strategy)
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


async def element_resolve_again(
    client_id: str,
    tab_id: str,
    element_id: str,
    selector_hint: str = '',
    xpath_hint: str = '',
    text: str = '',
    role: str = '',
    within_element_id: str = '',
    max_candidates: int = 5,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    cache = get_element_cache()
    old_entry = cache.get_valid(element_id, tab_info.tab_id, tab_info.document_generation)

    hint_selector = selector_hint or (old_entry.selector_hint if old_entry else '')
    hint_xpath = xpath_hint or (old_entry.xpath_hint if old_entry else '')

    if not hint_selector and not hint_xpath and not text:
        return StructuredError(
            ErrorCode.STALE_ELEMENT,
            f'Element {element_id} is stale and no resolution hints are available.',
            retryable=False,
            recovery_hint='Use element_find or page_get_tree to find the element again.',
        ).to_dict()

    candidates: JsonArray = []
    safe_max = max(1, min(max_candidates, 20))

    if hint_selector:
        try:
            elements = await tab_info.pydoll_tab.query(
                hint_selector,
                timeout=3,
                find_all=True,
                raise_exc=False,
            )
            if elements:
                for el in elements[:safe_max]:
                    candidates.append(await _describe_element(el))
        except PydollException:
            pass

    if hint_xpath and len(candidates) == 0:
        try:
            elements = await tab_info.pydoll_tab.query(
                hint_xpath,
                timeout=3,
                find_all=True,
                raise_exc=False,
            )
            if elements:
                for el in elements[:safe_max]:
                    candidates.append(await _describe_element(el))
        except PydollException:
            pass

    if len(candidates) == 0:
        return StructuredError(
            ErrorCode.STALE_ELEMENT,
            f'Element {element_id} could not be re-resolved.',
            retryable=False,
            recovery_hint='The element has been removed from the DOM.',
        ).to_dict()

    if len(candidates) > 1:
        return StructuredError(
            ErrorCode.AMBIGUOUS_ELEMENT,
            f'Multiple candidates found when re-resolving {element_id}.',
            retryable=True,
            details={'candidates': candidates},
            recovery_hint='Use selector_hint or xpath_hint to identify the single correct element.',
        ).to_dict()

    new_element = require_json_object(candidates[0], 'resolved candidate')
    new_id = f'el_resolved_{element_id}'
    cache.store(
        ElementCacheEntry(
            element_id=new_id,
            tab_id=tab_id,
            document_generation=tab_info.document_generation,
            tag_name=get_string(new_element, 'tag', ''),
            text_summary=get_string(new_element, 'text', '')[:100],
            selector_hint=hint_selector,
            xpath_hint=hint_xpath,
        )
    )

    return {
        'success': True,
        'resolved': True,
        'old_element_id': element_id,
        'element_id': new_id,
        'candidate': new_element,
        'strategy_used': 'selector_hint' if hint_selector else 'xpath_hint',
        'warnings': [],
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


async def _describe_element(element: WebElement) -> JsonObject:
    try:
        tag = element.tag_name or ''
        result = await element.execute_script(
            'const r=this.getBoundingClientRect();'
            "return {text:this.innerText||this.textContent||'',"
            "role:this.getAttribute('role')||'',enabled:!this.disabled};",
            return_by_value=True,
        )
        data = extract_script_object(result)
        return {
            'tag': tag,
            'text': get_string(data, 'text', '')[:100],
            'role': get_string(data, 'role', ''),
            'enabled': bool(data.get('enabled', False)),
        }
    except (PydollException, InvalidScriptResponseError):
        return {'tag': '', 'text': '', 'role': '', 'enabled': False}
