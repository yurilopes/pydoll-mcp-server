"""Focused tests for modern frontend agent tools."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest import MonkeyPatch

from pydoll_mcp_server.json_types import JsonObject

pytestmark = [pytest.mark.unit]


class _FakeJsTab:
    def __init__(self, response: JsonObject) -> None:
        self.response = response

    async def execute_script(self, script: str, return_by_value: bool = True) -> JsonObject:
        return self.response


class _FakeRegistry:
    def __init__(self, tab: _FakeJsTab) -> None:
        self.tab = tab

    def get_tab(self, client_id: str, tab_id: str) -> SimpleNamespace:
        return SimpleNamespace(pydoll_tab=self.tab)


@pytest.mark.asyncio
async def test_js_evaluate_returns_structured_json(monkeypatch: MonkeyPatch) -> None:
    from pydoll_mcp_server.tools import javascript

    tab = _FakeJsTab({'result': {'result': {'type': 'object', 'value': {'answer': 42, 'items': [1, 2]}}}})
    monkeypatch.setattr(javascript, 'get_registry', lambda: _FakeRegistry(tab))

    result = await javascript.js_evaluate_readonly('client', 'tab', 'return {answer: 42, items: [1, 2]};')

    assert result['success'] is True
    assert result['value'] == {'answer': 42, 'items': [1, 2]}
    assert result['value_type'] == 'object'
    assert isinstance(result['result_size_bytes'], int)
    assert isinstance(result['script_hash'], str)


@pytest.mark.asyncio
async def test_artifact_import_requires_allowlist(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    from pydoll_mcp_server.config import get_config
    from pydoll_mcp_server.tools.files import artifact_import

    runtime = tmp_path / 'runtime'
    outside = tmp_path / 'outside'
    outside.mkdir()
    source = outside / 'resume.txt'
    source.write_text('resume', encoding='utf-8')
    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    monkeypatch.setenv('PYDOLL_MCP_RUNTIME_DIR', str(runtime))
    get_config.cache_clear()

    denied = await artifact_import('client', str(source))
    assert denied['error_code'] == 'PERMISSION_DENIED'

    monkeypatch.setenv('PYDOLL_MCP_IMPORT_ALLOWLIST', str(outside))
    get_config.cache_clear()
    imported = await artifact_import('client', str(source))
    assert imported['success'] is True
    assert Path(str(imported['path'])).exists()


def test_tool_catalog_contains_frontend_robustness_tools() -> None:
    from pydoll_mcp_server.tool_catalog import TOOLS

    names = {tool.__name__ for tool in TOOLS}
    assert {
        'page_get_interactive_summary',
        'element_click_by_text',
        'element_click_center',
        'mouse_click',
        'element_fill_and_verify',
        'element_wait_value',
        'form_snapshot',
        'form_errors',
        'combobox_get_options',
        'combobox_type_and_select',
        'combobox_select_option',
        'page_wait_for_text',
        'page_wait_text_gone',
        'page_wait_for_selector',
        'page_wait_for_network_idle',
        'file_upload_state',
        'artifact_get_paths',
        'artifact_import',
    } <= names
