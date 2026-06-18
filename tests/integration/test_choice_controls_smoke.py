"""Browser smoke coverage for label-backed choice controls."""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch

import pytest

from pydoll_mcp_server.json_types import get_array, get_string, require_json_object
from tests.integration.test_browser_smoke import launch_and_goto_fixture, register_smoke_tab, stop_smoke_browser

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]


@pytest.mark.asyncio
async def test_radio_selection_uses_label_and_verifies_state() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    from pydoll_mcp_server.tools.elements import element_click
    from pydoll_mcp_server.tools.form_choice import form_select_choice
    from pydoll_mcp_server.tools.page_summary import page_get_interactive_summary

    browser, tab = await launch_and_goto_fixture('choice-controls.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_ALLOW_NO_AUTH': 'true'}):
            info = await register_smoke_tab(browser, tab, 'choice-smoke')

        summary = await page_get_interactive_summary('choice-smoke', info.tab_id)
        radios = [
            require_json_object(item, 'radio')
            for item in get_array(summary, 'items', [])
            if require_json_object(item, 'summary item').get('role') == 'radio'
        ]
        assert len({get_string(item, 'selector_hint') for item in radios}) == 3
        option = next(item for item in radios if get_string(item, 'name') == '5 or more')
        clicked = await element_click('choice-smoke', info.tab_id, get_string(option, 'element_id'))
        assert clicked['success'] is True
        assert clicked['verified'] is True
        assert clicked['strategy_used'] == 'associated_label'

        selected = await form_select_choice(
            'choice-smoke',
            info.tab_id,
            'PowerBI solutions',
            '5 or more',
        )
        assert selected['success'] is True
        assert selected['checked'] is True
        assert selected['verified'] is True
    finally:
        await stop_smoke_browser(browser)
