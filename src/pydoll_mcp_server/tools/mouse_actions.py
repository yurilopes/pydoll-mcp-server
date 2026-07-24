"""Coordinate-based mouse tools for visible page controls."""

from __future__ import annotations

from pydoll.exceptions import PydollException
from pydoll.protocol.input.types import MouseButton

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_script_object,
)
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_float
from pydoll_mcp_server.tools.element_resolver import resolve_element


async def element_click_center(
    client_id: str,
    tab_id: str,
    element_id: str,
    button: str = 'left',
    click_count: int = 1,
    timeout: float | None = None,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    element = await resolve_element(tab_info, element_id)
    if element is None:
        return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
    try:
        result = await element.execute_script(
            """const r=this.getBoundingClientRect();return {
            x:r.x,y:r.y,width:r.width,height:r.height,visible:r.width>0&&r.height>0};""",
            return_by_value=True,
        )
        bounds = extract_script_object(result)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Element bounds failed: {exc}', retryable=True).to_dict()
    if not bounds.get('visible'):
        return StructuredError(ErrorCode.INVALID_INPUT, 'Element is not visible.').to_dict()
    x = get_float(bounds, 'x') + get_float(bounds, 'width') / 2
    y = get_float(bounds, 'y') + get_float(bounds, 'height') / 2
    click = await mouse_click(client_id, tab_id, x, y, button, click_count, timeout)
    if not click.get('success'):
        return click
    click['element_id'] = element_id
    click['bounds'] = bounds
    return click


async def mouse_click(
    client_id: str,
    tab_id: str,
    x: float,
    y: float,
    button: str = 'left',
    click_count: int = 1,
    timeout: float | None = None,
) -> JsonObject:
    if x < 0 or y < 0:
        return StructuredError(ErrorCode.INVALID_INPUT, 'Mouse coordinates must be non-negative.').to_dict()
    mouse_button = _mouse_button(button)
    if mouse_button is None:
        return StructuredError(ErrorCode.INVALID_INPUT, f'Unsupported mouse button: {button}').to_dict()
    safe_click_count = max(1, min(click_count, 3))
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        async with tab_operation_lock(tab_id):
            await tab.mouse.click(x, y, button=mouse_button, click_count=safe_click_count)
        return {
            'success': True,
            'clicked': True,
            'mode_used': 'mouse',
            'x': x,
            'y': y,
            'button': mouse_button.value,
            'click_count': safe_click_count,
            'timeout': timeout or 0,
        }
    except StructuredError as exc:
        return exc.to_dict()
    except PydollException as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Mouse click failed: {exc}', retryable=True).to_dict()


def _mouse_button(button: str) -> MouseButton | None:
    normalized = button.lower()
    if normalized == 'left':
        return MouseButton.LEFT
    if normalized == 'right':
        return MouseButton.RIGHT
    if normalized == 'middle':
        return MouseButton.MIDDLE
    return None
