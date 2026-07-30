"""Element resolution and low-level interaction helpers."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from pydoll.browser.tab import Tab
from pydoll.elements.shadow_root import ShadowRoot
from pydoll.elements.web_element import WebElement
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.models import TabInfo
from pydoll_mcp_server.browser.pydoll_compat import get_element_attribute, get_element_text, is_element_visible
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_script_object,
    extract_script_value,
)
from pydoll_mcp_server.dom.element_cache import (
    ElementCache,
    ElementCacheEntry,
    cache_observed_element,
    get_element_cache,
)
from pydoll_mcp_server.dom.reference_scripts import reference_metadata_script
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    InvalidJsonValueError,
    JsonArray,
    JsonObject,
    fold_visible_text,
    require_json_object,
)

QueryScope = Tab | WebElement | ShadowRoot


@dataclass(frozen=True)
class ElementResolution:
    """Result of resolving a cached reference immediately before an action."""

    element: WebElement | None
    strategy: str
    candidate_count: int
    fingerprint_match: bool
    candidates: JsonArray
    error: StructuredError | None = None

    @property
    def details(self) -> JsonObject:
        return {
            'strategy': self.strategy,
            'candidate_count': self.candidate_count,
            'fingerprint_match': self.fingerprint_match,
            'resolved_again': self.strategy != 'cached_element',
            'candidates': list(self.candidates),
        }


async def resolve_element(tab_info: TabInfo, element_id: str) -> WebElement | None:
    cache = get_element_cache()
    entry = cache.get_valid(element_id, tab_info.tab_id, tab_info.document_generation)
    if entry is None:
        entry = cache.get_for_tab(element_id, tab_info.tab_id)
    if entry is None:
        return None

    # Legacy cache entries have no browser-side reference metadata. Keep their
    # fast path, but always re-query observed references because frameworks can
    # replace a node without changing the document generation.
    if (
        entry.pydoll_element is not None
        and entry.document_generation == tab_info.document_generation
        and not (entry.selector_hint or entry.xpath_hint or entry.fingerprint)
    ):
        return entry.pydoll_element

    pydoll_tab = tab_info.pydoll_tab
    scoped = await resolve_deep_scope(pydoll_tab, entry)
    if scoped is not None:
        entry.pydoll_element = scoped
        cache.store(entry)
        return scoped

    hints_to_try: list[str] = []
    if entry.selector_hint:
        hints_to_try.append(entry.selector_hint)
    if entry.xpath_hint:
        hints_to_try.append(entry.xpath_hint)

    for hint in hints_to_try:
        element = await pydoll_tab.query(
            hint,
            timeout=5,
            find_all=False,
            raise_exc=False,
        )
        if element is not None:
            entry.pydoll_element = element
            cache.store(entry)
            return element

    return None


async def resolve_element_for_action(tab_info: TabInfo, element_id: str) -> ElementResolution:
    """Resolve a reference with ambiguity checks for an imminent mutation."""

    cache = get_element_cache()
    entry = cache.get_for_tab(element_id, tab_info.tab_id)
    if entry is None:
        return ElementResolution(
            element=None,
            strategy='missing_reference',
            candidate_count=0,
            fingerprint_match=False,
            candidates=[],
            error=StructuredError(
                ErrorCode.STALE_ELEMENT,
                f'Element {element_id} is stale or not found',
                retryable=False,
                recovery_hint='Re-observe the page and use the new element_id.',
            ),
        )

    if not entry.selector_hint and not entry.xpath_hint and entry.pydoll_element is not None:
        return ElementResolution(entry.pydoll_element, 'cached_element', 1, False, [])

    candidates: list[WebElement] = []
    strategy = 'selector_hint'
    scope = await _resolve_scope(tab_info.pydoll_tab, entry)
    if scope is None:
        scope = tab_info.pydoll_tab
    for hint in (entry.selector_hint, entry.xpath_hint):
        if not hint:
            continue
        raw = await scope.query(hint, timeout=5, find_all=True, raise_exc=False)
        if isinstance(raw, list):
            candidates = raw
        elif raw is not None:
            candidates = [raw]
        if candidates:
            strategy = 'selector_hint' if hint == entry.selector_hint else 'xpath_hint'
            break

    if not candidates:
        return ElementResolution(
            element=None,
            strategy='not_found',
            candidate_count=0,
            fingerprint_match=False,
            candidates=[],
            error=StructuredError(
                ErrorCode.STALE_ELEMENT,
                f'Element {element_id} is stale or not found',
                retryable=False,
                recovery_hint='Re-find the element using element_find or page_snapshot.',
            ),
        )

    described: list[tuple[WebElement, int, bool, JsonObject]] = []
    for index, candidate in enumerate(candidates):
        score, fingerprint_match, detail = await _score_candidate(entry, candidate, index)
        described.append((candidate, score, fingerprint_match, detail))

    described.sort(key=lambda item: item[1], reverse=True)
    if entry.match_index >= 0 and entry.match_index < len(described) and len(described) > 1:
        indexed = next((item for item in described if item[3].get('source_index') == entry.match_index), None)
        if indexed is not None and indexed[2]:
            return ElementResolution(indexed[0], 'fingerprint_match', len(described), True, _candidate_json(described))

    best = described[0]
    if len(described) > 1:
        runner_up = described[1]
        if best[1] <= runner_up[1] + 10:
            return ElementResolution(
                element=None,
                strategy='ambiguous',
                candidate_count=len(described),
                fingerprint_match=best[2],
                candidates=_candidate_json(described),
                error=StructuredError(
                    ErrorCode.AMBIGUOUS_ELEMENT,
                    f'Element {element_id} resolved to multiple candidates.',
                    details={
                        'element_id': element_id,
                        'candidates': _candidate_json(described),
                        'selector_hint': entry.selector_hint,
                        'xpath_hint': entry.xpath_hint,
                    },
                    retryable=True,
                    recovery_hint='Use element_resolve_again with a narrower selector or match_index.',
                ),
            )

    return ElementResolution(
        element=best[0],
        strategy='fingerprint_match' if best[2] else strategy,
        candidate_count=len(described),
        fingerprint_match=best[2],
        candidates=_candidate_json(described),
    )


async def resolve_deep_scope(tab: Tab, entry: ElementCacheEntry) -> WebElement | None:
    if not entry.frame_path and not entry.shadow_path:
        return None
    scope: QueryScope = tab
    for frame_selector in entry.frame_path:
        frame = await scope.query(frame_selector, timeout=2, find_all=False, raise_exc=False)
        if frame is None:
            return None
        scope = frame
    for shadow_selector in entry.shadow_path:
        host = await scope.query(shadow_selector, timeout=2, find_all=False, raise_exc=False)
        if host is None:
            return None
        scope = await host.get_shadow_root()
    for hint in (entry.selector_hint, entry.xpath_hint):
        if not hint:
            continue
        element = await scope.query(hint, timeout=2, find_all=False, raise_exc=False)
        if element is not None:
            return element
    return None


async def _resolve_scope(tab: Tab, entry: ElementCacheEntry) -> QueryScope | None:
    if not entry.frame_path and not entry.shadow_path:
        return tab
    scope: QueryScope = tab
    for frame_selector in entry.frame_path:
        frame = await scope.query(frame_selector, timeout=2, find_all=False, raise_exc=False)
        if frame is None:
            return None
        scope = frame
    for shadow_selector in entry.shadow_path:
        host = await scope.query(shadow_selector, timeout=2, find_all=False, raise_exc=False)
        if host is None:
            return None
        scope = await host.get_shadow_root()
    return scope


async def _score_candidate(
    entry: ElementCacheEntry,
    candidate: WebElement,
    source_index: int,
) -> tuple[int, bool, JsonObject]:
    tag = str(candidate.tag_name or '').lower()
    role = _attribute(candidate, 'role')
    name = _attribute(candidate, 'aria-label') or _attribute(candidate, 'name')
    label = name
    try:
        text = (await get_element_text(candidate)).strip().replace('\n', ' ')[:160]
    except (PydollException, TypeError, ValueError):
        text = ''
    score = 0
    fingerprint_match = False
    if entry.tag_name and tag == entry.tag_name.lower():
        score += 30
    if entry.role and role == entry.role:
        score += 25
    if entry.label_summary and fold_visible_text(entry.label_summary) in fold_visible_text(label):
        score += 35
    if entry.text_summary:
        expected = fold_visible_text(entry.text_summary)
        actual = fold_visible_text(text)
        if actual == expected:
            score += 45
            fingerprint_match = True
        elif expected and expected in actual:
            score += 20
    if entry.fingerprint:
        try:
            fingerprint = require_json_object(json.loads(entry.fingerprint), 'element fingerprint')
        except (InvalidJsonValueError, json.JSONDecodeError):
            fingerprint = {}
        if str(fingerprint.get('tag', '')).lower() == tag:
            score += 10
        if str(fingerprint.get('role', '')) == role:
            score += 10
        fingerprint_label = str(fingerprint.get('label', ''))
        if fingerprint_label and fold_visible_text(fingerprint_label) == fold_visible_text(label) and label:
            score += 20
            fingerprint_match = True
    detail: JsonObject = {
        'source_index': source_index,
        'tag': tag,
        'role': role,
        'label': label,
        'text': text,
        'score': score,
        'fingerprint_match': fingerprint_match,
    }
    return score, fingerprint_match, detail


def _candidate_json(described: list[tuple[WebElement, int, bool, JsonObject]]) -> JsonArray:
    return [item[3] for item in described]


def _attribute(element: WebElement, name: str) -> str:
    value = element.get_attribute(name)
    return str(value or '')


def cache_element(cache: ElementCache, tab_info: TabInfo, element: WebElement) -> str:
    element_id = f'el_{uuid.uuid4().hex[:12]}'
    text_summary = ''
    tag = ''
    tag = element.tag_name or ''
    attrs = {name: get_element_attribute(element, name) for name in ('id', 'data-testid', 'name')}
    selector_hint = ''
    xpath_hint = ''
    if attrs.get('id'):
        selector_hint = f'#{attrs["id"]}'
        xpath_hint = f'//*[@id="{attrs["id"]}"]'
    elif attrs.get('data-testid'):
        selector_hint = f'[data-testid="{attrs["data-testid"]}"]'
        xpath_hint = f'//*[@data-testid="{attrs["data-testid"]}"]'
    elif attrs.get('name') and tag:
        selector_hint = f'{tag}[name="{attrs["name"]}"]'
        xpath_hint = f'//{tag}[@name="{attrs["name"]}"]'
    entry = ElementCacheEntry(
        element_id=element_id,
        tab_id=tab_info.tab_id,
        document_generation=tab_info.document_generation,
        tag_name=tag,
        text_summary=text_summary,
        selector_hint=selector_hint,
        xpath_hint=xpath_hint,
        pydoll_element=element,
    )
    cache.store(entry)
    return element_id


async def cache_element_with_reference(
    cache: ElementCache,
    tab_info: TabInfo,
    element: WebElement,
    *,
    fallback_selector: str = '',
    match_index: int = 0,
) -> str:
    """Cache an element with a browser-generated positional reference."""

    try:
        observation = extract_script_object(
            await element.execute_script(reference_metadata_script(), return_by_value=True)
        )
        if not observation.get('selector_hint') and fallback_selector:
            observation['selector_hint'] = fallback_selector
        if not observation.get('xpath_hint'):
            observation['match_index'] = match_index
        return cache_observed_element(
            cache,
            tab_info.tab_id,
            tab_info.document_generation,
            observation,
            pydoll_element=element,
        )
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        return cache_element(cache, tab_info, element)


async def safe_text(element: WebElement) -> str:
    return await get_element_text(element)


async def safe_is_visible(element: WebElement) -> bool:
    return await is_element_visible(element)


async def set_element_value_via_js(element: WebElement, value: str) -> None:
    value_literal = json.dumps(value)
    script = f"""
    const nextValue = {value_literal};
    if (this.tagName === 'INPUT' || this.tagName === 'TEXTAREA') {{
        this.value = nextValue;
        this.dispatchEvent(new Event('input', {{ bubbles: true }}));
        this.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return this.value;
    }}
    if (this.isContentEditable) {{
        this.textContent = nextValue;
        this.dispatchEvent(new Event('input', {{ bubbles: true }}));
        return this.textContent;
    }}
    return null;
    """
    result = await element.execute_script(script, return_by_value=True)
    actual = extract_script_value(result)
    if actual != value:
        raise ValueError('Element value could not be set through JavaScript fallback')


async def read_element_value_via_js(element: WebElement) -> str | None:
    result = await element.execute_script(
        """
        if (this.tagName === 'INPUT' || this.tagName === 'TEXTAREA') return this.value;
        if (this.isContentEditable) return this.textContent;
        return null;
        """,
        return_by_value=True,
    )
    actual = extract_script_value(result)
    return actual if isinstance(actual, str) else None
