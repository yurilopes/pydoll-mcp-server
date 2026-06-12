"""Integration tests for element resolution from tree IDs."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = [pytest.mark.integration]


class TestElementResolution:
    def test_resolver_tries_selector_hint(self) -> None:
        from pydoll_mcp_server.dom.element_cache import (
            ElementCacheEntry,
            get_element_cache,
        )

        cache = get_element_cache()
        cache.clear()

        mock_tab = MagicMock()
        mock_tab.query = AsyncMock(return_value=MagicMock())
        tab_info = MagicMock()
        tab_info.tab_id = 'tab_test'
        tab_info.document_generation = 1
        tab_info._pydoll_tab = mock_tab

        entry = ElementCacheEntry(
            element_id='el_test_resolver',
            tab_id='tab_test',
            document_generation=1,
            tag_name='button',
            selector_hint='#btn-click',
        )
        cache.store(entry)

        from pydoll_mcp_server.tools.elements import _resolve_element

        async def run_test():
            return await _resolve_element(tab_info, 'el_test_resolver')

        result = asyncio.run(run_test())
        assert result is not None
        mock_tab.query.assert_called_once_with(
            '#btn-click', timeout=5, find_all=False, raise_exc=False,
        )

    def test_resolver_returns_cached_pydoll_element(self) -> None:
        from pydoll_mcp_server.dom.element_cache import (
            ElementCacheEntry,
            get_element_cache,
        )

        cache = get_element_cache()
        cache.clear()

        mock_element = MagicMock()
        tab_info = MagicMock()
        tab_info.tab_id = 'tab_test'
        tab_info.document_generation = 1

        entry = ElementCacheEntry(
            element_id='el_cached',
            tab_id='tab_test',
            document_generation=1,
            tag_name='button',
            _pydoll_element=mock_element,
        )
        cache.store(entry)

        from pydoll_mcp_server.tools.elements import _resolve_element

        async def run_test():
            return await _resolve_element(tab_info, 'el_cached')

        result = asyncio.run(run_test())
        assert result is mock_element

    def test_resolver_returns_none_for_invalid_entry(self) -> None:
        tab_info = MagicMock()
        tab_info.tab_id = 'tab_test'
        tab_info.document_generation = 1
        tab_info._pydoll_tab = MagicMock()

        from pydoll_mcp_server.tools.elements import _resolve_element

        async def run_test():
            return await _resolve_element(tab_info, 'nonexistent')

        result = asyncio.run(run_test())
        assert result is None

    def test_build_selector_hint_uses_id(self) -> None:
        from pydoll_mcp_server.dom.tree import _build_selector_hint
        node = {'tag': 'button', 'attrs': {'id': 'btn-submit'}}
        assert _build_selector_hint(node) == '#btn-submit'

    def test_build_selector_hint_uses_data_testid(self) -> None:
        from pydoll_mcp_server.dom.tree import _build_selector_hint
        node = {'tag': 'div', 'attrs': {'data-testid': 'result'}}
        assert _build_selector_hint(node) == '[data-testid="result"]'

    def test_build_selector_hint_uses_name(self) -> None:
        from pydoll_mcp_server.dom.tree import _build_selector_hint
        node = {'tag': 'input', 'attrs': {'name': 'username'}}
        assert _build_selector_hint(node) == 'input[name="username"]'

    def test_build_selector_hint_uses_class(self) -> None:
        from pydoll_mcp_server.dom.tree import _build_selector_hint
        node = {'tag': 'div', 'attrs': {'class': 'container main'}}
        assert _build_selector_hint(node) == 'div.container'

    def test_build_selector_hint_uses_text(self) -> None:
        from pydoll_mcp_server.dom.tree import _build_selector_hint
        node = {'tag': 'button', 'attrs': {}, 'text': 'Click Me'}
        assert _build_selector_hint(node) == 'button'

    def test_build_xpath_hint_uses_id(self) -> None:
        from pydoll_mcp_server.dom.tree import _build_xpath_hint
        node = {'tag': 'button', 'attrs': {'id': 'btn-submit'}}
        assert _build_xpath_hint(node) == '//*[@id="btn-submit"]'

    def test_build_xpath_hint_uses_text(self) -> None:
        from pydoll_mcp_server.dom.tree import _build_xpath_hint
        node = {'tag': 'button', 'attrs': {}, 'text': 'Click Me'}
        assert 'Click' in _build_xpath_hint(node)

    def test_cache_entry_stores_hints(self) -> None:
        from pydoll_mcp_server.dom.element_cache import ElementCacheEntry
        entry = ElementCacheEntry(
            element_id='el_1',
            tab_id='tab_1',
            document_generation=1,
            selector_hint='#my-id',
            xpath_hint='//button[@id="my-id"]',
            text_summary='Test button',
            tag_name='button',
            bounding_box={'x': 0, 'y': 0, 'width': 100, 'height': 30},
        )
        assert entry.selector_hint == '#my-id'
        assert entry.xpath_hint == '//button[@id="my-id"]'
        assert entry.tag_name == 'button'
