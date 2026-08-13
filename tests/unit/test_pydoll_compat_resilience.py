"""Tests for resilient handling of transient Pydoll element responses."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_hidden_element_text_failure_is_non_fatal() -> None:
    from pydoll_mcp_server.browser.pydoll_compat import get_element_text

    element = AsyncMock()
    type(element).text = property(lambda _self: _raise_key_error())

    assert asyncio.run(get_element_text(element)) == ''


def _raise_key_error() -> str:
    raise KeyError('result')


def test_linkedin_resume_upload_falls_back_after_native_transport_failure() -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_upload_resume

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin_upload._execute_script',
            new=AsyncMock(
                side_effect=[
                    {'success': True, 'target': {'selector_hint': '#resume-file'}},
                    {'success': True, 'target': {'selector_hint': '#upload-button'}},
                ]
            ),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_upload.element_find',
            new=AsyncMock(return_value={'success': True, 'element_id': 'el_file'}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_upload.upload_files',
            new=AsyncMock(
                return_value={
                    'success': False,
                    'error_code': 'EXECUTION_ERROR',
                    'details': {'reason': 'native_upload_transport_error'},
                }
            ),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_upload._upload_with_file_chooser',
            new=AsyncMock(
                return_value={
                    'success': True,
                    'uploaded': True,
                    'strategy_used': 'chooser_intercept',
                }
            ),
        ) as chooser,
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
            new=AsyncMock(
                return_value={
                    'success': True,
                    'uploads': {'selected_or_latest_resume': 'resume.pdf'},
                    'toast_messages': [],
                }
            ),
        ),
    ):
        result = asyncio.run(
            linkedin_easy_apply_upload_resume(
                'client',
                'tab',
                r'C:\tmp\resume.pdf',
                expected_filename='resume.pdf',
                timeout_ms=1000,
            )
        )

    assert result['uploaded'] is True
    assert result['upload_verified'] is True
    chooser.assert_awaited_once()
