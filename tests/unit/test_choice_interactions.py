"""Tests for verified radio and checkbox interactions."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.tools.choice_interactions import set_choice_state
from pydoll_mcp_server.tools.form_choice import form_select_choice

pytestmark = [pytest.mark.unit]


def script_result(value: JsonObject) -> JsonObject:
    return {'result': {'result': {'value': value}}}


def test_choice_helper_returns_verified_strategy() -> None:
    element = MagicMock()
    element.execute_script = AsyncMock(
        return_value=script_result({'checked': True, 'verified': True, 'strategy_used': 'associated_label'})
    )

    result = asyncio.run(set_choice_state(element, True))

    assert result == {'checked': True, 'verified': True, 'strategy_used': 'associated_label'}
    script = element.execute_script.call_args.args[0]
    assert 'ambiguous_group_option' in script
    assert 'choice_state_not_verified' in script


def test_form_select_choice_returns_cached_verified_option() -> None:
    tab = MagicMock()
    tab.execute_script = AsyncMock(
        return_value=script_result(
            {
                'checked': True,
                'verified': True,
                'strategy_used': 'associated_label',
                'tag': 'input',
                'label': '5 or more',
                'selector_hint': 'input[name="experience"][value="5-plus"]',
                'xpath_hint': '//input[@name="experience" and @value="5-plus"]',
            }
        )
    )
    tab_info = MagicMock(pydoll_tab=tab, tab_id='tab-test', document_generation=1)

    with patch('pydoll_mcp_server.tools.form_choice.get_registry') as registry:
        registry.return_value.get_tab.return_value = tab_info
        result = asyncio.run(form_select_choice('client', 'tab-test', 'PowerBI experience', '5 or more'))

    assert result.get('success') is True
    assert result.get('checked') is True
    assert result.get('verified') is True
    assert str(result.get('element_id', '')).startswith('el_')


def test_form_select_choice_rejects_ambiguous_option() -> None:
    tab = MagicMock()
    tab.execute_script = AsyncMock(return_value=script_result({'error': 'ambiguous_option', 'count': 2}))
    tab_info = MagicMock(pydoll_tab=tab, tab_id='tab-test', document_generation=1)

    with patch('pydoll_mcp_server.tools.form_choice.get_registry') as registry:
        registry.return_value.get_tab.return_value = tab_info
        result = asyncio.run(form_select_choice('client', 'tab-test', 'Experience', '5'))

    assert result.get('success') is not True
    assert result.get('error_code') == 'AMBIGUOUS_ELEMENT'


def test_summary_uses_unique_name_and_value_hints() -> None:
    from pydoll_mcp_server.tools.surface_scripts import surface_script

    script = surface_script(
        '{"scope":"auto","max_fields":10,"max_controls":10,"include_values":false,"text_max_chars":300}'
    )
    assert '[name="' in script
    assert '[value="' in script
