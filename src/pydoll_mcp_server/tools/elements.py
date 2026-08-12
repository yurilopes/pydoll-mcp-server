"""Element interaction tools: find, click, type, fill, get text/attribute."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.pydoll_compat import (
    get_element_attribute,
    get_element_text,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.config import get_limits_config, get_timeout_config
from pydoll_mcp_server.dom.element_cache import get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_bool, get_object, get_string
from pydoll_mcp_server.security.policy import is_sensitive_field
from pydoll_mcp_server.security.site_signals import (
    inspect_element_security,
    inspect_site_diagnostics,
    security_control_error,
)
from pydoll_mcp_server.tools.choice_interactions import set_choice_state
from pydoll_mcp_server.tools.element_resolver import (
    resolve_element,
)
from pydoll_mcp_server.tools.element_screenshot import element_screenshot as element_screenshot
from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens
from pydoll_mcp_server.tools.form_controls import fill_element_framework_safe


async def element_find(
    client_id: str,
    tab_id: str,
    selector: str,
    strategy: Annotated[
        str,
        Field(
            description='Selector strategy: css, xpath, or text.',
            json_schema_extra={'enum': ['css', 'xpath', 'text']},
        ),
    ] = 'css',
    timeout: float | None = None,
    find_all: bool = False,
) -> JsonObject:
    from pydoll_mcp_server.tools.element_find import element_find as implementation

    return await implementation(client_id, tab_id, selector, strategy, timeout, find_all)


async def element_click(
    client_id: str,
    tab_id: str,
    element_id: str,
    timeout: float | None = None,
    click_strategy: Annotated[
        str,
        Field(
            description='Click strategy. Use native normally; enhanced strategies are advanced fallbacks.',
            json_schema_extra={
                'enum': ['auto', 'native', 'center_mouse', 'dispatch_pointer_sequence', 'trusted_fallback_if_safe']
            },
        ),
    ] = 'auto',
    expect_dialog: Annotated[bool, Field(description='Wait for a JavaScript dialog after the click.')] = False,
    expect_url_change: Annotated[bool, Field(description='Require the tab URL to change after the click.')] = False,
    expect_text: Annotated[str, Field(description='Optional visible text that must appear after the click.')] = '',
    expect_selector: Annotated[
        str,
        Field(description='Optional CSS selector that must appear after the click.'),
    ] = '',
    expect_network_idle: Annotated[bool, Field(description='Wait for network idle after the click.')] = False,
    effect_timeout: Annotated[
        float | None,
        Field(description='Optional timeout used only for effect verification.'),
    ] = None,
    expect_attribute_selector: Annotated[str, Field(description='CSS selector whose attribute must change.')] = '',
    expect_attribute_name: Annotated[str, Field(description='Attribute paired with expect_attribute_selector.')] = '',
    expect_attribute_value: Annotated[str, Field(description='Optional exact expected attribute value.')] = '',
    expect_enabled_element_id: Annotated[str, Field(description='Cached control that must become enabled.')] = '',
    expect_progress_change: Annotated[bool, Field(description='Require visible progress to change.')] = False,
    expect_active_surface_change: Annotated[bool, Field(description='Require the active surface to change.')] = False,
) -> JsonObject:
    if bool(expect_attribute_selector) != bool(expect_attribute_name):
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'expect_attribute_selector and expect_attribute_name must be provided together.',
        ).to_dict()
    has_effect = any(
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
    if has_effect or click_strategy != 'native':
        from pydoll_mcp_server.tools.click_effects import element_click_enhanced

        return await element_click_enhanced(
            client_id=client_id,
            tab_id=tab_id,
            element_id=element_id,
            timeout=timeout,
            click_strategy=click_strategy,
            expect_dialog=expect_dialog,
            expect_url_change=expect_url_change,
            expect_text=expect_text,
            expect_selector=expect_selector,
            expect_network_idle=expect_network_idle,
            effect_timeout=effect_timeout,
            expect_attribute_selector=expect_attribute_selector,
            expect_attribute_name=expect_attribute_name,
            expect_attribute_value=expect_attribute_value,
            expect_enabled_element_id=expect_enabled_element_id,
            expect_progress_change=expect_progress_change,
            expect_active_surface_change=expect_active_surface_change,
        )

    config = get_timeout_config()
    timeout = timeout or config.click
    timeout = min(timeout, config.max_timeout)
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = None
    try:
        async with tab_operation_lock(tab_id):
            element = await resolve_element(tab_info, element_id)
            if element is None:
                return StructuredError(
                    error_code=ErrorCode.STALE_ELEMENT,
                    message=f'Element {element_id} is stale or not found',
                    retryable=False,
                    recovery_hint='Re-find the element using element_find or page_get_tree.',
                ).to_dict()
            if get_element_cache().get_for_tab(element_id, tab_id) is not None:
                security_control = await inspect_element_security(element)
                if security_control:
                    return security_control_error(security_control)
            invalidate_review_tokens(client_id, tab_id)
            try:
                choice_result = await set_choice_state(element, True)
                choice_error = get_string(choice_result, 'error', '')
                if not choice_error:
                    diagnostics = await inspect_site_diagnostics(tab_info.pydoll_tab)
                    return {
                        'contract_version': 2,
                        'operation_id': f'click_{element_id}',
                        'success': True,
                        'status': 'verified' if get_bool(choice_result, 'verified') else 'dispatched',
                        'element_id': element_id,
                        'clicked': True,
                        'checked': get_bool(choice_result, 'checked'),
                        'verified': get_bool(choice_result, 'verified'),
                        'strategy_used': get_string(choice_result, 'strategy_used'),
                        'mcp_action': {'event_sent': True, 'strategy_used': get_string(choice_result, 'strategy_used')},
                        'page_effect': {'expectation': {}, 'observed': False, 'missing': []},
                        'effect_status': 'no_effect',
                        'site_diagnostics': diagnostics,
                    }
                if choice_error != 'not_checkable':
                    return StructuredError(
                        ErrorCode.EXECUTION_ERROR,
                        f'Choice click failed: {choice_error}',
                        retryable=True,
                        details=get_object(choice_result, 'diagnostic', {}),
                    ).to_dict()
            except (TypeError, ValueError):
                pass
            await element.execute_script("this.scrollIntoView({block:'center'}); return true;", return_by_value=True)
            await element.click()
    except Exception as exc:
        if element is None:
            return StructuredError(
                error_code=ErrorCode.STALE_ELEMENT,
                message=f'Element {element_id} could not be resolved before retry',
                retryable=True,
            ).to_dict()
        return StructuredError(
            ErrorCode.ACTION_UNKNOWN,
            'Native click transport failed after the action may have been dispatched. No click retry was attempted.',
            retryable=False,
            details={'error': str(exc), 'strategy': 'native'},
            recovery_hint='Observe the page manually before taking another action.',
        ).to_dict()

    diagnostics = await inspect_site_diagnostics(tab_info.pydoll_tab)
    return {
        'contract_version': 2,
        'operation_id': f'click_{element_id}',
        'success': True,
        'status': 'dispatched',
        'element_id': element_id,
        'clicked': True,
        'mcp_action': {'event_sent': True, 'strategy_used': 'native'},
        'page_effect': {'expectation': {}, 'observed': False, 'missing': []},
        'effect_status': 'no_effect',
        'site_diagnostics': diagnostics,
    }


async def element_type(
    client_id: str,
    tab_id: str,
    element_id: str,
    text: str,
    delay: float = 0.0,
) -> JsonObject:
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    try:
        async with tab_operation_lock(tab_id):
            security_control = await inspect_element_security(element)
            if security_control:
                return security_control_error(security_control)
            await element.execute_script("this.scrollIntoView({block:'center'}); return true;", return_by_value=True)
            try:
                await element.type_text(text)
            except PydollException:
                # Some custom controls report an invalid visibility result when clicked
                # through WebElement, although the browser can focus them directly.
                keyboard = getattr(tab_info.pydoll_tab, 'keyboard', None)
                if keyboard is None:
                    raise
                await element.execute_script('this.focus(); return true;', return_by_value=True)
                await keyboard.type_text(text)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Type failed: {e}',
            retryable=True,
        ).to_dict()

    return {
        'success': True,
        'element_id': element_id,
        'chars_typed': len(text),
    }


async def element_fill(
    client_id: str,
    tab_id: str,
    element_id: str,
    value: str,
    verify: bool = True,
    mode: Annotated[
        str,
        Field(
            description='Fill mode: auto, framework_safe, keyboard, or blur.',
            json_schema_extra={'enum': ['auto', 'framework_safe', 'keyboard', 'blur']},
        ),
    ] = 'auto',
    validation_timeout: float = 3.0,
    expected_enabled_element_id: str = '',
    state_verification: Annotated[
        str,
        Field(
            description='Verification level: dom, framework_event, blurred, or submission_ready.',
            json_schema_extra={'enum': ['dom', 'framework_event', 'blurred', 'submission_ready']},
        ),
    ] = 'submission_ready',
) -> JsonObject:
    return await fill_element_framework_safe(
        client_id,
        tab_id,
        element_id,
        value,
        verify=verify,
        mode=mode,
        validation_timeout=validation_timeout,
        expected_enabled_element_id=expected_enabled_element_id,
        state_verification=state_verification,
    )


async def element_get_text(
    client_id: str,
    tab_id: str,
    element_id: str,
    max_chars: int = 5000,
) -> JsonObject:
    limits = get_limits_config()
    max_chars = min(max_chars, limits.max_text_chars)
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    try:
        text = await get_element_text(element)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get element text: {e}',
            retryable=True,
        ).to_dict()

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    return {
        'success': True,
        'element_id': element_id,
        'text': text,
        'length': len(text),
        'truncated': truncated,
    }


async def element_get_attribute(
    client_id: str,
    tab_id: str,
    element_id: str,
    name: str,
) -> JsonObject:
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(
            error_code=ErrorCode.STALE_ELEMENT,
            message=f'Element {element_id} is stale',
            retryable=False,
        ).to_dict()

    try:
        value = get_element_attribute(element, name)
    except Exception:
        value = None

    redacted = is_sensitive_field(name)
    if redacted and value is not None:
        value = '[REDACTED]'

    return {
        'success': True,
        'element_id': element_id,
        'attribute': name,
        'value': value,
        'exists': value is not None,
        'redacted': redacted,
    }
