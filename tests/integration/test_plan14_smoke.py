"""Browser smoke test for PLAN_14 multi-step form flow without js_evaluate."""

from __future__ import annotations

import atexit
import os
import tempfile
import threading
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.browser_smoke, pytest.mark.browser, pytest.mark.slow]

FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures' / 'pages'


class _QuietFixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@lru_cache
def _fixture_server() -> ThreadingHTTPServer:
    handler = partial(_QuietFixtureHandler, directory=str(FIXTURES_DIR))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    atexit.register(server.shutdown)
    return server


def build_fixture_url(filename: str) -> str:
    server = _fixture_server()
    return f'http://127.0.0.1:{server.server_port}/{filename}'


@pytest.mark.asyncio
async def test_multi_step_form_flow_without_js_evaluate() -> None:
    runtime_dir = Path(tempfile.gettempdir()) / 'pydoll-mcp-smoke-plan14'
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.environ['PYDOLL_MCP_RUNTIME_DIR'] = str(runtime_dir)
    with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
        from pydoll_mcp_server.config import get_config

        get_config.cache_clear()
        from pydoll_mcp_server.tools.active_surface import page_get_active_surface
        from pydoll_mcp_server.tools.browser import browser_close, browser_launch
        from pydoll_mcp_server.tools.elements import element_click, element_find
        from pydoll_mcp_server.tools.files import upload_files
        from pydoll_mcp_server.tools.form_fill import form_fill_fields
        from pydoll_mcp_server.tools.page import page_goto
        from pydoll_mcp_server.tools.primary_action import page_click_primary_action
        from pydoll_mcp_server.tools.submission import submission_wait_for_confirmation
        from pydoll_mcp_server.tools.upload_prep import artifact_prepare_upload

        client_id = 'smoke-plan14'
        fixture_url = build_fixture_url('multi-step-application.html')

        launch_result = await browser_launch(client_id=client_id, headless=True, profile_mode='temporary')
        assert launch_result.get('success') is True
        tab_id: str = str(launch_result.get('tab_id', ''))

        try:
            goto_result = await page_goto(client_id, tab_id, fixture_url)
            assert goto_result.get('success') is True

            apply_find = await element_find(
                client_id=client_id,
                tab_id=tab_id,
                selector='#main-apply',
            )
            assert apply_find.get('success') is True
            apply_id = str(apply_find.get('element_id', ''))
            click_result = await element_click(
                client_id=client_id,
                tab_id=tab_id,
                element_id=apply_id,
            )
            assert click_result.get('success') is True

            surface = await page_get_active_surface(
                client_id=client_id,
                tab_id=tab_id,
                scope='modal',
            )
            assert surface.get('success') is True

            contact_fields: list[dict[str, object]] = [
                {'label_contains': 'Full Name', 'value': 'John Doe'},
                {'label_contains': 'Email', 'value': 'john@example.com'},
                {'label_contains': 'Phone', 'value': '+1 555-0000'},
            ]
            fill_result = await form_fill_fields(
                client_id=client_id,
                tab_id=tab_id,
                fields=contact_fields,
                scope='modal',
                validate=True,
            )
            assert fill_result.get('success') is True

            step_result = await page_click_primary_action(
                client_id=client_id,
                tab_id=tab_id,
                scope='modal',
                expected_progress_change=True,
            )
            assert step_result.get('success') is True

            tmp_dir = Path(str(runtime_dir)) / 'tmp' / client_id
            tmp_dir.mkdir(parents=True, exist_ok=True)
            source_pdf = tmp_dir / 'test.pdf'
            source_pdf.write_bytes(b'%PDF-1.4\n%fake pdf content\n')

            prep_result = await artifact_prepare_upload(
                client_id=client_id,
                source_path=str(source_pdf),
            )
            assert prep_result.get('success') is True
            prepared_path: str = str(prep_result.get('path', ''))

            file_find = await element_find(
                client_id=client_id,
                tab_id=tab_id,
                selector='#field-resume',
                strategy='css',
            )
            if file_find.get('success') is True:
                file_input_id = str(file_find.get('element_id', ''))
                upload_result = await upload_files(
                    client_id=client_id,
                    tab_id=tab_id,
                    element_id=file_input_id,
                    paths=[prepared_path],
                    expect_filename_visible=True,
                )
                assert upload_result.get('success') is True

            step2_result = await page_click_primary_action(
                client_id=client_id,
                tab_id=tab_id,
                scope='modal',
                expected_progress_change=True,
            )
            assert step2_result.get('success') is True

            questions_result = await form_fill_fields(
                client_id=client_id,
                tab_id=tab_id,
                fields=[
                    {'label_contains': 'Years of Experience', 'value': '5'},
                    {'label_contains': 'Preferred Role', 'value': 'individual'},
                ],
                scope='modal',
                validate=True,
            )
            assert questions_result.get('success') is True

            adv2_result = await page_click_primary_action(
                client_id=client_id,
                tab_id=tab_id,
                scope='modal',
                expected_progress_change=True,
            )
            assert adv2_result.get('success') is True

            submit_result = await page_click_primary_action(
                client_id=client_id,
                tab_id=tab_id,
                scope='modal',
            )
            assert submit_result.get('success') is True

            confirm_result = await submission_wait_for_confirmation(
                client_id=client_id,
                tab_id=tab_id,
                success_text_any=['submitted', 'received', 'Application Submitted'],
                timeout=10.0,
            )
            assert confirm_result.get('success') is True

        finally:
            close_result = await browser_close(client_id=client_id, browser_id='')
            assert close_result.get('success') is True or 'not found' in str(close_result.get('message', '')).lower()
