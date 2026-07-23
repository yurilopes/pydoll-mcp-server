"""Unit tests for LinkedIn Easy Apply tools."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pydoll_mcp_server.json_types import JsonObject, get_array, get_object

pytestmark = [pytest.mark.unit]


def _script_result(value: JsonObject) -> JsonObject:
    return {'result': {'result': {'value': value}}}


class TestLinkedInToolRegistration:
    def test_registers_linkedin_tools(self) -> None:
        from pydoll_mcp_server.tool_catalog import TOOLS

        names = {tool.__name__ for tool in TOOLS}
        assert 'linkedin_job_snapshot' in names
        assert 'linkedin_easy_apply_open' in names
        assert 'linkedin_easy_apply_snapshot' in names
        assert 'linkedin_easy_apply_close' in names
        assert 'linkedin_easy_apply_submit' in names
        assert 'linkedin_jobs_search' in names
        assert 'linkedin_jobs_search_results' in names
        assert 'linkedin_jobs_open_result' in names
        assert 'linkedin_jobs_page_snapshot' in names
        assert 'linkedin_application_evidence' in names


class TestLinkedInSnapshot:
    def test_snapshot_returns_dialog_scoped_payload(self) -> None:
        from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_snapshot

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value=_script_result(
                {
                    'success': True,
                    'dialog_present': True,
                    'step_index': 1,
                    'step_count': 4,
                    'step_title': 'Contact info',
                    'fields': [
                        {
                            'tag': 'select',
                            'label': 'Código do país',
                            'selected_text': ['Brasil (+55)'],
                            'selected_value': 'br',
                        }
                    ],
                    'questions': [],
                    'uploads': {},
                    'primary_action': {'text': 'Avançar'},
                    'secondary_actions': [],
                    'blocking_prompt': {},
                    'toast_messages': [],
                    'inline_errors': [],
                    'pending_required': [],
                    'review_summary': {},
                    'authorization_risk': False,
                    'risk_text': '',
                }
            )
        )
        with patch('pydoll_mcp_server.tools.linkedin_runtime.get_registry') as registry:
            tab_info = MagicMock()
            tab_info.pydoll_tab = mock_tab
            registry.return_value.get_tab.return_value = tab_info

            result = asyncio.run(linkedin_easy_apply_snapshot('client', 'tab'))

        assert result['success'] is True
        assert result['step_title'] == 'Contact info'
        fields = result['fields']
        assert isinstance(fields, list)
        field = fields[0]
        assert isinstance(field, dict)
        assert field['selected_text'] == ['Brasil (+55)']

    def test_job_snapshot_exposes_authorization_risk(self) -> None:
        from pydoll_mcp_server.tools.linkedin import linkedin_job_snapshot

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value=_script_result(
                {
                    'success': True,
                    'linkedin_job_id': '4429994998',
                    'company': 'TSR Consulting',
                    'role': 'Senior Full Stack Developer',
                    'button_state': 'easy_apply',
                    'authorization_risk': True,
                    'risk_text': 'Only GC Holders & US Citizen',
                }
            )
        )
        with patch('pydoll_mcp_server.tools.linkedin_runtime.get_registry') as registry:
            tab_info = MagicMock()
            tab_info.pydoll_tab = mock_tab
            registry.return_value.get_tab.return_value = tab_info

            result = asyncio.run(linkedin_job_snapshot('client', 'tab'))

        assert result['linkedin_job_id'] == '4429994998'
        assert result['button_state'] == 'easy_apply'
        assert result['authorization_risk'] is True

    @pytest.mark.parametrize(
        ('state', 'button_state'),
        [
            ('not_started', 'easy_apply'),
            ('draft', 'continue'),
            ('submitted', 'applied'),
            ('saved', 'saved'),
            ('unavailable', 'unavailable'),
        ],
    )
    def test_job_snapshot_exposes_application_state(self, state: str, button_state: str) -> None:
        from pydoll_mcp_server.tools.linkedin import linkedin_job_snapshot

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value=_script_result(
                {
                    'success': True,
                    'linkedin_job_id': '123',
                    'application_state': state,
                    'application_state_text': state,
                    'button_state': button_state,
                    'easy_apply_available': state in {'not_started', 'draft'},
                    'can_continue_easy_apply': state == 'draft',
                    'already_applied': state == 'submitted',
                }
            )
        )
        with patch('pydoll_mcp_server.tools.linkedin_runtime.get_registry') as registry:
            tab_info = MagicMock()
            tab_info.pydoll_tab = mock_tab
            registry.return_value.get_tab.return_value = tab_info

            result = asyncio.run(linkedin_job_snapshot('client', 'tab'))

        assert result['application_state'] == state
        assert result['button_state'] == button_state


class TestLinkedInActions:
    def test_open_uses_resolved_element_click(self) -> None:
        from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_open

        with (
            patch(
                'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
                new=AsyncMock(return_value={'success': True, 'form_present': False, 'submitted': False}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin._click_resolved_action',
                new=AsyncMock(return_value={'success': True, 'action': 'apply', 'click': {'clicked': True}}),
            ) as click,
            patch(
                'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_wait_ready',
                new=AsyncMock(return_value={'success': True, 'surface': 'dialog', 'form_present': True}),
            ),
        ):
            result = asyncio.run(linkedin_easy_apply_open('client', 'tab'))

        assert result['success'] is True
        click.assert_awaited_once()
        click_args = click.await_args
        assert click_args is not None
        assert click_args.args[2] == 'apply'

    def test_upload_resume_passes_paths_to_upload_files(self) -> None:
        from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_upload_resume

        with (
            patch(
                'pydoll_mcp_server.tools.linkedin_upload._click_resolved_action',
                new=AsyncMock(return_value={'success': True, 'clicked': True}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_upload._execute_script',
                new=AsyncMock(return_value={'success': True, 'target': {'selector_hint': '#resume-file'}}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_upload.element_find',
                new=AsyncMock(return_value={'success': True, 'element_id': 'el_file'}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_upload.upload_files',
                new=AsyncMock(return_value={'success': True, 'accepted': []}),
            ) as upload,
            patch(
                'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
                new=AsyncMock(
                    return_value={
                        'success': True,
                        'uploads': {'selected_or_latest_resume': 'resume.pdf'},
                        'toast_messages': ['O currículo foi carregado'],
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
        upload.assert_awaited_once()
        upload_args = upload.await_args
        assert upload_args is not None
        assert upload_args.kwargs['paths'] == [r'C:\tmp\resume.pdf']

    def test_submit_requires_confirmation(self) -> None:
        from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_submit

        result = asyncio.run(linkedin_easy_apply_submit('client', 'tab'))

        assert result['error_code'] == 'INVALID_INPUT'

    def test_submit_captures_confirmation_after_click(self) -> None:
        from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_submit

        snapshots: list[JsonObject] = [
            {'success': True, 'dialog_present': True, 'is_final_submit_step': True},
            {
                'success': True,
                'dialog_present': False,
                'submitted': True,
                'confirmation_text': 'Se candidatou agora',
                'application_status': 'submitted',
                'timestamp_text': 'agora',
            },
        ]

        async def snapshot_side_effect(client_id: str, tab_id: str) -> JsonObject:
            return snapshots.pop(0)

        with (
            patch(
                'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
                new=AsyncMock(side_effect=snapshot_side_effect),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin._click_resolved_action',
                new=AsyncMock(return_value={'success': True, 'clicked': True}),
            ),
        ):
            result = asyncio.run(linkedin_easy_apply_submit('client', 'tab', confirm_submit=True))

        assert result['submitted'] is True
        assert result['confirmation_text'] == 'Se candidatou agora'
        assert result['dialog_closed'] is True

    def test_fill_questions_returns_blockers_and_snapshot_risk(self) -> None:
        from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_fill_questions

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value=_script_result(
                {
                    'success': True,
                    'filled': [{'question_contains': 'W2', 'option_text': 'No'}],
                    'unfilled': [],
                    'ambiguous': [],
                    'blockers': ['Only GC Holders & US Citizen'],
                }
            )
        )
        with (
            patch('pydoll_mcp_server.tools.linkedin_runtime.get_registry') as registry,
            patch(
                'pydoll_mcp_server.tools.linkedin.linkedin_easy_apply_snapshot',
                new=AsyncMock(
                    return_value={
                        'success': True,
                        'authorization_risk': True,
                        'risk_text': 'Only GC Holders & US Citizen',
                    }
                ),
            ),
        ):
            tab_info = MagicMock()
            tab_info.pydoll_tab = mock_tab
            registry.return_value.get_tab.return_value = tab_info

            result = asyncio.run(
                linkedin_easy_apply_fill_questions(
                    'client',
                    'tab',
                    [{'question_contains': 'W2', 'option_text': 'No'}],
                )
            )

        assert result['success'] is True
        assert result['authorization_risk'] is True
        assert result['risk_text'] == 'Only GC Holders & US Citizen'


class TestLinkedInRuntime:
    def test_click_resolved_action_retries_with_pointer_after_no_effect(self) -> None:
        from pydoll_mcp_server.tools.linkedin_runtime import click_resolved_action

        before = {
            'success': True,
            'surface': 'none',
            'form_present': False,
            'prompt_present': False,
            'content_signature': 'job detail',
        }
        after_no_effect = {
            'success': True,
            'surface': 'none',
            'form_present': False,
            'prompt_present': False,
            'content_signature': 'job detail',
        }
        after_effect = {
            'success': True,
            'surface': 'dialog',
            'form_present': True,
            'prompt_present': False,
            'content_signature': 'Contact info',
        }
        resolution = {'success': True, 'surface': 'job_view', 'target': {'selector_hint': '#apply'}}
        clicks = [
            {'success': True, 'strategy_used': 'native'},
            {'success': True, 'strategy_used': 'dispatch_pointer_sequence'},
        ]
        with (
            patch(
                'pydoll_mcp_server.tools.linkedin_runtime.execute_script',
                new=AsyncMock(side_effect=[before, resolution, resolution]),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_runtime.click_selector',
                new=AsyncMock(side_effect=clicks),
            ) as click,
            patch(
                'pydoll_mcp_server.tools.linkedin_runtime._wait_for_action_state',
                new=AsyncMock(side_effect=[after_no_effect, after_effect]),
            ),
        ):
            result = asyncio.run(click_resolved_action('client', 'tab', 'apply', 3000))

        assert result['success'] is True
        assert result['effect_observed'] is True
        assert click.await_count == 2
        assert click.await_args_list[1].kwargs['click_strategy'] == 'dispatch_pointer_sequence'

    def test_click_resolved_action_returns_no_effect_after_failed_recovery(self) -> None:
        from pydoll_mcp_server.tools.linkedin_runtime import click_resolved_action

        state = {
            'success': True,
            'surface': 'none',
            'form_present': False,
            'prompt_present': False,
            'content_signature': 'unchanged',
        }
        resolution = {'success': True, 'surface': 'job_view', 'target': {'selector_hint': '#apply'}}
        with (
            patch(
                'pydoll_mcp_server.tools.linkedin_runtime.execute_script',
                new=AsyncMock(side_effect=[state, resolution, resolution]),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_runtime.click_selector',
                new=AsyncMock(return_value={'success': True}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_runtime._wait_for_action_state',
                new=AsyncMock(return_value=state),
            ),
        ):
            result = asyncio.run(click_resolved_action('client', 'tab', 'apply', 3000))

        assert result['error_code'] == 'NO_EFFECT'
        details = get_object(result, 'details', {})
        assert len(get_array(details, 'attempts', [])) == 2
