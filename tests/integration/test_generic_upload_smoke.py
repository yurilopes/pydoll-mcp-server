"""Real-browser smoke tests for generic upload trigger automation."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.integration.test_browser_smoke import (
    build_fixture_url,
    launch_and_goto_fixture,
    register_smoke_tab,
    stop_smoke_browser,
)

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]


@pytest.mark.asyncio
async def test_generic_upload_trigger_uses_hidden_input_without_native_dialog() -> None:
    if importlib.util.find_spec('pydoll.browser') is None:
        pytest.skip('Pydoll not available')

    from pydoll_mcp_server.tools.element_advanced import element_find_by_text
    from pydoll_mcp_server.tools.files import artifact_get_paths
    from pydoll_mcp_server.tools.upload_trigger import upload_files_from_trigger
    from pydoll_mcp_server.tools.waits import page_wait_for_text

    browser, tab = await launch_and_goto_fixture('generic-file-upload.html')
    try:
        with patch.dict(os.environ, {'PYDOLL_MCP_ALLOW_NO_AUTH': 'true'}):
            info = await register_smoke_tab(browser, tab, 'generic-upload-smoke')
        paths = await artifact_get_paths('generic-upload-smoke')
        artifact_dir = Path(str(paths['client_artifacts_dir']))
        artifact_dir.mkdir(parents=True, exist_ok=True)
        resume = artifact_dir / 'resume.pdf'
        resume.write_bytes(b'%PDF-1.4\n%generic upload fixture\n')

        trigger = await element_find_by_text(
            'generic-upload-smoke',
            info.tab_id,
            'Upload resume with input',
            exact=True,
        )
        assert trigger['success'] is True

        result = await upload_files_from_trigger(
            client_id='generic-upload-smoke',
            tab_id=info.tab_id,
            trigger_element_id=str(trigger['element_id']),
            paths=[str(resume)],
            expected_filenames=['resume.pdf'],
        )

        assert result['success'] is True
        assert result['uploaded'] is True
        assert result['strategy_used'] == 'direct_input'
        assert result['native_dialog_used'] is False
        assert (await page_wait_for_text('generic-upload-smoke', info.tab_id, 'Resume uploaded'))['success'] is True
    finally:
        await stop_smoke_browser(browser)


@pytest.mark.native_ui
@pytest.mark.asyncio
async def test_generic_upload_trigger_controls_windows_native_picker() -> None:
    if sys.platform != 'win32':
        pytest.skip('Windows native picker test requires Windows')
    if os.environ.get('PYDOLL_MCP_NATIVE_UI_TESTS') != '1':
        pytest.skip('Set PYDOLL_MCP_NATIVE_UI_TESTS=1 in an interactive desktop session')
    if importlib.util.find_spec('pywinauto') is None:
        pytest.skip('Install pydoll-mcp-server[windows] to run native picker tests')

    from pydoll_mcp_server.browser.registry import get_registry
    from pydoll_mcp_server.browser.script_utils import extract_script_object
    from pydoll_mcp_server.config import get_config
    from pydoll_mcp_server.json_types import get_bool
    from pydoll_mcp_server.tools.browser import browser_close, browser_launch
    from pydoll_mcp_server.tools.element_advanced import element_find_by_text
    from pydoll_mcp_server.tools.page import page_goto
    from pydoll_mcp_server.tools.upload_trigger import upload_files_from_trigger

    client_id = 'generic-native-upload-smoke'
    downloads_dir = Path.home() / 'Downloads'
    if not downloads_dir.is_dir():
        pytest.skip('The interactive Downloads directory is unavailable')
    file_descriptor, file_name = tempfile.mkstemp(
        prefix='pydoll-mcp-native-ui-',
        suffix='.pdf',
        dir=downloads_dir,
    )
    os.close(file_descriptor)
    resume = downloads_dir / file_name
    resume.write_bytes(b'%PDF-1.4\n%native picker fixture\n')
    upload_environment = patch.dict(
        os.environ,
        {
            'PYDOLL_MCP_ALLOW_NO_AUTH': 'true',
            'PYDOLL_MCP_UPLOAD_ALLOWLIST': str(downloads_dir),
        },
    )
    upload_environment.start()
    try:
        get_config.cache_clear()
        launch = await browser_launch(client_id=client_id, headless=False, profile_mode='temporary')
        assert launch['success'] is True
        tab_id = str(launch['tab_id'])
        browser_id = str(launch['browser_id'])
        try:
            goto = await page_goto(client_id, tab_id, build_fixture_url('generic-file-upload.html'))
            assert goto['success'] is True
            tab_info = get_registry().get_tab(client_id, tab_id)
            api_probe = await tab_info.pydoll_tab.execute_script(
                "return {available: typeof window.showOpenFilePicker === 'function'};",
                return_by_value=True,
            )
            if not get_bool(extract_script_object(api_probe), 'available'):
                pytest.skip('Chrome does not expose the File System Access API in this session')

            trigger = await element_find_by_text(client_id, tab_id, 'Upload resume with native picker', exact=True)
            assert trigger['success'] is True
            result = await upload_files_from_trigger(
                client_id=client_id,
                tab_id=tab_id,
                trigger_element_id=str(trigger['element_id']),
                paths=[str(resume)],
                picker_strategy='desktop',
                expected_filenames=[resume.name],
                timeout_ms=30000,
            )

            assert result.get('success') is True, result
            assert result['strategy_used'] == 'desktop_picker'
            assert result['native_dialog_used'] is True
        finally:
            close = await browser_close(client_id=client_id, browser_id=browser_id)
            assert close['success'] is True or 'not found' in str(close.get('message', '')).lower()
    finally:
        upload_environment.stop()
        get_config.cache_clear()
        resume.unlink(missing_ok=True)
