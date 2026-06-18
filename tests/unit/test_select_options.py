"""Unit tests for native select option retrieval."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


class TestSelectGetOptions:
    def test_returns_limited_native_select_options(self) -> None:
        from pydoll_mcp_server.tools.form_controls import select_get_options

        mock_element = MagicMock()
        mock_element.execute_script = AsyncMock(
            return_value={
                'result': {
                    'result': {
                        'value': {
                            'options': [
                                {'text': 'United States', 'value': 'us', 'label': 'United States', 'selected': True},
                                {'text': 'Brazil', 'value': 'br', 'label': 'Brazil', 'selected': False},
                            ],
                            'count': 250,
                            'partial': True,
                            'hidden_or_collapsed_options_count': 248,
                        }
                    }
                }
            }
        )

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.form_controls.get_registry') as mock_registry,
            patch('pydoll_mcp_server.tools.form_controls.resolve_element', AsyncMock(return_value=mock_element)),
        ):
            mock_registry.return_value.get_tab.return_value = MagicMock()
            result = asyncio.run(select_get_options('test', 'tab-test', 'el_select', max_options=2))

            assert result.get('success') is True
            assert result.get('count') == 250
            assert result.get('partial') is True
            assert result.get('hidden_or_collapsed_options_count') == 248
            options = result.get('options')
            assert isinstance(options, list)
            assert len(options) == 2

    def test_rejects_non_select_element(self) -> None:
        from pydoll_mcp_server.tools.form_controls import select_get_options

        mock_element = MagicMock()
        mock_element.execute_script = AsyncMock(
            return_value={'result': {'result': {'value': {'error': 'not_select', 'tag': 'INPUT'}}}}
        )

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.form_controls.get_registry') as mock_registry,
            patch('pydoll_mcp_server.tools.form_controls.resolve_element', AsyncMock(return_value=mock_element)),
        ):
            mock_registry.return_value.get_tab.return_value = MagicMock()
            result = asyncio.run(select_get_options('test', 'tab-test', 'el_input'))

            assert result.get('success') is not True
            assert result.get('error_code') == 'INVALID_INPUT'

    def test_stale_select_element_returns_stale(self) -> None:
        from pydoll_mcp_server.tools.form_controls import select_get_options

        with (
            patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}),
            patch('pydoll_mcp_server.tools.form_controls.get_registry') as mock_registry,
            patch('pydoll_mcp_server.tools.form_controls.resolve_element', AsyncMock(return_value=None)),
        ):
            mock_registry.return_value.get_tab.return_value = MagicMock()
            result = asyncio.run(select_get_options('test', 'tab-test', 'el_missing'))

            assert result.get('success') is not True
            assert result.get('error_code') == 'STALE_ELEMENT'
