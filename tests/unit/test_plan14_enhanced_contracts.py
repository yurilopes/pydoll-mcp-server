"""Unit tests for PLAN_14 enhanced tool contracts (params verification)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest
from pydoll.browser.tab import Tab

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_click_observation_preserves_delayed_route_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.tools import click_observation

    urls = iter(('https://example.test/start', 'https://example.test/application'))
    tab = object.__new__(Tab)
    monkeypatch.setattr(
        tab,
        'execute_script',
        AsyncMock(return_value={'result': {'result': {'type': 'boolean', 'value': False}}}),
    )

    async def fake_get_tab_url(_tab: object) -> str:
        return next(urls, 'https://example.test/application')

    monkeypatch.setattr(click_observation, 'get_tab_url', fake_get_tab_url)

    observed, matched = await click_observation.observe_effects(
        'tab-id',
        tab,
        'https://example.test/start',
        False,
        False,
        'Full name',
        '',
        False,
        0.2,
    )

    assert observed is True
    assert 'url_changed' in matched
    assert 'expect_text' not in matched


def test_public_fill_state_is_consistent_without_exposing_values() -> None:
    from pydoll_mcp_server.tools.form_controls import build_public_fill_state

    state = build_public_fill_state(
        {
            'value': 'Yuri Abreu',
            'framework_value': 'present',
            'controlled_value_survived': True,
            'input_type': 'text',
            'ready_for_submission': False,
        },
        ready_for_submission=True,
    )

    assert state['value_present'] is True
    assert state['value_length'] == 10
    assert state['dom_value'] == '[PRESENT]'
    assert state['framework_value'] == 'present'
    assert state['ready_for_submission'] is True
    assert state.get('value') is None


def test_process_liveness_check_accepts_a_live_windows_process() -> None:
    from pydoll_mcp_server.tools.diagnostics import is_process_alive

    assert is_process_alive(os.getpid()) is True
    assert is_process_alive(2_147_483_647) is False


class TestUploadFilesEnhanced:
    def test_upload_files_accepts_new_params(self) -> None:
        import inspect

        from pydoll_mcp_server.tools.files import upload_files

        sig = inspect.signature(upload_files)
        params = list(sig.parameters.keys())
        assert 'expect_filename_visible' in params
        assert 'verify_timeout' in params


class TestElementClickEnhanced:
    def test_element_click_accepts_new_params(self) -> None:
        import inspect

        from pydoll_mcp_server.tools.elements import element_click

        sig = inspect.signature(element_click)
        params = list(sig.parameters.keys())
        assert 'click_strategy' in params
        assert 'expect_dialog' in params
        assert 'expect_text' in params
        assert 'expect_url_change' in params
        assert 'expect_selector' in params
        assert 'expect_network_idle' in params
        assert 'effect_timeout' in params


class TestElementClickByTextEnhanced:
    def test_element_click_by_text_accepts_new_params(self) -> None:
        import inspect

        from pydoll_mcp_server.tools.semantic_actions import element_click_by_text

        sig = inspect.signature(element_click_by_text)
        params = list(sig.parameters.keys())
        assert 'role' in params
        assert 'tag' in params
        assert 'within_element_id' in params
        assert 'nearest_heading' in params
        assert 'match_index' in params
        assert 'ambiguity_threshold' in params
        assert 'prefer_modal' in params
