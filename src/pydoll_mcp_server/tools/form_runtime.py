"""Shared runtime state for batched semantic form workflows."""

from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass, field

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.json_types import JsonArray, JsonObject


def _empty_object() -> JsonObject:
    return {}


def _empty_json_array() -> JsonArray:
    return []


def _empty_string_list() -> list[str]:
    return []


@dataclass
class PerformanceSummary:
    """Redacted performance counters exposed by a high-level workflow."""

    started_at: float = field(default_factory=time.monotonic)
    discovery_ms: float = 0.0
    mutation_ms: float = 0.0
    verification_ms: float = 0.0
    wait_ms: float = 0.0
    browser_calls: int = 0
    full_scans: int = 0
    deep_scans: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    fallbacks: int = 0
    round_trips_saved: int = 0

    def browser_call(self, count: int = 1) -> None:
        self.browser_calls += max(0, count)

    def add_phase(self, phase: str, started_at: float) -> None:
        elapsed = max(0.0, (time.monotonic() - started_at) * 1000)
        if phase == 'discovery':
            self.discovery_ms += elapsed
        elif phase == 'mutation':
            self.mutation_ms += elapsed
        elif phase == 'verification':
            self.verification_ms += elapsed
        elif phase == 'wait':
            self.wait_ms += elapsed

    def absorb(self, value: JsonObject) -> None:
        """Accumulate a redacted performance envelope from one internal phase."""

        self.discovery_ms += _number(value.get('discovery_ms'))
        self.mutation_ms += _number(value.get('mutation_ms'))
        self.verification_ms += _number(value.get('verification_ms'))
        self.wait_ms += _number(value.get('wait_ms'))
        self.browser_calls += _integer(value.get('browser_calls'))
        self.full_scans += _integer(value.get('full_scans'))
        self.deep_scans += _integer(value.get('deep_scans'))
        self.cache_hits += _integer(value.get('cache_hits'))
        self.cache_misses += _integer(value.get('cache_misses'))
        self.fallbacks += _integer(value.get('fallbacks'))
        self.round_trips_saved += _integer(value.get('round_trips_saved'))

    def to_json(self) -> JsonObject:
        total_ms = (time.monotonic() - self.started_at) * 1000
        return {
            'total_ms': round(max(0.0, total_ms), 1),
            'discovery_ms': round(max(0.0, self.discovery_ms), 1),
            'mutation_ms': round(max(0.0, self.mutation_ms), 1),
            'verification_ms': round(max(0.0, self.verification_ms), 1),
            'wait_ms': round(max(0.0, self.wait_ms), 1),
            'browser_calls': self.browser_calls,
            'full_scans': self.full_scans,
            'deep_scans': self.deep_scans,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'fallbacks': self.fallbacks,
            'round_trips_saved': self.round_trips_saved,
        }


@dataclass
class FormExecutionContext:
    """State shared by the internal phases of one form operation."""

    client_id: str
    tab_id: str
    scope: str = 'auto'
    preset: str = 'generic_form'
    document_generation: int = 0
    mutation_epoch: int = 0
    surface_snapshot: JsonObject = field(default_factory=_empty_object)
    form_fingerprint: str = ''
    snapshot_id: str = ''
    performance: PerformanceSummary = field(default_factory=PerformanceSummary)
    owned_target_ids: list[str] = field(default_factory=_empty_string_list)
    trace: JsonArray = field(default_factory=_empty_json_array)

    def refresh_version(self) -> None:
        tab_info = get_registry().get_tab(self.client_id, self.tab_id)
        generation = getattr(tab_info, 'document_generation', 0)
        mutation_epoch = getattr(tab_info, 'mutation_epoch', 0)
        self.document_generation = generation if isinstance(generation, int) and not isinstance(generation, bool) else 0
        self.mutation_epoch = (
            mutation_epoch if isinstance(mutation_epoch, int) and not isinstance(mutation_epoch, bool) else 0
        )

    def set_snapshot(self, snapshot: JsonObject, fingerprint: str = '') -> None:
        self.surface_snapshot = copy.deepcopy(snapshot)
        self.form_fingerprint = fingerprint
        self.snapshot_id = f'snapshot_{uuid.uuid4().hex[:16]}'

    def performance_json(self) -> JsonObject:
        return self.performance.to_json()

    def trace_event(self, phase: str, operation: str, status: str) -> None:
        self.trace.append({'phase': phase, 'operation': operation, 'status': status})


@dataclass(frozen=True)
class SurfaceCacheKey:
    client_id: str
    tab_id: str
    connection_identity: int
    document_generation: int
    mutation_epoch: int
    scope: str
    preset: str
    include_values: bool
    include_diagnostics: bool
    diagnostic_mode: str = 'compact'
    include_shadow: bool = True
    max_fields: int = 100
    max_controls: int = 120
    text_max_chars: int = 300


@dataclass
class SurfaceCacheEntry:
    key: SurfaceCacheKey
    snapshot: JsonObject
    fingerprint: str
    created_at: float = field(default_factory=time.time)


_SURFACE_CACHE: dict[SurfaceCacheKey, SurfaceCacheEntry] = {}
_DEEP_CACHE: dict[SurfaceCacheKey, JsonObject] = {}
_PREFLIGHT_CACHE: dict[tuple[SurfaceCacheKey, tuple[str, ...], str], JsonObject] = {}


def get_mutation_epoch(client_id: str, tab_id: str) -> int:
    value = getattr(get_registry().get_tab(client_id, tab_id), 'mutation_epoch', 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _integer(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def advance_mutation_epoch(
    client_id: str,
    tab_id: str,
    reason: str = '',
    tab_info: TabInfo | None = None,
) -> int:
    """Invalidate semantic state after a browser mutation."""

    target = tab_info if tab_info is not None else get_registry().get_tab(client_id, tab_id)
    current = getattr(target, 'mutation_epoch', 0)
    next_epoch = (current if isinstance(current, int) and not isinstance(current, bool) else 0) + 1
    target.mutation_epoch = next_epoch
    clear_surface_cache(client_id, tab_id)
    from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens

    invalidate_review_tokens(client_id, tab_id)
    del reason
    return next_epoch


def mark_document_changed(client_id: str, tab_id: str, tab_info: TabInfo | None = None) -> int:
    """Reset the mutation epoch after a navigation or reload."""

    target = tab_info if tab_info is not None else get_registry().get_tab(client_id, tab_id)
    target.mark_navigated()
    clear_surface_cache(client_id, tab_id)
    from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens

    invalidate_review_tokens(client_id, tab_id)
    generation = getattr(target, 'document_generation', 0)
    return generation if isinstance(generation, int) and not isinstance(generation, bool) else 0


def cache_key(
    client_id: str,
    tab_id: str,
    scope: str,
    preset: str,
    include_values: bool,
    include_diagnostics: bool = True,
    tab_info: object | None = None,
    diagnostic_mode: str = 'compact',
    include_shadow: bool = True,
) -> SurfaceCacheKey:
    resolved_tab = tab_info if tab_info is not None else get_registry().get_tab(client_id, tab_id)
    generation = getattr(resolved_tab, 'document_generation', 0)
    safe_generation = generation if isinstance(generation, int) and not isinstance(generation, bool) else 0
    connection_identity = id(getattr(resolved_tab, 'pydoll_tab', None))
    return SurfaceCacheKey(
        client_id=client_id,
        tab_id=tab_id,
        connection_identity=connection_identity,
        document_generation=safe_generation,
        mutation_epoch=_safe_mutation_epoch(resolved_tab, client_id, tab_id),
        scope=scope,
        preset=preset,
        include_values=include_values,
        include_diagnostics=include_diagnostics,
        diagnostic_mode=diagnostic_mode,
        include_shadow=include_shadow,
    )


def _safe_mutation_epoch(resolved_tab: object, client_id: str, tab_id: str) -> int:
    value = getattr(resolved_tab, 'mutation_epoch', None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return get_mutation_epoch(client_id, tab_id)


def get_cached_surface(key: SurfaceCacheKey) -> SurfaceCacheEntry | None:
    entry = _SURFACE_CACHE.get(key)
    if entry is None:
        return None
    if entry.key != key:
        _SURFACE_CACHE.pop(key, None)
        return None
    return SurfaceCacheEntry(entry.key, copy.deepcopy(entry.snapshot), entry.fingerprint, entry.created_at)


def store_cached_surface(key: SurfaceCacheKey, snapshot: JsonObject, fingerprint: str) -> None:
    _SURFACE_CACHE[key] = SurfaceCacheEntry(key, copy.deepcopy(snapshot), fingerprint)


def get_cached_deep(key: SurfaceCacheKey) -> JsonObject | None:
    value = _DEEP_CACHE.get(key)
    return copy.deepcopy(value) if value is not None else None


def store_cached_deep(key: SurfaceCacheKey, value: JsonObject) -> None:
    _DEEP_CACHE[key] = copy.deepcopy(value)


def get_cached_preflight(
    key: SurfaceCacheKey,
    do_not_touch: list[str],
    employer_domain: str,
) -> JsonObject | None:
    cache_key_value = (key, tuple(do_not_touch), employer_domain)
    value = _PREFLIGHT_CACHE.get(cache_key_value)
    return copy.deepcopy(value) if value is not None else None


def store_cached_preflight(
    key: SurfaceCacheKey,
    do_not_touch: list[str],
    employer_domain: str,
    value: JsonObject,
) -> None:
    _PREFLIGHT_CACHE[(key, tuple(do_not_touch), employer_domain)] = copy.deepcopy(value)


def clear_surface_cache(client_id: str = '', tab_id: str = '') -> None:
    if not client_id and not tab_id:
        _SURFACE_CACHE.clear()
        _DEEP_CACHE.clear()
        _PREFLIGHT_CACHE.clear()
        return
    for key in [key for key in _SURFACE_CACHE if _cache_matches(key, client_id, tab_id)]:
        _SURFACE_CACHE.pop(key, None)
    for key in [key for key in _DEEP_CACHE if _cache_matches(key, client_id, tab_id)]:
        _DEEP_CACHE.pop(key, None)
    for cache_key_value in [key for key in _PREFLIGHT_CACHE if _cache_matches(key[0], client_id, tab_id)]:
        _PREFLIGHT_CACHE.pop(cache_key_value, None)


def _cache_matches(key: SurfaceCacheKey, client_id: str, tab_id: str) -> bool:
    return (not client_id or key.client_id == client_id) and (not tab_id or key.tab_id == tab_id)


def reset_form_runtime() -> None:
    """Clear process-local semantic state during server shutdown or tests."""

    _SURFACE_CACHE.clear()
    _DEEP_CACHE.clear()
    _PREFLIGHT_CACHE.clear()


__all__ = [
    'FormExecutionContext',
    'PerformanceSummary',
    'SurfaceCacheEntry',
    'SurfaceCacheKey',
    'advance_mutation_epoch',
    'cache_key',
    'clear_surface_cache',
    'get_cached_deep',
    'get_cached_preflight',
    'get_cached_surface',
    'get_mutation_epoch',
    'mark_document_changed',
    'reset_form_runtime',
    'store_cached_deep',
    'store_cached_preflight',
    'store_cached_surface',
]
