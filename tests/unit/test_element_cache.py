"""Tests for element cache."""

from __future__ import annotations

from pydoll_mcp_server.dom.element_cache import ElementCache, ElementCacheEntry


class TestElementCache:
    def setup_method(self) -> None:
        self.cache = ElementCache(max_entries=10, max_age_seconds=3600)

    def test_store_and_get(self) -> None:
        entry = ElementCacheEntry(
            element_id='el_001',
            tab_id='tab_001',
            document_generation=1,
        )
        self.cache.store(entry)
        retrieved = self.cache.get('el_001')
        assert retrieved is not None
        assert retrieved.element_id == 'el_001'

    def test_get_nonexistent(self) -> None:
        assert self.cache.get('nonexistent') is None

    def test_get_valid_same_document(self) -> None:
        entry = ElementCacheEntry(
            element_id='el_001',
            tab_id='tab_001',
            document_generation=2,
        )
        self.cache.store(entry)
        valid = self.cache.get_valid('el_001', 'tab_001', 2)
        assert valid is not None

    def test_get_valid_different_document_returns_none(self) -> None:
        entry = ElementCacheEntry(
            element_id='el_001',
            tab_id='tab_001',
            document_generation=2,
        )
        self.cache.store(entry)
        valid = self.cache.get_valid('el_001', 'tab_001', 3)
        assert valid is None

    def test_get_valid_different_tab_returns_none(self) -> None:
        entry = ElementCacheEntry(
            element_id='el_001',
            tab_id='tab_001',
            document_generation=1,
        )
        self.cache.store(entry)
        valid = self.cache.get_valid('el_001', 'tab_002', 1)
        assert valid is None

    def test_invalidate_tab(self) -> None:
        entry1 = ElementCacheEntry(
            element_id='el_001',
            tab_id='tab_001',
            document_generation=1,
        )
        entry2 = ElementCacheEntry(
            element_id='el_002',
            tab_id='tab_002',
            document_generation=1,
        )
        self.cache.store(entry1)
        self.cache.store(entry2)
        self.cache.invalidate_tab('tab_001')
        assert self.cache.get('el_001') is None
        assert self.cache.get('el_002') is not None

    def test_max_entries_eviction(self) -> None:
        cache = ElementCache(max_entries=3)
        for i in range(5):
            cache.store(
                ElementCacheEntry(
                    element_id=f'el_{i}',
                    tab_id='tab_001',
                    document_generation=1,
                )
            )
        assert cache.size == 3

    def test_clear(self) -> None:
        for i in range(5):
            self.cache.store(
                ElementCacheEntry(
                    element_id=f'el_{i}',
                    tab_id='tab_001',
                    document_generation=1,
                )
            )
        self.cache.clear()
        assert self.cache.size == 0

    def test_invalidate_document(self) -> None:
        entry1 = ElementCacheEntry(
            element_id='el_001',
            tab_id='tab_001',
            document_generation=1,
        )
        entry2 = ElementCacheEntry(
            element_id='el_002',
            tab_id='tab_001',
            document_generation=2,
        )
        self.cache.store(entry1)
        self.cache.store(entry2)
        self.cache.invalidate_document('tab_001', 2)
        assert self.cache.get('el_001') is None
        assert self.cache.get('el_002') is not None

    def test_entry_metadata(self) -> None:
        entry = ElementCacheEntry(
            element_id='el_001',
            tab_id='tab_001',
            document_generation=1,
            frame_path=['frame_1'],
            shadow_path=['open'],
            selector_hint='#my-id',
            xpath_hint='//button[@id="my-id"]',
            text_summary='Click Me',
            tag_name='button',
            bounding_box={'x': 10, 'y': 20, 'width': 100, 'height': 30},
        )
        self.cache.store(entry)
        retrieved = self.cache.get('el_001')
        assert retrieved is not None
        assert retrieved.frame_path == ['frame_1']
        assert retrieved.shadow_path == ['open']
        assert retrieved.selector_hint == '#my-id'
        assert retrieved.tag_name == 'button'
        assert retrieved.bounding_box == {'x': 10, 'y': 20, 'width': 100, 'height': 30}
