"""Unit tests for upload artifact preparation."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

from pydoll_mcp_server.json_types import JsonObject

pytestmark = [pytest.mark.unit]


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
