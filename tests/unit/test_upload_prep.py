"""Unit tests for upload artifact preparation."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from pydoll_mcp_server.json_types import JsonObject, get_object, get_string

pytestmark = [pytest.mark.unit]


class TestUploadPrep:
    def test_prepare_accepts_local_source_outside_runtime(self, tmp_path: Path) -> None:
        from pydoll_mcp_server.config import get_config
        from pydoll_mcp_server.tools.upload_prep import artifact_prepare_upload

        source = tmp_path / 'generated-resume.pdf'
        source.write_bytes(b'%PDF-1.4 local source')
        runtime = tmp_path / 'runtime'
        with patch.dict(
            os.environ,
            {
                'PYDOLL_MCP_AUTH_TOKEN': 'test-token',
                'PYDOLL_MCP_RUNTIME_DIR': str(runtime),
                'PYDOLL_MCP_UPLOAD_POLICY': 'local',
            },
        ):
            get_config.cache_clear()
            result: JsonObject = asyncio.run(
                artifact_prepare_upload(
                    client_id='test',
                    source_path=str(source),
                )
            )

        assert result.get('success') is True
        evidence = get_object(result, 'evidence', {})
        assert get_string(evidence, 'source') == str(source.resolve())
        get_config.cache_clear()

    def test_rejects_outside_allowlist(self) -> None:
        from pydoll_mcp_server.tools.upload_prep import artifact_prepare_upload

        with patch.dict(
            os.environ,
            {'PYDOLL_MCP_AUTH_TOKEN': 'test-token', 'PYDOLL_MCP_UPLOAD_POLICY': 'restricted'},
        ):
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

        with patch.dict(
            os.environ,
            {'PYDOLL_MCP_AUTH_TOKEN': 'test-token', 'PYDOLL_MCP_UPLOAD_POLICY': 'restricted'},
        ):
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
