"""Element cache for reusing element references across calls."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from pydoll.elements.web_element import WebElement

from pydoll_mcp_server.json_types import JsonObject, get_array, get_int, get_object, get_string


@dataclass
class ElementCacheEntry:
    element_id: str
    tab_id: str
    document_generation: int
    frame_path: list[str] = field(default_factory=lambda: [])
    shadow_path: list[str] = field(default_factory=lambda: [])
    selector_hint: str = ''
    xpath_hint: str = ''
    text_summary: str = ''
    bounding_box: dict[str, float] = field(default_factory=lambda: {})
    tag_name: str = ''
    role: str = ''
    label_summary: str = ''
    fingerprint: str = ''
    match_index: int = 0
    cached_at: float = 0.0
    pydoll_element: WebElement | None = field(default=None, repr=False)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.cached_at


class ElementCache:
    def __init__(self, max_entries: int = 1000, max_age_seconds: float = 3600.0) -> None:
        self._entries: dict[str, ElementCacheEntry] = {}
        self._max_entries = max_entries
        self._max_age = max_age_seconds

    def store(self, entry: ElementCacheEntry) -> None:
        if len(self._entries) >= self._max_entries:
            oldest = min(
                self._entries.values(),
                key=lambda e: e.cached_at,
            )
            del self._entries[oldest.element_id]
        entry.cached_at = time.time()
        self._entries[entry.element_id] = entry

    def get(self, element_id: str) -> ElementCacheEntry | None:
        entry = self._entries.get(element_id)
        if entry is None:
            return None
        if entry.age_seconds > self._max_age:
            del self._entries[element_id]
            return None
        return entry

    def get_valid(
        self,
        element_id: str,
        tab_id: str,
        document_generation: int,
    ) -> ElementCacheEntry | None:
        entry = self.get(element_id)
        if entry is None:
            return None
        if entry.tab_id != tab_id:
            return None
        if entry.document_generation != document_generation:
            return None
        return entry

    def get_for_tab(self, element_id: str, tab_id: str) -> ElementCacheEntry | None:
        entry = self.get(element_id)
        if entry is None or entry.tab_id != tab_id:
            return None
        return entry

    def invalidate_tab(self, tab_id: str) -> None:
        to_remove = [eid for eid, e in self._entries.items() if e.tab_id == tab_id]
        for eid in to_remove:
            del self._entries[eid]

    def invalidate_document(self, tab_id: str, generation: int) -> None:
        to_remove = [
            eid for eid, e in self._entries.items() if e.tab_id == tab_id and e.document_generation != generation
        ]
        for eid in to_remove:
            del self._entries[eid]

    def clear(self) -> None:
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)


_cache: ElementCache | None = None


def get_element_cache() -> ElementCache:
    global _cache
    if _cache is None:
        _cache = ElementCache()
    return _cache


def cache_observed_element(
    cache: ElementCache,
    tab_id: str,
    document_generation: int,
    observation: JsonObject,
    *,
    pydoll_element: WebElement | None = None,
    frame_path: list[str] | None = None,
    shadow_path: list[str] | None = None,
) -> str:
    """Store one observation while keeping all reference metadata in one shape."""

    element_id = get_string(observation, 'element_id', '') or f'el_{uuid.uuid4().hex[:12]}'
    fingerprint_value = observation.get('fingerprint', {})
    fingerprint = json.dumps(fingerprint_value, ensure_ascii=False, sort_keys=True)
    bounds = get_object(observation, 'bounds', get_object(observation, 'bounding_box', {}))
    bounding_box = {
        key: float(value)
        for key, value in bounds.items()
        if key in {'x', 'y', 'width', 'height'} and isinstance(value, int | float) and not isinstance(value, bool)
    }
    entry = ElementCacheEntry(
        element_id=element_id,
        tab_id=tab_id,
        document_generation=document_generation,
        frame_path=list(frame_path or _string_list(get_array(observation, 'frame_path', []))),
        shadow_path=list(shadow_path or _string_list(get_array(observation, 'shadow_path', []))),
        selector_hint=get_string(observation, 'selector_hint', ''),
        xpath_hint=get_string(observation, 'xpath_hint', ''),
        text_summary=get_string(observation, 'text', get_string(observation, 'label', ''))[:160],
        bounding_box=bounding_box,
        tag_name=get_string(observation, 'tag', ''),
        role=get_string(observation, 'role', ''),
        label_summary=get_string(observation, 'label', get_string(observation, 'name', ''))[:160],
        fingerprint=fingerprint,
        match_index=get_int(observation, 'match_index', 0),
        pydoll_element=pydoll_element,
    )
    cache.store(entry)
    return element_id


def _string_list(value: Sequence[object]) -> list[str]:
    return [item for item in value if isinstance(item, str)]
