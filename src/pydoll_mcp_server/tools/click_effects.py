"""Enhanced click with effect observation and stale element re-resolution."""

from __future__ import annotations

import time

from pydoll.elements.web_element import WebElement
from pydoll.exceptions import ElementNotInteractable, ElementNotVisible, PydollException
from pydoll.protocol.input.types import MouseButton

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.pydoll_compat import get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_object
from pydoll_mcp_server.browser.tab_reconciliation import sync_browser_tabs
from pydoll_mcp_server.config import get_timeout_config
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_bool, get_object, get_string
from pydoll_mcp_server.security.site_signals import inspect_element_security, inspect_site_diagnostics
from pydoll_mcp_server.tools.choice_interactions import set_choice_state
from pydoll_mcp_server.tools.click_observation import (
    capture_effect_state,
    effect_expectation,
    missing_effects,
    observe_effects,
)
from pydoll_mcp_server.tools.element_resolver import resolve_element_for_action
from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens
from pydoll_mcp_server.tools.form_runtime import advance_mutation_epoch

VALID_STRATEGIES = frozenset(
    {'auto', 'native', 'center_mouse', 'dispatch_pointer_sequence', 'trusted_fallback_if_safe'}
)


async def element_click_enhanced(
    client_id: str,
    tab_id: str,
    element_id: str,
    timeout: float | None = None,
    click_strategy: str = 'auto',
    expect_dialog: bool = False,
    expect_url_change: bool = False,
    expect_text: str = '',
    expect_selector: str = '',
    expect_network_idle: bool = False,
    effect_timeout: float | None = None,
    expect_attribute_selector: str = '',
    expect_attribute_name: str = '',
    expect_attribute_value: str = '',
    expect_enabled_element_id: str = '',
    expect_progress_change: bool = False,
    expect_active_surface_change: bool = False,
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

    pre_click_url = await get_tab_url(tab_info.pydoll_tab) or ''
    before_target_ids = {
        tab.target_id for tab in get_registry().list_tabs(client_id, tab_info.browser_id) if tab.target_id
    }
    fallbacks_attempted: list[str] = []
    strategy_used = click_strategy
    clicked = False
    last_error: str | None = None
    action_unknown = False
    baseline: JsonObject = {}

    async with tab_operation_lock(tab_id):
        resolution = await resolve_element_for_action(tab_info, element_id)
        if resolution.error is not None:
            response = resolution.error.to_dict()
            response['mcp_action'] = resolution.details
            response['failure_origin'] = 'resolution'
            return response
        element = resolution.element
        if element is None:
            return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
        security_control = await inspect_element_security(element)
        if security_control:
            response = StructuredError(
                ErrorCode.SECURITY_CONTROL_PRESENT,
                'The target is a security control that requires user action.',
                details={'security_control': security_control},
                retryable=False,
                recovery_hint='Ask the user to complete the security control, then re-observe the page.',
            ).to_dict()
            response['failure_origin'] = 'security'
            response['mcp_action'] = resolution.details
            return response
        invalidate_review_tokens(client_id, tab_id)
        advance_mutation_epoch(client_id, tab_id, 'click', tab_info)
        if any(
            (expect_attribute_selector, expect_enabled_element_id, expect_progress_change, expect_active_surface_change)
        ):
            baseline = await capture_effect_state(
                tab_info,
                expect_attribute_selector,
                expect_attribute_name,
                expect_enabled_element_id,
                expect_progress_change,
                expect_active_surface_change,
            )

        choice_result: JsonObject = {}
        try:
            choice_result = await set_choice_state(element, True)
        except (InvalidScriptResponseError, PydollException, TypeError, ValueError):
            choice_result = {'error': 'not_checkable'}
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
        for strategy in strategy_order:
            try:
                clicked = await _execute_click(tab_id, client_id, element, strategy)
                strategy_used = strategy
                if strategy != 'native' and strategy != click_strategy:
                    fallbacks_attempted.append(strategy)
                break
            except (PydollException, ValueError, TypeError) as exc:
                last_error = str(exc)
                if (
                    strategy == 'native'
                    and click_strategy == 'auto'
                    and not isinstance(exc, ElementNotVisible | ElementNotInteractable)
                ):
                    action_unknown = True
                    break
                if strategy != 'native':
                    fallbacks_attempted.append(strategy)
                continue

    if action_unknown:
        response = StructuredError(
            ErrorCode.ACTION_UNKNOWN,
            'Native click transport failed after the action may have been dispatched. No click retry was attempted.',
            retryable=False,
            details={'strategy': 'native', 'error': last_error or 'unknown'},
            recovery_hint='Observe the page manually before taking another action.',
        ).to_dict()
        response['failure_origin'] = 'transport'
        return response
    if not clicked:
        response = StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Click failed after all strategies: {last_error or "unknown"}',
            retryable=True,
            details={'strategies_attempted': [click_strategy, *fallbacks_attempted]},
        ).to_dict()
        response['failure_origin'] = 'mcp'
        return response

    effect_observed = False
    matched_effects: JsonArray = []
    effect_limit = effect_timeout or 5.0
    effect_limit = min(effect_limit, 30.0)

    has_effect_request = any(
        (
            expect_dialog,
            expect_url_change,
            expect_text,
            expect_selector,
            expect_network_idle,
            expect_attribute_selector,
            expect_enabled_element_id,
            expect_progress_change,
            expect_active_surface_change,
        )
    )

    if has_effect_request:
        effect_observed, effect_list = await observe_effects(
            tab_id,
            tab_info.pydoll_tab,
            pre_click_url,
            expect_dialog,
            expect_url_change,
            expect_text,
            expect_selector,
            expect_network_idle,
            effect_limit,
            baseline=baseline,
            tab_info=tab_info,
            expect_attribute_selector=expect_attribute_selector,
            expect_attribute_name=expect_attribute_name,
            expect_attribute_value=expect_attribute_value,
            expect_enabled_element_id=expect_enabled_element_id,
            expect_progress_change=expect_progress_change,
            expect_active_surface_change=expect_active_surface_change,
        )
        matched_effects = list(effect_list)

    new_tabs: JsonArray = []
    try:
        await sync_browser_tabs(client_id, tab_info.browser_id)
        for candidate in get_registry().list_tabs(client_id, tab_info.browser_id):
            if candidate.target_id and candidate.target_id not in before_target_ids:
                new_tabs.append(
                    {
                        'target_id': candidate.target_id,
                        'tab_id': candidate.tab_id,
                        'url': candidate.url,
                        'title': candidate.title,
                        'opener_tab_id': tab_id,
                        'provenance': 'click',
                    }
                )
    except (PydollException, StructuredError, RuntimeError, TimeoutError, OSError):
        new_tabs = []
    if new_tabs:
        matched_effects.append({'kind': 'new_target_effect', 'targets': new_tabs})
        effect_observed = True

    evidence: JsonObject = {
        'timestamp': time.time(),
        'strategy': strategy_used,
        'before': {'url': pre_click_url},
        'after': {'url': await get_tab_url(tab_info.pydoll_tab) or ''},
        'viewport': {},
    }

    missing = missing_effects(
        expect_dialog,
        expect_url_change,
        expect_text,
        expect_selector,
        expect_network_idle,
        matched_effects,
        expect_attribute_selector=expect_attribute_selector,
        expect_enabled_element_id=expect_enabled_element_id,
        expect_progress_change=expect_progress_change,
        expect_active_surface_change=expect_active_surface_change,
    )
    diagnostics = (
        await inspect_site_diagnostics(tab_info.pydoll_tab)
        if not clicked or (has_effect_request and not effect_observed)
        else _diagnostics_skipped()
    )
    mcp_action: JsonObject = {
        'element_id': element_id,
        'event_sent': clicked,
        'strategy_requested': click_strategy,
        'strategy_used': strategy_used,
        'fallbacks_attempted': list(fallbacks_attempted),
        'resolution': resolution.details,
    }
    page_effect: JsonObject = {
        'expectation': effect_expectation(
            expect_dialog,
            expect_url_change,
            expect_text,
            expect_selector,
            expect_network_idle,
            expect_attribute_selector=expect_attribute_selector,
            expect_attribute_name=expect_attribute_name,
            expect_attribute_value=expect_attribute_value,
            expect_enabled_element_id=expect_enabled_element_id,
            expect_progress_change=expect_progress_change,
            expect_active_surface_change=expect_active_surface_change,
        ),
        'observed': effect_observed,
        'matched': matched_effects,
        'missing': missing,
        'evidence': evidence,
    }
    action_status = 'verified' if effect_observed else ('unknown' if has_effect_request else 'dispatched')
    effect_kind = 'visible_effect' if effect_observed else 'no_effect'
    if 'expect_selector_hidden' in matched_effects:
        effect_kind = 'hidden_effect'
    page_effect.update({'effect_status': effect_kind})
    if has_effect_request and missing:
        if effect_observed:
            return {
                'contract_version': 2,
                'operation_id': f'click_{int(time.time() * 1000)}',
                'success': True,
                'status': 'unknown',
                'element_id': element_id,
                'clicked': clicked,
                'verified': False,
                'effect_observed': True,
                'strategy_used': strategy_used,
                'fallbacks_attempted': list(fallbacks_attempted),
                'matched_effects': matched_effects,
                'warnings': [
                    {
                        'kind': 'expected_effect_pending',
                        'missing': missing,
                        'recovery': 'Re-observe the active surface before taking another action.',
                    }
                ],
                'evidence': evidence,
                'mcp_action': mcp_action,
                'page_effect': page_effect,
                'effect_status': effect_kind,
                'site_diagnostics': diagnostics,
                'failure_origin': 'page',
            }
        response = StructuredError(
            ErrorCode.NO_EFFECT,
            'The click event was sent, but the requested page effect was not observed.',
            details={'mcp_action': mcp_action, 'page_effect': page_effect, 'site_diagnostics': diagnostics},
            retryable=True,
            recovery_hint='Re-observe the page and verify whether the site is still validating or blocked.',
        ).to_dict()
        response.update(
            {
                'clicked': clicked,
                'element_id': element_id,
                'mcp_action': mcp_action,
                'page_effect': page_effect,
                'site_diagnostics': diagnostics,
                'failure_origin': 'page',
                'effect_status': effect_kind,
            }
        )
        return response

    return {
        'contract_version': 2,
        'operation_id': f'click_{int(time.time() * 1000)}',
        'success': True,
        'status': action_status,
        'element_id': element_id,
        'clicked': clicked,
        'verified': clicked,
        'effect_observed': effect_observed,
        'strategy_used': strategy_used,
        'fallbacks_attempted': list(fallbacks_attempted),
        'matched_effects': matched_effects,
        'warnings': [],
        'evidence': evidence,
        'mcp_action': mcp_action,
        'page_effect': page_effect,
        'effect_status': effect_kind,
        'site_diagnostics': diagnostics,
        'new_tabs': new_tabs,
        'failure_origin': '',
    }


async def _execute_click(tab_id: str, client_id: str, element: WebElement, strategy: str) -> bool:
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
        pos = extract_normalized_object(result, 'click_center_bounds')
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


def _strategy_order(requested: str) -> list[str]:
    if requested == 'auto':
        return ['native', 'center_mouse', 'dispatch_pointer_sequence']
    if requested == 'trusted_fallback_if_safe':
        return ['native', 'center_mouse', 'dispatch_pointer_sequence']
    return [requested]


def _diagnostics_skipped() -> JsonObject:
    return {
        'framework_hints': [],
        'security_controls': [],
        'validation_state': {},
        'diagnostics_skipped': True,
    }
