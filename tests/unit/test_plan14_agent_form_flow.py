"""Unit tests for PLAN_14 Agent Form Flow V2 tools."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pydoll_mcp_server.json_types import JsonObject

pytestmark = [pytest.mark.unit]


class TestActiveSurface:
    def test_invalid_scope_is_rejected(self) -> None:
        from pydoll_mcp_server.tools.active_surface import page_get_active_surface

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            result: JsonObject = asyncio.run(
                page_get_active_surface(
                    client_id='test',
                    tab_id='tab-test',
                    scope='invalid_scope',
                )
            )
            assert result.get('success') is not True
            assert result.get('error_code') == 'INVALID_INPUT'

    def test_auto_scope_calls_script(self) -> None:
        from pydoll_mcp_server.tools.active_surface import page_get_active_surface

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value={
                'result': {
                    'result': {
                        'value': {
                            'surface_scope': 'main',
                            'surface_reason': 'main element',
                            'surface_tag': 'main',
                            'surface_role': 'main',
                            'surface_label': '',
                            'surface_selector': '',
                            'fields': [],
                            'controls': [
                                {
                                    'tag': 'button',
                                    'role': 'button',
                                    'name': 'Next',
                                    'text': 'Next',
                                    'text_length': 4,
                                    'truncated': False,
                                    'enabled': True,
                                    'selector_hint': '#next',
                                    'xpath_hint': '',
                                }
                            ],
                            'containers': [
                                {
                                    'tag': 'form',
                                    'role': 'form',
                                    'name': '',
                                    'text_excerpt': 'Contact information',
                                    'text_length': 19,
                                    'truncated': False,
                                    'selector_hint': '#form',
                                    'xpath_hint': '',
                                }
                            ],
                            'primary_action': {},
                            'secondary_actions': [],
                            'progress': {},
                            'errors': [],
                            'pending_required': [],
                            'review_text': [],
                            'active_element': {},
                            'warnings': [],
                        }
                    }
                }
            }
        )

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.active_surface.get_registry') as mock_registry,
        ):
            mock_tab_info = MagicMock()
            mock_tab_info.pydoll_tab = mock_tab
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            result: JsonObject = asyncio.run(
                page_get_active_surface(
                    client_id='test',
                    tab_id='tab-test',
                    scope='auto',
                )
            )
            assert result.get('success') is True
            assert isinstance(result.get('surface'), dict)
            assert isinstance(result.get('fields'), list)
            assert isinstance(result.get('controls'), list)
            assert isinstance(result.get('containers'), list)
            assert result.get('count') == {'fields': 0, 'controls': 1, 'containers': 1}
            script = mock_tab.execute_script.call_args.args[0]
            assert '"text_max_chars": 300' in script

    def test_text_max_chars_is_clamped_in_script_payload(self) -> None:
        from pydoll_mcp_server.tools.active_surface import page_get_active_surface

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value={
                'result': {
                    'result': {
                        'value': {
                            'surface_scope': 'main',
                            'surface_reason': 'main element',
                            'surface_tag': 'main',
                            'surface_role': 'main',
                            'surface_label': '',
                            'surface_selector': '',
                            'fields': [],
                            'controls': [],
                            'containers': [],
                            'primary_action': {},
                            'secondary_actions': [],
                            'progress': {},
                            'errors': [],
                            'pending_required': [],
                            'review_text': [],
                            'active_element': {},
                            'warnings': [],
                        }
                    }
                }
            }
        )

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.active_surface.get_registry') as mock_registry,
        ):
            mock_tab_info = MagicMock()
            mock_tab_info.pydoll_tab = mock_tab
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            result: JsonObject = asyncio.run(
                page_get_active_surface(
                    client_id='test',
                    tab_id='tab-test',
                    scope='auto',
                    text_max_chars=10,
                )
            )
            assert result.get('success') is True
            script = mock_tab.execute_script.call_args.args[0]
            assert '"text_max_chars": 50' in script


class TestTextCandidates:
    def test_returns_ranked_results(self) -> None:
        from pydoll_mcp_server.tools.text_ranking import element_find_by_text_candidates

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value={
                'result': {
                    'result': {
                        'value': [
                            {
                                'unstable_index': 0,
                                'rank': 1,
                                'score': 1250.0,
                                'tag': 'button',
                                'role': 'button',
                                'name': 'Apply',
                                'text': 'Apply',
                                'actionable': True,
                                'enabled': True,
                                'visible': True,
                                'in_modal': False,
                                'in_main': True,
                                'nearest_heading': '',
                                'section_label': '',
                                'selector_hint': '#main-apply',
                                'xpath_hint': '',
                                'bounds': {'x': 10, 'y': 20, 'width': 100, 'height': 32},
                                'reasons': ['exact_text', 'semantic_actionable'],
                            }
                        ]
                    }
                }
            }
        )

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.text_ranking.get_registry') as mock_registry,
        ):
            mock_tab_info = MagicMock()
            mock_tab_info.pydoll_tab = mock_tab
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            result: JsonObject = asyncio.run(
                element_find_by_text_candidates(
                    client_id='test',
                    tab_id='tab-test',
                    text='Apply',
                    exact=True,
                    max_candidates=5,
                )
            )
            assert result.get('success') is True
            candidates = result.get('candidates', [])
            assert isinstance(candidates, list)
            assert len(candidates) == 1


class TestResolveAgain:
    def test_returns_stale_without_hints(self) -> None:
        from pydoll_mcp_server.tools.element_reresolution import element_resolve_again

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.element_reresolution.get_registry') as mock_registry,
        ):
            mock_tab_info = MagicMock()
            mock_tab_info.pydoll_tab = MagicMock()
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            result: JsonObject = asyncio.run(
                element_resolve_again(
                    client_id='test',
                    tab_id='tab-test',
                    element_id='el_nonexistent',
                )
            )
            assert result.get('success') is not True

    def test_with_selector_hint_resolves(self) -> None:
        from pydoll_mcp_server.tools.element_reresolution import element_resolve_again

        mock_element = MagicMock()
        mock_element.tag_name = 'button'
        mock_element.execute_script = AsyncMock(
            return_value={
                'text': 'Click me',
                'role': 'button',
                'enabled': True,
            }
        )

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.element_reresolution.get_registry') as mock_registry,
        ):
            mock_tab = MagicMock()
            mock_tab.query = AsyncMock(return_value=[mock_element])
            mock_tab_info = MagicMock()
            mock_tab_info.pydoll_tab = mock_tab
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            result: JsonObject = asyncio.run(
                element_resolve_again(
                    client_id='test',
                    tab_id='tab-test',
                    element_id='el_stale',
                    selector_hint='#main-apply',
                )
            )
            assert result.get('success') is True
            assert result.get('resolved') is True
            assert 'element_id' in result
