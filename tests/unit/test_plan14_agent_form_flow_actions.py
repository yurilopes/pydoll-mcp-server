"""Unit tests for PLAN_14 action-oriented agent form flow tools."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.tools.form_fill import FormFillField

pytestmark = [pytest.mark.unit]


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

            fields: list[FormFillField] = [
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

            surface_response: JsonObject = {
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
