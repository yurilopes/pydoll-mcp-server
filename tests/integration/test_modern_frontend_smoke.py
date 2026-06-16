"""Real-browser smoke tests for modern frontend agent tools."""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch

import pytest

from pydoll_mcp_server.json_types import get_array, require_json_object
from tests.integration.test_browser_smoke import launch_and_goto_fixture, register_smoke_tab, stop_smoke_browser
from tests.typing_helpers import array_at, string_at

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]


@pytest.mark.asyncio
async def test_agent_modern_frontend_workflow_without_custom_js() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    from pydoll_mcp_server.config import get_config
    from pydoll_mcp_server.dom.tree import build_page_tree
    from pydoll_mcp_server.tools.element_advanced import element_find_by_label
    from pydoll_mcp_server.tools.elements import element_fill
    from pydoll_mcp_server.tools.files import upload_files
    from pydoll_mcp_server.tools.form_controls import combobox_type_and_select, form_errors
    from pydoll_mcp_server.tools.page_summary import page_get_interactive_summary
    from pydoll_mcp_server.tools.semantic_actions import element_click_by_text
    from pydoll_mcp_server.tools.waits import page_wait_for_text

    browser, tab = await launch_and_goto_fixture('modern-controls.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_ALLOW_NO_AUTH': 'true'}):
            info = await register_smoke_tab(browser, tab, 'modern-smoke')

        tree = await build_page_tree('modern-smoke', info.tab_id)
        tags = {str(require_json_object(node, 'tree node').get('tag')) for node in get_array(tree, 'nodes', [])}
        assert 'head' not in tags
        assert 'script' not in tags

        summary = await page_get_interactive_summary('modern-smoke', info.tab_id)
        assert summary['success'] is True
        assert any(
            require_json_object(item, 'summary item').get('name') == 'Freelance' for item in array_at(summary, 'items')
        )

        save_empty = await element_click_by_text('modern-smoke', info.tab_id, 'Save', exact=True)
        assert save_empty['success'] is True
        assert (await page_wait_for_text('modern-smoke', info.tab_id, 'This field is required'))['success'] is True
        errors = await form_errors('modern-smoke', info.tab_id)
        assert errors['success'] is True
        assert errors['count'] == 1

        title = await element_find_by_label('modern-smoke', info.tab_id, 'Professional title')
        title_id = string_at(title, 'element_id')
        filled = await element_fill('modern-smoke', info.tab_id, title_id, 'Senior Python developer')
        assert filled['success'] is True
        assert (await page_wait_for_text('modern-smoke', info.tab_id, 'Title state: Senior Python developer'))[
            'success'
        ] is True

        combo = await element_find_by_label('modern-smoke', info.tab_id, 'Primary skill')
        selected = await combobox_type_and_select(
            'modern-smoke',
            info.tab_id,
            string_at(combo, 'element_id'),
            'Artificial',
            'Artificial Intelligence',
            exact=True,
        )
        assert selected['success'] is True
        assert (await page_wait_for_text('modern-smoke', info.tab_id, 'Selected skill: Artificial Intelligence'))[
            'success'
        ] is True

        mode = await element_click_by_text('modern-smoke', info.tab_id, 'Freelance', exact=True)
        assert mode['success'] is True
        assert (await page_wait_for_text('modern-smoke', info.tab_id, 'Selected mode: Freelance'))['success'] is True

        artifact = get_config().artifacts_dir / 'modern-smoke' / 'resume.txt'
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text('resume', encoding='utf-8')
        file_input = await element_find_by_label('modern-smoke', info.tab_id, 'Resume')
        upload = await upload_files('modern-smoke', info.tab_id, string_at(file_input, 'element_id'), [str(artifact)])
        assert upload['success'] is True
        assert (await page_wait_for_text('modern-smoke', info.tab_id, 'Attached file: resume.txt'))['success'] is True

        saved = await element_click_by_text('modern-smoke', info.tab_id, 'Save', exact=True)
        assert saved['success'] is True
        assert (await page_wait_for_text('modern-smoke', info.tab_id, 'You have updated your profile'))[
            'success'
        ] is True
    finally:
        await stop_smoke_browser(browser)
