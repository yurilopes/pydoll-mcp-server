"""Declarative registration of MCP tools."""

from __future__ import annotations

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from pydoll_mcp_server.browser.cdp_helpers import get_user_agent, get_viewport, set_user_agent, set_viewport
from pydoll_mcp_server.dom.deep_traversal import element_find_deep, page_get_tree_deep
from pydoll_mcp_server.dom.tree import build_page_tree, page_get_text, page_screenshot
from pydoll_mcp_server.security.proxy import proxy_validate
from pydoll_mcp_server.tools.active_surface import page_get_active_surface
from pydoll_mcp_server.tools.browser import browser_close, browser_launch, browser_list, proxy_get
from pydoll_mcp_server.tools.click_effects import element_resolve_again
from pydoll_mcp_server.tools.diagnostics import (
    browser_attach,
    diagnostics_snapshot,
    health_check,
    server_status,
    trace_cleanup,
    trace_get,
    trace_start,
    trace_stop,
)
from pydoll_mcp_server.tools.element_advanced import (
    element_check,
    element_find_by_label,
    element_find_by_placeholder,
    element_find_by_role,
    element_find_by_test_id,
    element_find_by_text,
    element_get_state,
    element_hover,
    element_scroll_into_view,
    element_select_option,
    element_uncheck,
    keyboard_press,
)
from pydoll_mcp_server.tools.elements import (
    element_click,
    element_fill,
    element_find,
    element_get_attribute,
    element_get_text,
    element_screenshot,
    element_type,
)
from pydoll_mcp_server.tools.files import (
    artifact_get_paths,
    artifact_import,
    download_expect,
    file_upload_state,
    upload_files,
)
from pydoll_mcp_server.tools.files_advanced import (
    download_get_info,
    download_list,
    download_prepare,
    download_wait,
    page_print_pdf,
)
from pydoll_mcp_server.tools.form_controls import (
    combobox_get_options,
    combobox_select_option,
    combobox_type_and_select,
    element_fill_and_verify,
    element_wait_value,
    form_errors,
    form_snapshot,
)
from pydoll_mcp_server.tools.form_fill import form_fill_fields
from pydoll_mcp_server.tools.inspection import (
    console_disable,
    console_enable,
    console_list,
    network_clear,
    network_disable,
    network_enable,
    network_get_response,
    network_list,
    network_summary,
)
from pydoll_mcp_server.tools.javascript import js_evaluate, js_evaluate_readonly
from pydoll_mcp_server.tools.page import page_back, page_forward, page_goto, page_reload, page_wait
from pydoll_mcp_server.tools.page_advanced import (
    frame_list,
    frame_snapshot,
    page_diff,
    page_get_accessibility_tree,
    page_scroll,
    page_scroll_to,
    page_snapshot,
)
from pydoll_mcp_server.tools.page_summary import page_get_interactive_summary
from pydoll_mcp_server.tools.primary_action import page_click_primary_action
from pydoll_mcp_server.tools.semantic_actions import element_click_by_text, element_click_center, mouse_click
from pydoll_mcp_server.tools.storage import cookies_get, cookies_set, storage_get, storage_set
from pydoll_mcp_server.tools.submission import submission_wait_for_confirmation
from pydoll_mcp_server.tools.tab_advanced import (
    dialog_handle,
    dialog_list,
    popup_prepare,
    popup_wait,
    tab_duplicate,
    tab_health_check,
    tab_new,
    tab_recreate,
)
from pydoll_mcp_server.tools.tabs import tab_activate, tab_close, tab_list, tab_recover
from pydoll_mcp_server.tools.text_ranking import element_find_by_text_candidates
from pydoll_mcp_server.tools.upload_prep import artifact_prepare_upload
from pydoll_mcp_server.tools.waits import (
    element_wait_for_state,
    network_wait_for_request,
    network_wait_for_response,
    operation_cancel,
    page_wait_for_function,
    page_wait_for_network_idle,
    page_wait_for_selector,
    page_wait_for_text,
    page_wait_for_url,
    page_wait_text_gone,
)

Tool = Callable[..., object]

TOOLS: tuple[Tool, ...] = (
    health_check,
    server_status,
    browser_launch,
    browser_list,
    browser_close,
    browser_attach,
    proxy_validate,
    proxy_get,
    tab_list,
    tab_activate,
    tab_close,
    tab_recover,
    page_goto,
    page_reload,
    page_back,
    page_forward,
    page_wait,
    page_get_text,
    build_page_tree,
    page_screenshot,
    page_get_tree_deep,
    element_find,
    element_find_deep,
    element_click,
    element_click_by_text,
    element_click_center,
    element_type,
    element_fill,
    element_fill_and_verify,
    element_get_text,
    element_get_attribute,
    element_screenshot,
    js_evaluate_readonly,
    js_evaluate,
    set_user_agent,
    get_user_agent,
    set_viewport,
    get_viewport,
    cookies_get,
    cookies_set,
    storage_get,
    storage_set,
    download_expect,
    upload_files,
    file_upload_state,
    artifact_get_paths,
    artifact_import,
    network_enable,
    network_disable,
    network_list,
    network_get_response,
    console_enable,
    console_disable,
    console_list,
    diagnostics_snapshot,
    trace_start,
    trace_stop,
    trace_get,
    trace_cleanup,
    tab_new,
    tab_duplicate,
    tab_health_check,
    tab_recreate,
    element_get_state,
    element_select_option,
    element_check,
    element_uncheck,
    element_hover,
    element_scroll_into_view,
    element_find_by_role,
    element_find_by_text,
    element_find_by_label,
    element_find_by_placeholder,
    element_find_by_test_id,
    keyboard_press,
    page_scroll,
    page_scroll_to,
    page_snapshot,
    page_diff,
    page_get_accessibility_tree,
    page_get_interactive_summary,
    frame_list,
    frame_snapshot,
    page_wait_for_url,
    page_wait_for_function,
    page_wait_for_text,
    page_wait_text_gone,
    page_wait_for_selector,
    page_wait_for_network_idle,
    element_wait_for_state,
    element_wait_value,
    network_wait_for_request,
    network_wait_for_response,
    operation_cancel,
    network_summary,
    network_clear,
    dialog_list,
    dialog_handle,
    popup_prepare,
    popup_wait,
    download_prepare,
    download_wait,
    download_list,
    download_get_info,
    page_print_pdf,
    mouse_click,
    form_snapshot,
    form_errors,
    combobox_get_options,
    combobox_type_and_select,
    combobox_select_option,
    page_get_active_surface,
    element_find_by_text_candidates,
    element_resolve_again,
    form_fill_fields,
    page_click_primary_action,
    artifact_prepare_upload,
    submission_wait_for_confirmation,
)


def register_tools(mcp: FastMCP) -> None:
    for function in TOOLS:
        mcp.tool(name=_public_tool_name(function), structured_output=False)(function)


def _public_tool_name(function: Tool) -> str:
    if function is build_page_tree:
        return 'page_get_tree'
    if function is set_user_agent:
        return 'user_agent_set'
    if function is get_user_agent:
        return 'user_agent_get'
    if function is set_viewport:
        return 'viewport_set'
    if function is get_viewport:
        return 'viewport_get'
    return function.__name__
