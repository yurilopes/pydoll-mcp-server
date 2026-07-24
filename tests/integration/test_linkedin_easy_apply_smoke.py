"""Browser smoke tests for LinkedIn-specific surfaces and actions."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from pydoll_mcp_server.json_types import get_array, get_object, get_string, require_json_object
from tests.integration.test_browser_smoke import launch_and_goto_fixture, register_smoke_tab, stop_smoke_browser

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]


@pytest.mark.asyncio
async def test_inline_easy_apply_snapshot_fill_and_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.tools.linkedin import (
        linkedin_easy_apply_click_next,
        linkedin_easy_apply_fill_questions,
        linkedin_easy_apply_snapshot,
        linkedin_easy_apply_submit,
    )
    from pydoll_mcp_server.tools.linkedin_search import linkedin_application_evidence

    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    browser, tab = await launch_and_goto_fixture('linkedin-easy-apply-inline.html')
    try:
        info = await register_smoke_tab(browser, tab, 'linkedin-inline-smoke')
        initial = await linkedin_easy_apply_snapshot('linkedin-inline-smoke', info.tab_id)
        assert initial.get('success') is True
        assert initial.get('surface') == 'inline'
        assert initial.get('form_present') is True
        assert initial.get('step_title') == 'Additional Questions'
        assert initial.get('step_index') == 3
        assert initial.get('step_count') == 4

        filled = await linkedin_easy_apply_fill_questions(
            'linkedin-inline-smoke',
            info.tab_id,
            [
                {'question_contains': 'UiPath', 'value': '3'},
                {'question_contains': 'Python (Programming Language)', 'value': '4'},
                {'question_contains': 'written your own code', 'value': 'Yes'},
                {'question_contains': 'W2', 'option_text': 'No'},
            ],
        )
        assert filled.get('success') is True, filled
        assert filled.get('unfilled') == []
        assert filled.get('ambiguous') == []
        assert filled.get('authorization_risk') is True

        review = await linkedin_easy_apply_click_next('linkedin-inline-smoke', info.tab_id, expected_current_step=3)
        assert review.get('success') is True
        assert review.get('surface') == 'inline'
        assert review.get('is_final_submit_step') is True
        assert review.get('step_index') == 4
        assert review.get('step_count') == 4
        review_summary = get_object(review, 'review_summary', {})
        assert get_array(review_summary, 'answers', [])

        evidence = await linkedin_application_evidence('linkedin-inline-smoke', info.tab_id)
        assert evidence.get('success') is True, evidence
        assert evidence.get('application_state') == 'draft'
        assert evidence.get('resume_filename') == 'Yuri_Abreu__automation_engineer__example_automation.pdf'
        assert len(get_array(evidence, 'answers', [])) >= 3

        refused = await linkedin_easy_apply_submit('linkedin-inline-smoke', info.tab_id)
        assert refused.get('error_code') == 'INVALID_INPUT'

        submitted = await linkedin_easy_apply_submit(
            'linkedin-inline-smoke', info.tab_id, confirm_submit=True, timeout_ms=3000
        )
        assert submitted.get('success') is True, submitted
        assert submitted.get('submitted') is True
        assert submitted.get('confirmation_text') == 'Application submitted'
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_radio_groups_with_preceding_questions_survive_re_render(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.tools.form_choice import form_select_choice
    from pydoll_mcp_server.tools.linkedin import (
        linkedin_easy_apply_click_next,
        linkedin_easy_apply_fill_questions,
        linkedin_easy_apply_snapshot,
    )
    from pydoll_mcp_server.tools.semantic_actions import element_click_by_text

    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    browser, tab = await launch_and_goto_fixture('linkedin-easy-apply-radio-groups.html')
    try:
        info = await register_smoke_tab(browser, tab, 'linkedin-radio-groups-smoke')
        initial = await linkedin_easy_apply_snapshot('linkedin-radio-groups-smoke', info.tab_id)
        assert initial.get('success') is True
        assert initial.get('step_title') == 'Additional Questions'
        assert initial.get('is_review_step') is False
        initial_questions = get_array(initial, 'questions', [])
        assert len(initial_questions) == 4
        assert len(get_array(initial, 'pending_required', [])) == 4
        first_question = require_json_object(initial_questions[0], 'first question')
        assert first_question['input_type'] == 'radio'
        assert first_question['options'] == ['Yes', 'No']
        assert get_string(first_question, 'label').startswith('Are you comfortable working in a remote setting')

        ordinal_click = await element_click_by_text(
            'linkedin-radio-groups-smoke',
            info.tab_id,
            'Yes',
            role='radio',
            match_index=2,
        )
        assert ordinal_click.get('success') is True, ordinal_click
        ordinal_snapshot = await linkedin_easy_apply_snapshot('linkedin-radio-groups-smoke', info.tab_id)
        ordinal_questions = get_array(ordinal_snapshot, 'questions', [])
        assert get_string(require_json_object(ordinal_questions[2], 'third question'), 'selected_option') == 'Yes'

        generic_choice = await form_select_choice(
            'linkedin-radio-groups-smoke',
            info.tab_id,
            'remote setting',
            'Yes',
        )
        assert generic_choice.get('success') is True, generic_choice
        assert generic_choice.get('verified') is True

        filled = await linkedin_easy_apply_fill_questions(
            'linkedin-radio-groups-smoke',
            info.tab_id,
            [
                {'question_contains': 'remote setting', 'option_text': 'Yes'},
                {'question_contains': 'background check', 'option_text': 'Yes'},
                {'question_contains': 'drug test', 'option_text': 'No'},
                {'question_contains': 'work eligibility', 'option_text': 'No'},
            ],
        )
        assert filled.get('success') is True, filled
        assert filled.get('unfilled') == []
        assert filled.get('ambiguous') == []
        snapshot = get_object(filled, 'snapshot')
        assert snapshot.get('pending_required') == []
        selected = [
            get_string(require_json_object(question, 'question'), 'selected_option')
            for question in get_array(snapshot, 'questions', [])
        ]
        assert selected == ['Yes', 'Yes', 'No', 'No']

        review = await linkedin_easy_apply_click_next(
            'linkedin-radio-groups-smoke',
            info.tab_id,
            expected_current_step=3,
        )
        assert review.get('success') is True, review
        assert review.get('step_index') == 4
        assert review.get('is_review_step') is True
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_dialog_easy_apply_open_and_close_save_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.tools.linkedin import (
        linkedin_easy_apply_close,
        linkedin_easy_apply_handle_save_prompt,
        linkedin_easy_apply_open,
    )

    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    browser, tab = await launch_and_goto_fixture('linkedin-easy-apply.html')
    try:
        info = await register_smoke_tab(browser, tab, 'linkedin-dialog-smoke')
        opened = await linkedin_easy_apply_open('linkedin-dialog-smoke', info.tab_id, timeout_ms=5000)
        assert opened.get('success') is True, opened
        assert opened.get('surface') == 'dialog'
        assert opened.get('dialog_present') is True
        assert opened.get('step_title') == 'Contact info'

        closed = await linkedin_easy_apply_close('linkedin-dialog-smoke', info.tab_id)
        assert closed.get('success') is True, closed
        assert closed.get('save_prompt_visible') is True

        discarded = await linkedin_easy_apply_handle_save_prompt('linkedin-dialog-smoke', info.tab_id, 'discard')
        assert discarded.get('success') is True, discarded
        assert discarded.get('prompt_action') == 'discard'
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_linkedin_search_snapshot_scopes_detail_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_open, linkedin_job_snapshot
    from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_open_result, linkedin_jobs_page_snapshot

    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    browser, tab = await launch_and_goto_fixture('linkedin-search-panel.html')
    try:
        info = await register_smoke_tab(browser, tab, 'linkedin-search-smoke')
        snapshot = await linkedin_jobs_page_snapshot('linkedin-search-smoke', info.tab_id)
        assert snapshot.get('success') is True
        assert snapshot.get('selected_job_id') == '101'
        assert snapshot.get('detail_panel_present') is True
        assert snapshot.get('detail_surface') == 'panel'
        detail = snapshot.get('detail_job_snapshot')
        assert isinstance(detail, dict)
        assert detail.get('role') == 'Full Stack Developer'
        assert detail.get('company') == 'Example Software'
        assert detail.get('application_state') == 'not_started'
        assert detail.get('easy_apply_button_text') == 'Easy Apply'
        assert detail.get('easy_apply_button_aria') == 'Use Easy Apply for this job'
        assert snapshot.get('has_next_page') is True
        results = get_array(snapshot, 'results', [])
        assert any(isinstance(item, dict) and item.get('linkedin_job_id') == '303' for item in results)

        opened = await linkedin_jobs_open_result(
            'linkedin-search-smoke',
            info.tab_id,
            linkedin_job_id='101',
            timeout_ms=5000,
        )
        assert opened.get('success') is True, opened
        assert opened.get('opened_from_result') is True
        assert opened.get('open_mode') == 'panel'
        assert opened.get('search_context_preserved') is True

        expected_states = {
            'not_started': ('not_started', 'easy_apply'),
            'draft': ('draft', 'continue'),
            'submitted': ('submitted', 'applied'),
            'saved': ('saved', 'saved'),
            'unavailable': ('unavailable', 'unavailable'),
        }
        for state, expected in expected_states.items():
            await tab.execute_script(f"window.setLinkedInJobState('{state}')", return_by_value=True)
            job = await linkedin_job_snapshot('linkedin-search-smoke', info.tab_id)
            assert (job.get('application_state'), job.get('button_state')) == expected

        await tab.execute_script("window.setLinkedInJobState('not_started')", return_by_value=True)
        apply = await linkedin_easy_apply_open('linkedin-search-smoke', info.tab_id, timeout_ms=5000)
        assert apply.get('success') is True, apply
        assert apply.get('surface') == 'inline'
        assert apply.get('form_present') is True
        assert apply.get('step_title') == 'Contact info'
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_inline_easy_apply_upload_requires_filename_and_toast(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_upload_resume

    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    browser, tab = await launch_and_goto_fixture('linkedin-easy-apply-upload.html')
    try:
        client_id = 'linkedin-upload-smoke'
        info = await register_smoke_tab(browser, tab, client_id)
        runtime_dir = Path(tempfile.gettempdir()) / 'pydoll-mcp-server-smoke' / 'tmp' / client_id
        runtime_dir.mkdir(parents=True, exist_ok=True)
        resume = runtime_dir / 'dedicated-resume.pdf'
        resume.write_bytes(b'%PDF-1.4\nfixture\n')

        result = await linkedin_easy_apply_upload_resume(
            client_id,
            info.tab_id,
            str(resume),
            expected_filename=resume.name,
            timeout_ms=5000,
        )
        assert result.get('success') is True, result
        assert result.get('uploaded') is True
        assert result.get('upload_verified') is True
        assert result.get('filename') == resume.name
        assert result.get('toast_confirmed') is True
        snapshot = get_object(result, 'snapshot', {})
        assert get_array(snapshot, 'toast_messages', []) == ['Resume uploaded']
        assert get_array(snapshot, 'inline_errors', []) == []
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.asyncio
async def test_native_picker_upload_reports_headless_unsupported_without_dialog_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydoll_mcp_server.tools.linkedin import linkedin_easy_apply_upload_resume

    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    browser, tab = await launch_and_goto_fixture('linkedin-easy-apply-native-picker.html')
    try:
        client_id = 'linkedin-native-picker-smoke'
        info = await register_smoke_tab(browser, tab, client_id)
        runtime_dir = Path(tempfile.gettempdir()) / 'pydoll-mcp-server-smoke' / 'tmp' / client_id
        runtime_dir.mkdir(parents=True, exist_ok=True)
        resume = runtime_dir / 'native-picker-resume.pdf'
        resume.write_bytes(b'%PDF-1.4\nfixture\n')

        result = await linkedin_easy_apply_upload_resume(
            client_id,
            info.tab_id,
            str(resume),
            expected_filename=resume.name,
            timeout_ms=5000,
        )

        assert result.get('error_code') == 'UNSUPPORTED', result
        details = get_object(result, 'details', {})
        assert get_string(details, 'reason') == 'native_picker_requires_visible_browser'
        assert get_string(result, 'strategy_requested') == 'auto'
    finally:
        await stop_smoke_browser(browser)
