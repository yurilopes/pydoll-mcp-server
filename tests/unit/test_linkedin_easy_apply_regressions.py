"""Regression tests for live LinkedIn Easy Apply failure modes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from pydoll_mcp_server.json_types import JsonObject, require_json_object

pytestmark = [pytest.mark.unit]


def test_open_recovers_when_modal_appears_after_no_effect() -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_open

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
            new=AsyncMock(return_value={'success': True, 'form_present': False, 'submitted': False}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin._click_resolved_action',
            new=AsyncMock(return_value={'error_code': 'NO_EFFECT', 'success': False}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_wait_ready',
            new=AsyncMock(return_value={'success': True, 'surface': 'dialog', 'form_present': True}),
        ),
    ):
        result = asyncio.run(linkedin_easy_apply_open('client', 'tab', timeout_ms=1000))

    assert result['success'] is True
    assert result['click_sent'] is True
    assert result['effect_observed'] is True
    assert result['recovery_attempted'] is True


def test_open_uses_verified_apply_anchor_when_action_resolver_misses_link() -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_open

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
            new=AsyncMock(return_value={'success': True, 'form_present': False, 'submitted': False}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_job_snapshot',
            new=AsyncMock(return_value={'success': True, 'linkedin_job_id': '123'}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin._click_resolved_action',
            new=AsyncMock(return_value={'success': False, 'error_code': 'RESOURCE_NOT_FOUND'}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_apply_link.element_find_by_text',
            new=AsyncMock(
                return_value={
                    'success': True,
                    'elements': [
                        {'element_id': 'el_apply', 'tag': 'a', 'text': 'Candidatura simplificada'},
                    ],
                }
            ),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_apply_link.element_get_attribute',
            new=AsyncMock(
                return_value={'success': True, 'value': 'https://www.linkedin.com/jobs/view/123/apply/'},
            ),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_apply_link.page_goto',
            new=AsyncMock(return_value={'success': True, 'url': 'https://www.linkedin.com/jobs/view/123/'}),
        ) as goto,
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_wait_ready',
            new=AsyncMock(
                return_value={
                    'success': True,
                    'surface': 'dialog',
                    'form_present': True,
                    'url': 'https://www.linkedin.com/jobs/view/123/',
                }
            ),
        ),
    ):
        result = asyncio.run(linkedin_easy_apply_open('client', 'tab', timeout_ms=1000))

    assert result['success'] is True
    assert result['open_mode'] == 'direct_apply_link'
    assert result['navigation_fallback'] is True
    assert result['click_sent'] is False
    goto.assert_awaited_once()


def test_upload_falls_back_to_localized_visible_trigger() -> None:
    from pydoll_mcp_server.tools.linkedin_upload import upload_from_localized_trigger

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin_upload.element_find_by_text_candidates',
            new=AsyncMock(
                return_value={
                    'success': True,
                    'candidates': [
                        {'element_id': 'el_upload', 'tag': 'label', 'enabled': True},
                    ],
                }
            ),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin_upload.upload_files_from_trigger',
            new=AsyncMock(return_value={'success': True, 'strategy_used': 'chooser_intercept'}),
        ) as upload,
    ):
        result = asyncio.run(
            upload_from_localized_trigger(
                'client',
                'tab',
                'C:/resume.pdf',
                'resume.pdf',
                1000,
            )
        )

    assert result is not None
    assert result['success'] is True
    upload.assert_awaited_once()
    assert upload.await_args is not None
    assert upload.await_args.kwargs['trigger_element_id'] == 'el_upload'


def test_open_rejects_non_modal_inline_surface() -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_open

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
            new=AsyncMock(return_value={'success': True, 'form_present': False, 'submitted': False}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin._click_resolved_action',
            new=AsyncMock(return_value={'success': True, 'click_sent': True}),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_wait_ready',
            new=AsyncMock(return_value={'success': True, 'surface': 'inline', 'form_present': True}),
        ),
    ):
        result = asyncio.run(linkedin_easy_apply_open('client', 'tab', timeout_ms=1000))

    assert result['error_code'] == 'NO_EFFECT'
    details = require_json_object(result.get('details'), 'error details')
    snapshot = require_json_object(details.get('snapshot'), 'snapshot')
    assert snapshot.get('surface') == 'inline'


def test_fill_questions_accepts_legacy_map_input() -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_fill_questions

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin._execute_mutating_script',
            new=AsyncMock(
                return_value={
                    'success': True,
                    'filled': [{'question_contains': 'Email address', 'status': 'filled', 'verification': True}],
                    'unfilled': [],
                    'ambiguous': [],
                    'radio_actions': [],
                    'blockers': [],
                }
            ),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
            new=AsyncMock(return_value={'success': True, 'authorization_risk': False, 'risk_text': ''}),
        ),
    ):
        result = asyncio.run(linkedin_easy_apply_fill_questions('client', 'tab', {'Email address': 'yuri@example.com'}))

    assert result['success'] is True
    assert result['input_format'] == 'map'
    assert result['requested_count'] == 1
    assert result['filled_count'] == 1


def test_fill_questions_preserves_script_error() -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_fill_questions

    with patch(
        'pydoll_mcp_server.tools.linkedin._execute_mutating_script',
        new=AsyncMock(
            return_value={
                'success': False,
                'error_code': 'EXECUTION_ERROR',
                'message': 'Script result must be a JSON object',
            }
        ),
    ):
        result = asyncio.run(
            linkedin_easy_apply_fill_questions(
                'client', 'tab', [{'question_contains': 'Email address', 'value': 'yuri@example.com'}]
            )
        )

    assert result['success'] is False
    assert result['error_code'] == 'EXECUTION_ERROR'
    assert result['filled_count'] == 0
    assert result['unfilled_count'] == 1


def test_submit_does_not_retry_after_unobserved_click() -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_submit

    snapshots: list[JsonObject] = [
        {'success': True, 'is_final_submit_step': True, 'pending_required': [], 'inline_errors': []},
        {'success': True, 'submitted': False, 'application_status': '', 'url': 'https://www.linkedin.com/jobs/view/1/'},
    ]

    async def snapshot_side_effect(*_args: object) -> JsonObject:
        return snapshots.pop(0)

    with (
        patch(
            'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
            new=AsyncMock(side_effect=snapshot_side_effect),
        ),
        patch(
            'pydoll_mcp_server.tools.linkedin._click_resolved_action',
            new=AsyncMock(return_value={'success': True, 'click': {'clicked': True}}),
        ) as click,
    ):
        result = asyncio.run(linkedin_easy_apply_submit('client', 'tab', confirm_submit=True, timeout_ms=1))

    assert result['error_code'] == 'NO_EFFECT'
    click.assert_awaited_once()
