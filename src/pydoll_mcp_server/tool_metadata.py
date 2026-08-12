"""Tool metadata, exposure profiles, and agent-facing guidance."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from mcp.types import ToolAnnotations


class ToolProfile(str, Enum):
    """Public tool exposure profiles."""

    FULL = 'full'
    AGENT = 'agent'
    LINKEDIN = 'linkedin'


@dataclass(frozen=True)
class ToolMetadata:
    """Metadata used when registering one public MCP tool."""

    title: str
    description: str
    category: str
    canonical: bool
    annotations: ToolAnnotations


def _split_names(value: str) -> tuple[str, ...]:
    return tuple(value.split())


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
OPEN_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
OPEN_MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
OPEN_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


AGENT_TOOL_NAMES = frozenset(
    _split_names(
        """
    health_check server_status browser_launch browser_list browser_close browser_attach tab_list tab_activate
    tab_close tab_recover
    tab_new tab_health_check profile_list page_goto page_reload page_back page_forward page_wait_for_url page_get_text
    page_snapshot page_screenshot page_get_tree_deep page_get_interactive_summary page_get_active_surface
    frame_list page_scroll page_scroll_to
    element_find element_find_deep element_find_by_role element_find_by_text element_find_by_label
    element_find_by_placeholder
    element_resolve_again element_click element_click_by_text element_type element_fill element_get_text
    element_get_attribute element_get_state element_select_option element_check element_uncheck keyboard_press
    form_snapshot form_errors form_fill_fields form_select_choice form_preflight form_review form_prepare
    form_submit_after_review application_domain_status combobox_get_options select_get_options
    combobox_type_and_select combobox_select_option page_wait_for_text page_wait_text_gone page_wait_for_selector
    page_wait_for_network_idle element_wait_for_state element_wait_value operation_cancel page_click_primary_action
    submission_wait_for_confirmation artifact_get_paths artifact_export artifact_prepare_upload upload_files
    upload_files_from_trigger
    file_upload_state
        """
    )
)

LINKEDIN_TOOL_NAMES = frozenset(
    _split_names(
        """
    linkedin_job_snapshot linkedin_easy_apply_open linkedin_easy_apply_close linkedin_easy_apply_snapshot
    linkedin_easy_apply_wait_ready linkedin_easy_apply_upload_resume linkedin_easy_apply_click_next
    linkedin_easy_apply_fill_questions linkedin_easy_apply_handle_save_prompt linkedin_easy_apply_submit
    linkedin_jobs_page_snapshot linkedin_jobs_open_result linkedin_application_evidence linkedin_jobs_search
    linkedin_jobs_search_results linkedin_message_recruiter
        """
    )
)

PUBLIC_TOOL_NAMES = _split_names(
    """
    health_check server_status browser_launch browser_list browser_close browser_attach proxy_validate proxy_get
    tab_list tab_activate tab_close tab_recover page_goto page_reload page_back page_forward page_wait page_get_text
    page_get_tree page_screenshot page_get_tree_deep element_find element_find_deep element_click element_click_by_text
    element_click_center element_type element_fill element_fill_and_verify element_get_text element_get_attribute
    element_screenshot js_evaluate_readonly js_evaluate user_agent_set user_agent_get viewport_set viewport_get
    cookies_get cookies_set storage_get storage_set download_expect upload_files upload_files_from_trigger
    file_upload_state artifact_get_paths
    artifact_import http_request network_enable network_disable network_list network_get_response network_get_request
    websocket_list websocket_get websocket_frames_list network_replay_request console_enable console_disable
    console_list
    diagnostics_snapshot trace_start trace_stop trace_get trace_cleanup tab_new tab_duplicate tab_health_check
    tab_recreate element_get_state element_select_option element_check element_uncheck element_hover
    element_scroll_into_view element_find_by_role element_find_by_text element_find_by_label element_find_by_placeholder
    element_find_by_test_id keyboard_press page_scroll page_scroll_to page_snapshot page_diff
    page_get_accessibility_tree page_get_interactive_summary frame_list frame_snapshot page_wait_for_url
    page_wait_for_function page_wait_for_text page_wait_text_gone page_wait_for_selector page_wait_for_network_idle
    element_wait_for_state element_wait_value network_wait_for_request network_wait_for_response operation_cancel
    network_summary network_clear dialog_list dialog_handle popup_prepare popup_wait download_prepare download_wait
    download_list download_get_info page_print_pdf mouse_click form_snapshot form_errors combobox_get_options
    select_get_options combobox_type_and_select combobox_select_option page_get_active_surface
    element_find_by_text_candidates element_resolve_again form_fill_fields form_select_choice form_preflight form_review
    form_prepare form_submit_after_review application_domain_status page_click_primary_action
    artifact_prepare_upload artifact_export submission_wait_for_confirmation profile_list profile_promote
    linkedin_job_snapshot
    linkedin_easy_apply_open linkedin_easy_apply_close linkedin_easy_apply_snapshot linkedin_easy_apply_wait_ready
    linkedin_easy_apply_upload_resume linkedin_easy_apply_click_next linkedin_easy_apply_fill_questions
    linkedin_easy_apply_handle_save_prompt linkedin_easy_apply_submit linkedin_jobs_page_snapshot
    linkedin_jobs_open_result
    linkedin_application_evidence linkedin_jobs_search linkedin_jobs_search_results linkedin_message_recruiter
    """
)

_CANONICAL_TOOL_NAMES = AGENT_TOOL_NAMES | LINKEDIN_TOOL_NAMES
_MUTATING_TOOL_NAMES = frozenset(
    _split_names(
        """
    browser_launch tab_activate tab_recover page_goto page_reload page_back page_forward element_click
    element_click_by_text element_click_center element_type element_fill element_fill_and_verify cookies_set storage_set
    upload_files upload_files_from_trigger artifact_import http_request network_enable network_disable
    network_replay_request
    trace_start trace_stop
    trace_cleanup tab_new tab_duplicate tab_recreate user_agent_set element_select_option element_check element_uncheck
    element_hover
    element_scroll_into_view keyboard_press page_scroll page_scroll_to page_print_pdf operation_cancel network_clear
    dialog_handle popup_prepare download_prepare mouse_click combobox_type_and_select combobox_select_option
    form_fill_fields form_select_choice form_prepare artifact_export page_click_primary_action
    artifact_prepare_upload profile_promote
    linkedin_easy_apply_open linkedin_easy_apply_close linkedin_easy_apply_upload_resume linkedin_easy_apply_click_next
    linkedin_easy_apply_fill_questions linkedin_easy_apply_handle_save_prompt linkedin_easy_apply_submit
    linkedin_jobs_search linkedin_jobs_open_result linkedin_message_recruiter
        """
    )
)
_DESTRUCTIVE_TOOL_NAMES = frozenset(
    _split_names(
        'browser_close tab_close tab_recreate js_evaluate http_request network_clear network_replay_request '
        'linkedin_easy_apply_submit form_submit_after_review'
    )
)
_OPEN_WORLD_TOOL_NAMES = frozenset(
    _split_names(
        'browser_launch page_goto page_reload page_back page_forward http_request network_replay_request '
        'tab_new tab_duplicate user_agent_set linkedin_jobs_search linkedin_easy_apply_submit form_submit_after_review'
    )
)

_CATEGORY_PREFIXES = (
    ('linkedin_', 'linkedin'),
    ('browser_', 'lifecycle'),
    ('proxy_', 'lifecycle'),
    ('profile_', 'lifecycle'),
    ('tab_', 'lifecycle'),
    ('page_wait', 'waits'),
    ('element_wait', 'waits'),
    ('network_wait', 'waits'),
    ('page_get', 'observation'),
    ('page_snapshot', 'observation'),
    ('page_diff', 'observation'),
    ('page_screenshot', 'observation'),
    ('page_', 'navigation'),
    ('element_', 'elements'),
    ('form_', 'forms'),
    ('combobox_', 'forms'),
    ('select_', 'forms'),
    ('network_', 'network'),
    ('websocket_', 'network'),
    ('http_', 'network'),
    ('console_', 'network'),
    ('download_', 'files'),
    ('upload_', 'files'),
    ('file_', 'files'),
    ('artifact_', 'files'),
    ('dialog_', 'dialogs'),
    ('popup_', 'tabs'),
    ('js_', 'advanced'),
    ('user_agent_', 'advanced'),
    ('viewport_', 'advanced'),
    ('cookies_', 'security'),
    ('storage_', 'security'),
    ('trace_', 'diagnostics'),
    ('diagnostics_', 'diagnostics'),
)
_TITLE_WORDS = {'http': 'HTTP', 'js': 'JavaScript', 'url': 'URL', 'pdf': 'PDF', 'api': 'API', 'id': 'ID'}
_TITLE_OVERRIDES = {
    'browser_launch': 'Launch Browser',
    'element_click_by_text': 'Click by Visible Text',
    'element_find_by_text_candidates': 'Rank Text Candidates',
    'element_resolve_again': 'Re-resolve Element',
    'form_fill_fields': 'Fill Form Fields',
    'http_request': 'Browser HTTP Request',
    'linkedin_jobs_search': 'Search LinkedIn Jobs',
    'page_get_active_surface': 'Get Active Surface',
    'page_click_primary_action': 'Click Primary Action',
    'submission_wait_for_confirmation': 'Wait for Submission Confirmation',
    'form_preflight': 'Preflight Form',
    'form_review': 'Review Form',
    'form_prepare': 'Prepare Form',
    'form_submit_after_review': 'Submit After Review',
    'application_domain_status': 'Check Application Domain Status',
}

_DESCRIPTION_OVERRIDES = {
    'health_check': 'Check server health and version. Use this before diagnosing a connection.',
    'server_status': ('Inspect owned resources and the active tool profile. Use this to confirm runtime capabilities.'),
    'browser_launch': (
        'Launch an owned browser and return its first tab. '
        'Use profile_mode and site_hint when preserving authenticated state matters.'
    ),
    'element_find': (
        'Find an element with CSS or XPath and cache its element_id. Use semantic finders when intent is known.'
    ),
    'element_click': (
        'Click a cached element_id and optionally verify an effect. '
        'Use element_click_by_text when no stable ID is available.'
    ),
    'element_click_by_text': (
        'Resolve and click a visible actionable control by text and context. '
        'Use page_click_primary_action for form footer actions.'
    ),
    'element_fill': (
        'Set and verify a value in a cached form element using framework-compatible events. '
        'Prefer this for ordinary fields.'
    ),
    'element_find_by_text_candidates': (
        'Return ranked candidates for ambiguous visible text without clicking. '
        'Use element_find_by_text for normal resolution.'
    ),
    'element_resolve_again': (
        'Recover a stale element_id using prior selector, role, or text hints. Use after a page rerender.'
    ),
    'form_fill_fields': (
        'Fill explicitly mapped fields in one framework-compatible operation. '
        'Use this instead of repeated element_fill calls.'
    ),
    'http_request': (
        'Send an HTTP request with the tab session context. '
        'Use only when page automation is insufficient and the target is explicit.'
    ),
    'network_replay_request': (
        'Replay a captured request with an explicit side-effect confirmation. '
        'Use only for advanced network diagnostics.'
    ),
    'page_get_active_surface': (
        'Inspect the focused modal, dialog, form, or main surface with cached fields and actions. '
        'Prefer this for focused workflows.'
    ),
    'page_snapshot': (
        'Capture the initial structured page observation with cached element IDs. '
        'Prefer this before deeper tree traversal.'
    ),
    'page_click_primary_action': (
        'Resolve and click the primary action of the active surface with optional progress verification. '
        'Use for form-step advancement.'
    ),
    'submission_wait_for_confirmation': (
        'Wait for success text, status text, URL change, or modal closure after submission. '
        'Use immediately after a submit action.'
    ),
    'form_preflight': (
        'Inspect required fields, blockers, security controls, and candidate data gaps without changing the page.'
    ),
    'form_review': (
        'Capture a compact, redacted review of the current application form and issue a short-lived review token '
        'only when the state is consistent.'
    ),
    'form_prepare': (
        'Prepare an application form from explicit caller-provided facts, choices, comboboxes, uploads, and steps. '
        'Never clicks the final submit action.'
    ),
    'form_submit_after_review': (
        'Submit exactly once after validating a scoped review token and explicit authorization. '
        'Returns a typed outcome and never retries an unknown click.'
    ),
    'application_domain_status': (
        'Check a restriction recorded for one explicit employer domain. Restrictions are not inferred across domains.'
    ),
    'upload_files_from_trigger': (
        'Upload an explicit local file through a custom browser trigger without manual staging. '
        'Use auto for input, intercepted chooser, or a validated Windows native picker fallback; '
        'verify the returned strategy and native staging evidence.'
    ),
    'linkedin_jobs_search': (
        'Build and open a LinkedIn Jobs search with location, remote, Easy Apply, '
        'date, experience, type, and pagination filters.'
    ),
    'linkedin_message_recruiter': (
        'Send one caller-provided message to the uniquely associated recruiter on the current LinkedIn job '
        'after a submitted application is confirmed. Does not navigate to profiles, send InMail, or retry delivery.'
    ),
}


def _category_for(public_name: str) -> str:
    for prefix, category in _CATEGORY_PREFIXES:
        if public_name.startswith(prefix):
            return category
    if public_name in {'health_check', 'server_status'}:
        return 'diagnostics'
    return 'advanced'


def _title_for(public_name: str) -> str:
    if public_name in _TITLE_OVERRIDES:
        return _TITLE_OVERRIDES[public_name]
    return ' '.join(_TITLE_WORDS.get(word, word.capitalize()) for word in public_name.split('_'))


def _annotation_for(public_name: str) -> ToolAnnotations:
    is_open = public_name in _OPEN_WORLD_TOOL_NAMES
    if public_name in _DESTRUCTIVE_TOOL_NAMES:
        return OPEN_DESTRUCTIVE if is_open else DESTRUCTIVE
    if public_name in _MUTATING_TOOL_NAMES:
        return OPEN_MUTATING if is_open else MUTATING
    return OPEN_READ_ONLY if is_open else READ_ONLY


def _description_for(public_name: str, title: str, category: str) -> str:
    override = _DESCRIPTION_OVERRIDES.get(public_name)
    if override is not None:
        return override
    if public_name in _MUTATING_TOOL_NAMES:
        external = '; keep the external target explicit' if public_name in _OPEN_WORLD_TOOL_NAMES else ''
        return (
            f'{title}. Use it when canonical {category} tools are insufficient; '
            f'it changes browser state, so re-observe afterward.{external}'
        )
    return (
        f'{title}. Use it for {category} observation or diagnostics; '
        'prefer a more specific canonical tool when one matches.'
    )


def _build_metadata() -> dict[str, ToolMetadata]:
    return {
        public_name: ToolMetadata(
            title=_title_for(public_name),
            description=_description_for(public_name, _title_for(public_name), _category_for(public_name)),
            category=_category_for(public_name),
            canonical=public_name in _CANONICAL_TOOL_NAMES,
            annotations=_annotation_for(public_name),
        )
        for public_name in PUBLIC_TOOL_NAMES
    }


TOOL_METADATA = _build_metadata()


def parse_tool_profile(value: str) -> ToolProfile:
    """Parse a public profile name or raise a clear validation error."""

    try:
        return ToolProfile(value.strip().lower())
    except ValueError as exc:
        choices = ', '.join(profile.value for profile in ToolProfile)
        raise ValueError(f'Unknown tool profile {value!r}. Choose one of: {choices}.') from exc


def tool_names_for_profile(profile: ToolProfile, all_names: Iterable[str]) -> frozenset[str]:
    """Return the public names exposed by one profile."""

    names = frozenset(all_names)
    if profile is ToolProfile.FULL:
        return names
    if profile is ToolProfile.AGENT:
        return AGENT_TOOL_NAMES
    return AGENT_TOOL_NAMES | LINKEDIN_TOOL_NAMES


__all__ = [
    'AGENT_TOOL_NAMES',
    'LINKEDIN_TOOL_NAMES',
    'PUBLIC_TOOL_NAMES',
    'TOOL_METADATA',
    'ToolMetadata',
    'ToolProfile',
    'parse_tool_profile',
    'tool_names_for_profile',
]
