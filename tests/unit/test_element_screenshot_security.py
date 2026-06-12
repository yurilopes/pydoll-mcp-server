"""Tests for element screenshot path validation."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


class TestElementScreenshotSecurity:
    def test_rejects_absolute_forbidden_path(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.tools.elements import element_screenshot

        forbidden = (
            'C:\\Windows\\Temp\\forbidden.png'
            if os.name == 'nt'
            else '/etc/forbidden.png'
        )

        mock_element = MagicMock()
        mock_element.take_screenshot = AsyncMock()

        with (
            patch(
                'pydoll_mcp_server.tools.elements.get_registry'
            ) as mock_registry,
            patch(
                'pydoll_mcp_server.tools.elements._resolve_element',
                return_value=mock_element,
            ),
        ):
            mock_tab_info = MagicMock()
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            import asyncio

            async def run():
                return await element_screenshot(
                    'test-client', 'tab-test', 'el-test',
                    path=forbidden,
                )

            result = asyncio.run(run())

            assert result.get('success') is not True, (
                f'Should reject forbidden path: {result}'
            )
            error_code = result.get('error_code', '')
            assert 'PERMISSION_DENIED' in error_code, (
                f'Expected PERMISSION_DENIED, got: {result}'
            )
            mock_element.take_screenshot.assert_not_called()

    def test_accepts_valid_relative_path(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.tools.elements import element_screenshot

        mock_element = MagicMock()
        mock_element.take_screenshot = AsyncMock(return_value='fake-data')

        with (
            patch(
                'pydoll_mcp_server.tools.elements.get_registry'
            ) as mock_registry,
            patch(
                'pydoll_mcp_server.tools.elements._resolve_element',
                return_value=mock_element,
            ),
        ):
            mock_tab_info = MagicMock()
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            import asyncio

            async def run():
                return await element_screenshot(
                    'test-client', 'tab-test', 'el-test',
                    path='screenshot.png',
                )

            result = asyncio.run(run())

            assert result.get('success') is True, f'Should accept: {result}'

    def test_base64_no_path_accepted(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.tools.elements import element_screenshot

        mock_element = MagicMock()
        mock_element.take_screenshot = AsyncMock(return_value='base64data')

        with (
            patch(
                'pydoll_mcp_server.tools.elements.get_registry'
            ) as mock_registry,
            patch(
                'pydoll_mcp_server.tools.elements._resolve_element',
                return_value=mock_element,
            ),
        ):
            mock_tab_info = MagicMock()
            mock_tab_info.tab_id = 'tab-test'
            mock_tab_info.document_generation = 1
            mock_registry.return_value.get_tab.return_value = mock_tab_info

            import asyncio

            async def run():
                return await element_screenshot(
                    'test-client', 'tab-test', 'el-test',
                )

            result = asyncio.run(run())

            assert result.get('success') is True
            assert result.get('data') == 'base64data'
