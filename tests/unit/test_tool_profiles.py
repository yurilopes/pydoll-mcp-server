"""Contracts for curated MCP tool profiles and agent-facing metadata."""

from __future__ import annotations

import os
import sys

import pytest

from pydoll_mcp_server.json_types import JsonObject, require_json_array, require_json_object
from pydoll_mcp_server.tool_catalog import get_exposed_tool_names
from pydoll_mcp_server.tool_metadata import (
    AGENT_TOOL_NAMES,
    JOBS_TOOL_NAMES,
    LINKEDIN_TOOL_NAMES,
    PUBLIC_TOOL_NAMES,
    TOOL_METADATA,
    ToolProfile,
    parse_tool_profile,
    profile_lifecycle,
)

pytestmark = pytest.mark.unit


def _names(value: str) -> frozenset[str]:
    return frozenset(value.split())


EXPECTED_AGENT_NAMES = _names(
    """
    health_check server_status browser_launch browser_list browser_close browser_attach tab_list tab_activate
    tab_close tab_recover
    tab_new tab_health_check profile_list page_goto page_reload page_back page_forward page_wait_for_url page_get_text
    page_snapshot page_screenshot page_get_tree_deep page_get_interactive_summary page_get_active_surface frame_list
    page_scroll page_scroll_to
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

EXPECTED_LINKEDIN_NAMES = _names(
    """
    linkedin_job_snapshot linkedin_easy_apply_open linkedin_easy_apply_close linkedin_easy_apply_snapshot
    linkedin_easy_apply_wait_ready linkedin_easy_apply_upload_resume linkedin_easy_apply_click_next
    linkedin_easy_apply_fill_questions linkedin_easy_apply_handle_save_prompt linkedin_easy_apply_submit
    linkedin_jobs_page_snapshot linkedin_jobs_open_result linkedin_application_evidence linkedin_jobs_search
    linkedin_jobs_search_results linkedin_message_recruiter
    """
)

EXPECTED_JOBS_NAMES = (
    EXPECTED_AGENT_NAMES
    | EXPECTED_LINKEDIN_NAMES
    | {'element_fill_and_verify', 'element_find_by_text_candidates', 'element_scroll_into_view'}
) - {'page_get_tree_deep', 'element_find_deep'}


def test_full_profile_preserves_all_public_names_without_duplicates() -> None:
    names = get_exposed_tool_names(ToolProfile.FULL)

    assert names == tuple(PUBLIC_TOOL_NAMES)
    assert len(names) == 151
    assert len(names) == len(set(names))
    assert set(TOOL_METADATA) == set(names)


def test_agent_profile_is_the_declared_allowlist() -> None:
    assert AGENT_TOOL_NAMES == EXPECTED_AGENT_NAMES
    assert set(get_exposed_tool_names(ToolProfile.AGENT)) == EXPECTED_AGENT_NAMES
    assert 'page_get_tree' not in AGENT_TOOL_NAMES
    assert 'http_request' not in AGENT_TOOL_NAMES
    assert 'js_evaluate' not in AGENT_TOOL_NAMES
    assert 'upload_files_from_trigger' in AGENT_TOOL_NAMES


def test_jobs_profile_is_the_focused_default_allowlist() -> None:
    jobs_names = set(get_exposed_tool_names(ToolProfile.JOBS))

    assert JOBS_TOOL_NAMES == EXPECTED_JOBS_NAMES
    assert jobs_names == EXPECTED_JOBS_NAMES
    assert len(jobs_names) == 90
    assert {'form_preflight', 'form_prepare', 'form_review', 'form_submit_after_review'} <= jobs_names
    assert {
        'js_evaluate',
        'js_evaluate_readonly',
        'http_request',
        'network_replay_request',
        'cookies_get',
        'storage_get',
        'page_get_tree_deep',
        'element_find_deep',
        'mouse_click',
        'element_click_center',
    }.isdisjoint(jobs_names)


def test_profile_lifecycle_and_defaults_are_job_oriented() -> None:
    assert profile_lifecycle(ToolProfile.JOBS) == 'recommended'
    assert profile_lifecycle(ToolProfile.AGENT) == 'legacy'
    assert profile_lifecycle(ToolProfile.LINKEDIN) == 'legacy'
    assert profile_lifecycle(ToolProfile.FULL) == 'compatibility'
    assert set(get_exposed_tool_names()) == EXPECTED_JOBS_NAMES


@pytest.mark.asyncio
async def test_server_status_reports_job_product_and_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.config import get_config
    from pydoll_mcp_server.tools.diagnostics import server_status

    get_config.cache_clear()
    monkeypatch.setenv('PYDOLL_MCP_ALLOW_NO_AUTH', 'true')
    try:
        result = await server_status()
    finally:
        get_config.cache_clear()
    capabilities = require_json_object(result.get('capabilities'), 'capabilities')

    assert result['product'] == 'job_search_and_application'
    assert result['recommended_tool_profile'] == 'jobs'
    assert result['profile_lifecycle'] == 'recommended'
    assert result['tool_profile'] == 'jobs'
    for key in ('job_search', 'application_workflow', 'forms', 'uploads', 'evidence', 'security_handoffs'):
        assert key in capabilities


def test_linkedin_profile_is_agent_plus_linkedin_tools() -> None:
    assert LINKEDIN_TOOL_NAMES == EXPECTED_LINKEDIN_NAMES
    linkedin_names = set(get_exposed_tool_names(ToolProfile.LINKEDIN))

    assert linkedin_names == EXPECTED_AGENT_NAMES | EXPECTED_LINKEDIN_NAMES
    assert len(linkedin_names) == 89
    assert 'linkedin_easy_apply_submit' in linkedin_names
    assert 'network_replay_request' not in linkedin_names


def test_all_manifest_entries_have_titles_and_descriptions() -> None:
    for name, metadata in TOOL_METADATA.items():
        assert metadata.title, name
        assert metadata.description, name
        assert metadata.category, name
        assert metadata.annotations is not None


def test_annotations_mark_read_only_mutating_destructive_and_open_world_tools() -> None:
    assert TOOL_METADATA['page_snapshot'].annotations.readOnlyHint is True
    assert TOOL_METADATA['element_click'].annotations.readOnlyHint is False
    assert TOOL_METADATA['browser_close'].annotations.destructiveHint is True
    assert TOOL_METADATA['http_request'].annotations.openWorldHint is True
    assert TOOL_METADATA['http_request'].annotations.destructiveHint is True
    assert TOOL_METADATA['linkedin_easy_apply_submit'].annotations.openWorldHint is True


def test_profile_parser_has_clear_error_for_unknown_profile() -> None:
    assert parse_tool_profile('JOBS') is ToolProfile.JOBS
    assert parse_tool_profile('LINKEDIN') is ToolProfile.LINKEDIN

    with pytest.raises(ValueError, match='Unknown tool profile'):
        parse_tool_profile('unknown')


def test_cli_argument_overrides_profile_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server import cli

    captured: list[str] = []
    monkeypatch.setenv('PYDOLL_MCP_TOOL_PROFILE', 'agent')
    monkeypatch.setattr(sys, 'argv', ['pydoll-mcp-server', '--transport', 'stdio', '--tool-profile', 'linkedin'])
    monkeypatch.setattr(cli, 'run_stdio', lambda: captured.append('started'))

    cli.main()

    assert captured == ['started']
    assert os.environ['PYDOLL_MCP_TOOL_PROFILE'] == 'linkedin'


def test_cli_uses_profile_environment_when_argument_is_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server import cli

    captured: list[str] = []
    monkeypatch.setenv('PYDOLL_MCP_TOOL_PROFILE', 'agent')
    monkeypatch.setattr(sys, 'argv', ['pydoll-mcp-server', '--transport', 'stdio'])
    monkeypatch.setattr(cli, 'run_stdio', lambda: captured.append('started'))

    cli.main()

    assert captured == ['started']
    assert os.environ['PYDOLL_MCP_TOOL_PROFILE'] == 'agent'


def test_cli_defaults_to_jobs_when_profile_is_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server import cli

    captured: list[str] = []
    monkeypatch.delenv('PYDOLL_MCP_TOOL_PROFILE', raising=False)
    monkeypatch.setattr(sys, 'argv', ['pydoll-mcp-server', '--transport', 'stdio'])
    monkeypatch.setattr(cli, 'run_stdio', lambda: captured.append('started'))

    cli.main()

    assert captured == ['started']
    assert os.environ['PYDOLL_MCP_TOOL_PROFILE'] == 'jobs'


def _schema_property(tool: object, property_name: str) -> JsonObject:
    raw_schema: object = getattr(tool, 'inputSchema', None)
    schema = require_json_object(raw_schema, 'tool input schema')
    properties = require_json_object(schema.get('properties'), 'tool input properties')
    return require_json_object(properties.get(property_name), f'tool property {property_name}')


def _schema_item_enum(property_schema: JsonObject) -> object:
    variants = require_json_array(property_schema.get('anyOf'), 'schema variants')
    first_variant = require_json_object(variants[0], 'schema variant')
    items = require_json_object(first_variant.get('items'), 'schema items')
    return items.get('enum')


@pytest.mark.asyncio
async def test_priority_tools_publish_parameter_descriptions_and_enums() -> None:
    from pydoll_mcp_server.server import mcp

    tools = {tool.name: tool for tool in await mcp.list_tools()}
    focus_names = {
        'browser_launch',
        'element_click',
        'element_click_by_text',
        'element_find_by_text_candidates',
        'element_resolve_again',
        'page_get_active_surface',
        'form_fill_fields',
        'page_click_primary_action',
        'submission_wait_for_confirmation',
        'linkedin_jobs_search',
    }

    assert focus_names <= tools.keys()
    for name in focus_names:
        assert tools[name].description
        assert tools[name].title

    assert _schema_property(tools['browser_launch'], 'profile_mode').get('enum') == ['persistent', 'temporary']
    assert _schema_property(tools['element_find'], 'strategy').get('enum') == ['css', 'xpath', 'text']
    assert _schema_property(tools['element_click'], 'click_strategy').get('enum') == [
        'auto',
        'native',
        'center_mouse',
        'dispatch_pointer_sequence',
        'trusted_fallback_if_safe',
    ]
    assert _schema_property(tools['page_get_active_surface'], 'scope').get('enum') == [
        'auto',
        'modal',
        'dialog',
        'form',
        'main',
        'viewport',
        'active_element_context',
    ]

    search_schema = _schema_property(tools['linkedin_jobs_search'], 'date_posted')
    assert search_schema.get('enum') == ['any', 'past_24h', 'past_week', 'past_month']
    sort_schema = _schema_property(tools['linkedin_jobs_search'], 'sort_by')
    assert sort_schema.get('enum') == ['relevance', 'recent']
    experience_schema = _schema_property(tools['linkedin_jobs_search'], 'experience_levels')
    assert _schema_item_enum(experience_schema) == [
        'internship',
        'entry',
        'associate',
        'mid_senior',
        'director',
        'executive',
    ]
    job_type_schema = _schema_property(tools['linkedin_jobs_search'], 'job_types')
    assert _schema_item_enum(job_type_schema) == [
        'full_time',
        'part_time',
        'contract',
        'temporary',
        'volunteer',
        'internship',
        'other',
    ]
