"""Integration tests for browser operations (requires Chrome/Pydoll)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.browser, pytest.mark.slow]


@pytest.mark.asyncio
async def test_can_import_pydoll() -> None:
    try:
        from pydoll.browser import Chrome
        from pydoll.browser.options import ChromiumOptions

        assert Chrome is not None
        assert ChromiumOptions is not None
    except ImportError as e:
        pytest.skip(f'Pydoll not installed: {e}')


@pytest.mark.asyncio
async def test_can_import_server_modules() -> None:
    with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test'}):
        from pydoll_mcp_server.browser.locks import get_lock_manager
        from pydoll_mcp_server.browser.profiles import get_profile_manager
        from pydoll_mcp_server.browser.registry import get_registry
        from pydoll_mcp_server.config import get_config

        assert get_config() is not None
        assert get_registry() is not None
        assert get_profile_manager() is not None
        assert get_lock_manager() is not None
