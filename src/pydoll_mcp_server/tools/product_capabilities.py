"""Product-oriented capability summaries for server status responses."""

from __future__ import annotations

from pydoll_mcp_server.json_types import JsonArray, JsonObject
from pydoll_mcp_server.tool_metadata import PUBLIC_TOOL_NAMES, tool_names_for_profile
from pydoll_mcp_server.tool_runtime import get_active_tool_profile


def dynamic_capabilities() -> JsonObject:
    """Return capabilities filtered to the tools exposed by the active profile."""

    exposed = tool_names_for_profile(get_active_tool_profile(), PUBLIC_TOOL_NAMES)

    def has(name: str) -> bool:
        return name in exposed

    def names(values: dict[str, str]) -> JsonArray:
        return [label for name, label in values.items() if has(name)]

    return {
        'transports': ['stdio', 'http', 'sse'],
        'job_search': names(
            {
                'linkedin_jobs_search': 'linkedin_search',
                'linkedin_jobs_search_results': 'search_results',
                'linkedin_jobs_page_snapshot': 'search_snapshot',
                'linkedin_jobs_open_result': 'open_job',
                'linkedin_job_snapshot': 'job_snapshot',
            }
        ),
        'application_workflow': names(
            {
                'form_preflight': 'preflight',
                'form_prepare': 'prepare',
                'form_review': 'review',
                'form_submit_after_review': 'authorized_submit',
                'page_click_primary_action': 'step_transition',
                'submission_wait_for_confirmation': 'confirmation',
                'linkedin_easy_apply_open': 'linkedin_open',
                'linkedin_easy_apply_click_next': 'linkedin_next',
                'linkedin_easy_apply_submit': 'linkedin_submit',
            }
        ),
        'forms': names(
            {
                'element_fill': 'framework_safe_fill',
                'form_snapshot': 'form_snapshot',
                'form_errors': 'form_errors',
                'form_fill_fields': 'form_fill_fields',
                'form_select_choice': 'choice',
                'combobox_type_and_select': 'combobox',
                'combobox_select_option': 'combobox_option',
                'select_get_options': 'select_options',
            }
        ),
        'uploads': names(
            {
                'upload_files': 'upload',
                'upload_files_from_trigger': 'trigger_upload',
                'file_upload_state': 'upload_state',
                'artifact_prepare_upload': 'prepare_upload',
            }
        ),
        'evidence': names(
            {
                'page_screenshot': 'screenshot',
                'artifact_get_paths': 'artifact_paths',
                'artifact_export': 'artifact_export',
                'linkedin_application_evidence': 'linkedin_application',
            }
        ),
        'security_handoffs': names(
            {
                'application_domain_status': 'domain_restrictions',
                'form_preflight': 'security_preflight',
                'form_review': 'attestation_review',
                'submission_wait_for_confirmation': 'outcome_classification',
            }
        ),
        'browser': names({'browser_launch': 'launch', 'browser_close': 'close', 'browser_list': 'list'}),
        'page': names(
            {
                'page_goto': 'navigation',
                'page_snapshot': 'snapshot',
                'page_get_tree': 'tree',
                'page_get_tree_deep': 'deep_tree',
                'page_get_interactive_summary': 'interactive_summary',
                'page_get_active_surface': 'active_surface',
            }
        ),
        'elements': names(
            {
                'element_find': 'find',
                'element_find_deep': 'find_deep',
                'element_click_by_text': 'click_by_text',
                'mouse_click': 'mouse_click',
                'element_click': 'interact',
                'element_get_state': 'state',
                'element_resolve_again': 'stale_resolution',
            }
        ),
        'waits': names(
            {
                'page_wait_for_url': 'url',
                'page_wait_for_text': 'text',
                'page_wait_for_selector': 'selector',
                'page_wait_for_network_idle': 'network_idle',
                'element_wait_value': 'element_value',
            }
        ),
        'artifacts': names(
            {
                'upload_files': 'upload',
                'file_upload_state': 'upload_state',
                'artifact_get_paths': 'artifact_paths',
                'artifact_export': 'artifact_export',
                'artifact_import': 'artifact_import',
            }
        ),
        'diagnostics': names(
            {'health_check': 'health', 'server_status': 'status', 'diagnostics_snapshot': 'diagnostics'}
        ),
        'inspection': names({'network_list': 'network', 'console_list': 'console'}),
        'security': ['auth', 'redaction', 'path_allowlist', 'no_free_cdp'],
    }


__all__ = ['dynamic_capabilities']
