"""Unit coverage for form control replacement and discovery safety."""

from __future__ import annotations

import pytest

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
