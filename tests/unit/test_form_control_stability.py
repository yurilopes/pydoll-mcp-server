"""Unit coverage for form control replacement and discovery safety."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from pydoll.elements.web_element import WebElement

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.json_types import JsonObject

pytestmark = [pytest.mark.unit]


def test_combobox_plan_re_resolves_after_control_is_recreated() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import match_field, stable_re_resolution_plan

    previous: JsonObject = {
        'element_id': 'old-location',
        'field_key': 'location',
        'placeholder': 'Start typing...',
        'selector_hint': 'input[placeholder="Start typing..."]',
        'fingerprint': 'location-fingerprint',
    }
    current: JsonObject = {
        'element_id': 'new-location',
        'field_key': 'location',
        'placeholder': 'Start typing...',
        'selector_hint': 'input[placeholder="Start typing..."]',
        'fingerprint': 'location-fingerprint',
    }
    plan: JsonObject = {'element_id': 'old-location', 'query': 'Brazil', 'option_text': 'Brazil'}

    original = match_field(plan, [previous])
    assert original is previous
    replacement = stable_re_resolution_plan(plan, previous)
    resolved = match_field(replacement, [current])
    assert resolved is current


def test_consistent_deep_inventory_never_blocks_prepare() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import hard_prepare_blockers

    preflight: JsonObject = {
        'fields': [{'label': 'Name', 'field_key': 'name', 'element_id': 'name-1'}],
        'do_not_touch': [],
        'blockers': [{'kind': 'discovery', 'details': {'status': 'consistent'}}],
        'attestation_handoffs': [],
        'missing_candidate_data': [],
    }

    assert hard_prepare_blockers(preflight, [{'label_contains': 'Name', 'value': 'Yuri'}]) == []


def test_cache_fallback_preserves_the_original_xpath_for_re_resolution() -> None:
    from pydoll_mcp_server.dom.element_cache import ElementCache
    from pydoll_mcp_server.tools.element_resolver import cache_element

    cache = ElementCache()

    def no_attribute(_name: str) -> None:
        return None

    element = cast(WebElement, SimpleNamespace(tag_name='input', get_attribute=no_attribute))
    tab_info = cast(TabInfo, SimpleNamespace(tab_id='tab-cache', document_generation=3))

    element_id = cache_element(
        cache,
        tab_info,
        element,
        fallback_selector='//*[@id="phone-field"]',
    )
    entry = cache.get_for_tab(element_id, 'tab-cache')

    assert entry is not None
    assert entry.xpath_hint == '//*[@id="phone-field"]'
    assert entry.selector_hint == ''


def test_aggregate_fill_requests_keyboard_for_unobserved_framework_state() -> None:
    from pydoll_mcp_server.tools.form_fill import keyboard_verification_needed

    assert keyboard_verification_needed({'verified': True}, 'submission_ready') is True
    assert (
        keyboard_verification_needed(
            {'verified': True, 'framework_event': True, 'controlled_value_survived': True, 'blurred': True},
            'submission_ready',
        )
        is False
    )
    assert keyboard_verification_needed({'verified': True}, 'dom') is False
