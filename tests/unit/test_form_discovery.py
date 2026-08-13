"""Unit tests for safe reconciliation of light and deep form surfaces."""

from __future__ import annotations

import pytest

from pydoll_mcp_server.json_types import JsonArray, JsonObject
from pydoll_mcp_server.tools.form_discovery import surface_disagreement

pytestmark = [pytest.mark.unit]


def test_invisible_deep_controls_do_not_create_false_surface_disagreement() -> None:
    fields: JsonArray = [
        {
            'field_key': 'name',
            'label': 'Name',
            'selector_hint': '#name',
            'shadow_path': [],
            'frame_path': [],
        }
    ]
    deep: JsonObject = {
        'success': True,
        'elements': [
            {
                'tag': 'input',
                'role': '',
                'attrs': {'type': 'text'},
                'visible': True,
                'selector_hint': '#name',
                'label': 'Name',
                'element_id': 'name',
                'shadow_path': [],
                'frame_path': [],
            },
            {
                'tag': 'input',
                'role': '',
                'attrs': {'type': 'checkbox'},
                'visible': False,
                'selector_hint': '#hidden-choice',
                'label': '',
                'element_id': 'hidden-choice',
                'shadow_path': [],
                'frame_path': [],
            },
            {
                'tag': 'textarea',
                'role': '',
                'attrs': {'name': 'g-recaptcha-response'},
                'visible': False,
                'selector_hint': '#g-recaptcha-response',
                'label': '',
                'element_id': 'recaptcha',
                'shadow_path': [],
                'frame_path': [],
            },
        ],
    }

    result = surface_disagreement(fields, deep)

    assert result['status'] == 'consistent'
    assert result['deep_interactive_count'] == 1
    assert result['ignored_hidden_count'] == 2
