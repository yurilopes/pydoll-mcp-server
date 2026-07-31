"""Unit tests for LinkedIn recruiter messaging."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from pydoll_mcp_server.json_types import JsonObject

pytestmark = [pytest.mark.unit]


def test_registration_exposes_only_the_composite_message_tool() -> None:
    from pydoll_mcp_server.tool_catalog import TOOLS

    names = {tool.__name__ for tool in TOOLS}
    assert 'linkedin_message_recruiter' in names
    assert 'linkedin_find_recruiter' not in names


def test_rejects_empty_message_before_page_access() -> None:
    from pydoll_mcp_server.tools.linkedin_recruiter import linkedin_message_recruiter

    with patch(
        'pydoll_mcp_server.tools.linkedin_recruiter.linkedin_job_snapshot',
        new=AsyncMock(side_effect=AssertionError('page must not be accessed')),
    ):
        result = asyncio.run(linkedin_message_recruiter('client', 'tab', '  '))

    assert result['error_code'] == 'INVALID_INPUT'


def test_requires_confirmed_submitted_application() -> None:
    from pydoll_mcp_server.tools.linkedin_recruiter import linkedin_message_recruiter

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.linkedin_job_snapshot',
            new=AsyncMock(return_value={'success': True, 'application_state': 'draft'}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.execute_script',
            new=AsyncMock(side_effect=AssertionError('recruiter must not be scanned')),
        ),
    ):
        result = asyncio.run(linkedin_message_recruiter('client', 'tab', 'Hello'))

    assert result['error_code'] == 'APPLICATION_NOT_CONFIRMED'
    details = result['details']
    assert isinstance(details, dict)
    assert details['failure_origin'] == 'validation'


def test_rejects_ambiguous_recruiter() -> None:
    from pydoll_mcp_server.tools.linkedin_recruiter import linkedin_message_recruiter

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.linkedin_job_snapshot',
            new=AsyncMock(return_value={'success': True, 'application_state': 'submitted'}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.execute_script',
            new=AsyncMock(
                return_value={
                    'success': True,
                    'recruiter_found': False,
                    'resolution': 'ambiguous',
                    'candidates': [{'name': 'A'}, {'name': 'B'}],
                }
            ),
        ),
    ):
        result = asyncio.run(linkedin_message_recruiter('client', 'tab', 'Hello'))

    assert result['error_code'] == 'AMBIGUOUS_RECRUITER'


def test_sends_once_and_waits_for_confirmation() -> None:
    from pydoll_mcp_server.tools.linkedin_recruiter import linkedin_message_recruiter

    script_results: list[JsonObject] = [
        {
            'success': True,
            'recruiter_found': True,
            'resolution': 'unique',
            'recruiter_name': 'Ana Recruiter',
            'message_button_selector': '#message-recruiter',
        },
        {
            'success': True,
            'composer_present': True,
            'composer_selector': '#composer',
        },
        {
            'success': True,
            'recruiter_found': True,
            'resolution': 'unique',
            'send_button_selector': '#send-message',
        },
        {
            'success': True,
            'confirmation_observed': True,
            'confirmation_text': 'Message sent',
        },
    ]

    async def scan(*_args: object, **_kwargs: object) -> JsonObject:
        return script_results.pop(0) if script_results else {'success': True, 'confirmation_observed': False}

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.linkedin_job_snapshot',
            new=AsyncMock(return_value={'success': True, 'application_state': 'submitted'}),
        ),
        patch('pydoll_mcp_server.tools.linkedin_recruiter.execute_script', new=AsyncMock(side_effect=scan)),
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.element_find',
            new=AsyncMock(return_value={'success': True, 'element_id': 'element-1'}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.element_fill',
            new=AsyncMock(return_value={'success': True, 'verified': True}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.click_selector',
            new=AsyncMock(return_value={'success': True, 'clicked': True}),
        ) as click,
    ):
        result = asyncio.run(linkedin_message_recruiter('client', 'tab', 'Hello Ana, I applied for this role.'))

    assert result['success'] is True
    assert result['sent'] is True
    assert result['confirmation_observed'] is True
    assert click.await_count == 2


def test_inconclusive_confirmation_does_not_retry_send() -> None:
    from pydoll_mcp_server.tools.linkedin_recruiter import linkedin_message_recruiter

    script_results: list[JsonObject] = [
        {
            'success': True,
            'recruiter_found': True,
            'resolution': 'unique',
            'recruiter_name': 'Ana Recruiter',
            'message_button_selector': '#message-recruiter',
        },
        {'success': True, 'composer_present': True, 'composer_selector': '#composer'},
        {'success': True, 'send_button_selector': '#send-message'},
        {'success': True, 'confirmation_observed': False},
    ]

    async def scan(*_args: object, **_kwargs: object) -> JsonObject:
        return script_results.pop(0) if script_results else {'success': True, 'confirmation_observed': False}

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.linkedin_job_snapshot',
            new=AsyncMock(return_value={'success': True, 'application_state': 'submitted'}),
        ),
        patch('pydoll_mcp_server.tools.linkedin_recruiter.execute_script', new=AsyncMock(side_effect=scan)),
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.element_find',
            new=AsyncMock(return_value={'success': True, 'element_id': 'element-1'}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.element_fill',
            new=AsyncMock(return_value={'success': True, 'verified': True}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_recruiter.click_selector',
            new=AsyncMock(return_value={'success': True, 'clicked': True}),
        ) as click,
    ):
        result = asyncio.run(linkedin_message_recruiter('client', 'tab', 'Hello Ana', timeout_ms=1))

    assert result['error_code'] == 'NO_EFFECT'
    assert click.await_count == 2


def test_recruiter_scripts_do_not_use_dom_click() -> None:
    from pydoll_mcp_server.tools.linkedin_recruiter_scripts import (
        recruiter_confirmation_script,
        recruiter_surface_script,
    )

    source = recruiter_surface_script() + recruiter_confirmation_script('Hello')
    assert '.click(' not in source
    assert 'showInMail' not in source
    assert 'connection' not in source.lower()
