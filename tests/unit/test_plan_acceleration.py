"""Regression tests for the shared semantic workflow runtime."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pydoll_mcp_server.json_types import (
    JsonObject,
    get_array,
    get_bool,
    get_object,
    get_string,
    require_json_object,
)

pytestmark = [pytest.mark.unit]


def test_surface_cache_isolated_by_mutation_epoch_and_returns_a_copy() -> None:
    from pydoll_mcp_server.tools.form_runtime import (
        SurfaceCacheKey,
        clear_surface_cache,
        get_cached_surface,
        store_cached_surface,
    )

    clear_surface_cache()
    key = SurfaceCacheKey('client', 'tab', 1, 2, 3, 'auto', 'generic_form', False, True)
    store_cached_surface(key, {'fields': [{'label': 'Name'}]}, 'fingerprint')
    cached = get_cached_surface(key)
    assert cached is not None
    cached.snapshot['fields'] = []
    cached_again = get_cached_surface(key)
    assert cached_again is not None
    assert get_array(cached_again.snapshot, 'fields') == [{'label': 'Name'}]
    changed = SurfaceCacheKey('client', 'tab', 1, 2, 4, 'auto', 'generic_form', False, True)
    assert get_cached_surface(changed) is None
    clear_surface_cache()


def test_presets_are_explicit_and_do_not_guess_from_urls() -> None:
    from pydoll_mcp_server.tools.form_presets import get_form_preset, preset_names

    assert set(preset_names()) == {'generic_form', 'linkedin_easy_apply', 'external_ats_multistep'}
    assert get_form_preset('linkedin_easy_apply') is not None
    assert get_form_preset('https://linkedin.example/apply') is None


def test_shadow_and_choice_plans_require_deep_discovery() -> None:
    from pydoll_mcp_server.tools.form_preflight_support import deep_discovery_required

    surface: JsonObject = {
        'success': True,
        'fields': [{'label': 'Name', 'field_key': 'name'}],
        'partial': False,
        'site_diagnostics': {'framework_hints': ['open_shadow_root']},
    }
    assert deep_discovery_required(surface, []) is True
    no_shadow: JsonObject = {
        'success': True,
        'fields': [{'label': 'Name', 'field_key': 'name'}],
        'partial': False,
        'site_diagnostics': {'framework_hints': []},
    }
    assert deep_discovery_required(no_shadow, [{'field_label': 'Email'}]) is True


def test_submit_text_is_normalized_for_accents() -> None:
    from pydoll_mcp_server.tools.form_prepare_support import is_final_submit_text

    assert is_final_submit_text('Enviar inscrição') is True
    assert is_final_submit_text('Continue') is False


def test_preflight_field_state_is_redacted_but_semantically_complete() -> None:
    from pydoll_mcp_server.tools.form_preflight_support import semantic_field_states

    fields = semantic_field_states(
        [
            {
                'label': 'Email',
                'required': True,
                'enabled': True,
                'value_present': True,
                'value_length': 20,
                'value_preview': 'yuri@example.com',
            }
        ]
    )
    field = require_json_object(fields[0], 'semantic field')
    assert field['dom_value'] == ''
    assert field['framework_value'] == 'unknown'
    assert field['verification'] == 'inconclusive'
    assert field['ready_for_submission'] is True


def test_shadow_aware_scripts_keep_paths_hidden_from_agent_contract() -> None:
    from pydoll_mcp_server.tools.choice_group_scripts import choice_group_helpers_script
    from pydoll_mcp_server.tools.form_fill_script import fill_script
    from pydoll_mcp_server.tools.form_scripts import combobox_options_script

    assert 'choiceShadowPath' in choice_group_helpers_script()
    assert 'shadowRoot' in fill_script('{"fields":[]}')
    assert 'collectOptions' in combobox_options_script(20)


@pytest.mark.asyncio
async def test_active_surface_merges_open_shadow_controls_and_reuses_the_snapshot() -> None:
    from pydoll_mcp_server.tools import active_surface
    from pydoll_mcp_server.tools.form_runtime import clear_surface_cache

    clear_surface_cache()
    tab = MagicMock()
    tab.execute_script = AsyncMock(
        return_value={
            'result': {
                'result': {
                    'value': {
                        'fields': [],
                        'controls': [],
                        'containers': [],
                        'primary_action': None,
                        'secondary_actions': [],
                        'errors': [],
                        'warnings': [],
                    }
                }
            }
        }
    )
    tab_info = SimpleNamespace(
        pydoll_tab=tab,
        document_generation=1,
        mutation_epoch=0,
    )
    deep = {
        'success': True,
        'partial': False,
        'errors': [],
        'elements': [
            {
                'element_id': 'deep-name',
                'tag': 'input',
                'role': 'textbox',
                'attrs': {'type': 'text', 'name': 'name', 'required': 'true'},
                'label': 'Full name',
                'selector_hint': 'input[name="name"]',
                'xpath_hint': '',
                'visible': True,
                'enabled': True,
                'value_length': 0,
                'shadow_path': ['profile-card'],
                'frame_path': [],
            }
        ],
    }

    def get_tab(_client: str, _tab: str) -> SimpleNamespace:
        return tab_info

    registry = SimpleNamespace(get_tab=get_tab)
    with (
        patch.object(active_surface, 'get_registry', return_value=registry),
        patch.object(
            active_surface,
            'inspect_site_diagnostics',
            new=AsyncMock(
                return_value={
                    'framework_hints': ['open_shadow_root'],
                    'security_controls': [],
                    'validation_state': {},
                }
            ),
        ),
        patch(
            'pydoll_mcp_server.dom.deep_traversal.page_get_tree_deep',
            new=AsyncMock(return_value=deep),
        ) as deep_call,
    ):
        first = await active_surface.page_get_active_surface('client', 'tab')
        second = await active_surface.page_get_active_surface('client', 'tab')

    fields = get_array(first, 'fields')
    assert fields
    field = require_json_object(fields[0], 'surface field')
    assert get_string(field, 'label', '') == 'Full name'
    deep_summary = get_object(first, 'deep_discovery')
    assert get_bool(deep_summary, 'used', False) is True
    assert get_bool(second, 'cache_hit', False) is True
    assert deep_call.await_count == 1
    clear_surface_cache()


@pytest.mark.asyncio
async def test_restricted_preflight_skips_expensive_discovery() -> None:
    from pydoll_mcp_server.tools import form_preflight_workflow
    from pydoll_mcp_server.tools.form_workflow_support import DOMAIN_RESTRICTIONS, record_domain_restriction

    DOMAIN_RESTRICTIONS.clear()
    record_domain_restriction('jobs.example.com', 'portal_limit', ['limit reached'], ['job-1'])
    tab_info = SimpleNamespace(document_generation=4, mutation_epoch=2)

    def get_tab(_client: str, _tab: str) -> SimpleNamespace:
        return tab_info

    registry = SimpleNamespace(get_tab=get_tab)
    surface = AsyncMock()
    with (
        patch.object(form_preflight_workflow, 'get_registry', return_value=registry),
        patch.object(form_preflight_workflow, 'page_get_active_surface', new=surface),
    ):
        result = await form_preflight_workflow.form_preflight(
            'client',
            'tab',
            employer_domain='https://jobs.example.com/apply',
        )

    blockers = get_array(result, 'blockers')
    assert get_string(result, 'status', '') == 'blocked'
    assert get_string(result, 'discovery_skipped', '') == 'domain_restriction'
    assert get_string(require_json_object(blockers[0], 'blocker'), 'kind', '') == 'domain_restriction'
    surface.assert_not_awaited()
    DOMAIN_RESTRICTIONS.clear()
