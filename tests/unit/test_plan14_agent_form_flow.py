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
                            'controls': [],
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
        from pydoll_mcp_server.tools.click_effects import element_resolve_again

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.click_effects.get_registry') as mock_registry,
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
        from pydoll_mcp_server.tools.click_effects import element_resolve_again

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
            patch('pydoll_mcp_server.tools.click_effects.get_registry') as mock_registry,
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


class TestFormFillFields:
    def test_accepts_field_list(self) -> None:
        from pydoll_mcp_server.tools.form_fill import form_fill_fields

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value={
                'result': {
                    'result': {
                        'value': {
                            'filled': [{'label': 'Full Name', 'tag': 'input', 'type': 'text', 'value_length': 8}],
                            'unfilled': [],
                            'ambiguous': [],
                            'validation_errors': [],
                            'pending_required': [],
                        }
                    }
                }
            }
        )

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.form_fill.get_registry') as mock_registry,
            patch('pydoll_mcp_server.tools.form_fill.tab_operation_lock') as mock_lock,
        ):
            mock_lock.return_value.__aenter__ = AsyncMock()
            mock_lock.return_value.__aexit__ = AsyncMock()
            mock_tab_info = MagicMock()
            mock_tab_info.pydoll_tab = mock_tab
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            fields: list[dict[str, object]] = [
                {'label_contains': 'Full Name', 'value': 'Test User'},
            ]
            result: JsonObject = asyncio.run(
                form_fill_fields(
                    client_id='test',
                    tab_id='tab-test',
                    fields=fields,
                    validate=False,
                )
            )
            assert isinstance(result, dict)
            assert isinstance(result.get('filled'), list)


class TestPrimaryAction:
    def test_returns_result(self) -> None:
        from pydoll_mcp_server.tools.primary_action import page_click_primary_action

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.primary_action.get_registry') as mock_registry,
            patch('pydoll_mcp_server.tools.primary_action.tab_operation_lock') as mock_lock,
            patch('pydoll_mcp_server.tools.primary_action.page_get_active_surface') as mock_surface,
        ):
            mock_lock.return_value.__aenter__ = AsyncMock()
            mock_lock.return_value.__aexit__ = AsyncMock()
            mock_tab_info = MagicMock()
            mock_tab = MagicMock()
            mock_tab.query = AsyncMock(return_value=MagicMock())
            mock_tab_info.pydoll_tab = mock_tab
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            surface_response: dict[str, object] = {
                'success': True,
                'surface': {},
                'fields': [],
                'controls': [],
                'primary_action': {
                    'tag': 'button',
                    'role': 'button',
                    'name': 'Next',
                    'element_id': 'el_test',
                    'selector_hint': '#btn-primary-action',
                },
                'secondary_actions': [],
                'progress': {},
                'errors': [],
                'pending_required': [],
                'review_text': [],
                'active_element': {},
                'warnings': [],
            }
            mock_surface.return_value = surface_response

            result: JsonObject = asyncio.run(
                page_click_primary_action(
                    client_id='test',
                    tab_id='tab-test',
                )
            )
            assert isinstance(result, dict)


class TestUploadPrep:
    def test_rejects_outside_allowlist(self) -> None:
        from pydoll_mcp_server.tools.upload_prep import artifact_prepare_upload

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            result: JsonObject = asyncio.run(
                artifact_prepare_upload(
                    client_id='test',
                    source_path='C:/Windows/System32/file.pdf',
                )
            )
            assert result.get('success') is not True
            assert result.get('error_code') == 'PERMISSION_DENIED'

    def test_denied_response_includes_dirs(self) -> None:
        from pydoll_mcp_server.tools.upload_prep import artifact_prepare_upload

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            result: JsonObject = asyncio.run(
                artifact_prepare_upload(
                    client_id='test',
                    source_path='/nonexistent/file.pdf',
                )
            )
            assert result.get('success') is not True
            details = result.get('details', {})
            assert isinstance(details, dict)
            assert 'allowed_directories' in details or 'message' in result


class TestSubmissionConfirmation:
    def test_returns_structured_status(self) -> None:
        from pydoll_mcp_server.tools.submission import submission_wait_for_confirmation

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(return_value='Application submitted')

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.submission.get_registry') as mock_registry,
            patch(
                'pydoll_mcp_server.tools.submission.get_tab_url',
                return_value='http://test/form',
            ),
        ):
            mock_tab_info = MagicMock()
            mock_tab_info.pydoll_tab = mock_tab
            mock_tab_info.tab_id = 'tab-test'
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            result: JsonObject = asyncio.run(
                submission_wait_for_confirmation(
                    client_id='test',
                    tab_id='tab-test',
                    success_text_any=['submitted'],
                    timeout=0.5,
                )
            )
            assert isinstance(result, dict)
            assert result.get('success') is True
            assert result.get('status') in ('confirmed', 'submitted_uncertain', 'blocked', 'failed')


class TestErrorCodeAmbiguous:
    def test_ambiguous_element_error_code_exists(self) -> None:
        from pydoll_mcp_server.errors import ErrorCode

        assert hasattr(ErrorCode, 'AMBIGUOUS_ELEMENT')
        assert ErrorCode.AMBIGUOUS_ELEMENT.value == 'AMBIGUOUS_ELEMENT'
