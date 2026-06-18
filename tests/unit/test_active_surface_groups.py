"""Grouped choice field tests for active surface observation."""

from __future__ import annotations

import pytest

from pydoll_mcp_server.json_types import get_array, require_json_object
from pydoll_mcp_server.tools.active_surface import deserialize_surface_fields
from pydoll_mcp_server.tools.surface_scripts import surface_script

pytestmark = [pytest.mark.unit]


def test_grouped_choices_receive_option_element_ids() -> None:
    fields = deserialize_surface_fields(
        [
            {
                'tag': 'div',
                'type': 'radio_group',
                'label': 'Years of PowerBI experience',
                'selector_hint': '#experience-group',
                'xpath_hint': '',
                'options': [
                    {
                        'tag': 'input',
                        'type': 'radio',
                        'label': '5 or more',
                        'selector_hint': '#experience-5',
                        'xpath_hint': '',
                    }
                ],
            }
        ],
        'test',
        'tab-test',
        1,
    )

    group = require_json_object(fields[0], 'group')
    assert group.get('element_id') == ''
    option = require_json_object(get_array(group, 'options', [])[0], 'option')
    assert str(option.get('element_id', '')).startswith('el_')


def test_script_groups_choices_and_excludes_dismiss_primary_actions() -> None:
    script = surface_script(
        '{"scope":"auto","max_fields":100,"max_controls":120,"include_values":false,"text_max_chars":300}'
    )

    assert "type: group.type + '_group'" in script
    assert 'options,' in script
    assert 'findPendingRequired(fields)' in script
    assert 'dismissWords.test' in script
