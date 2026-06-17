"""Unit tests for PLAN_14 enhanced tool contracts (params verification)."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


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
        assert 'ambiguity_threshold' in params
        assert 'prefer_modal' in params
