"""Deep DOM traversal through same-origin iframes and open shadow roots."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from pydoll_mcp_server.browser.pydoll_compat import get_element_attribute, get_element_text
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_script_value
from pydoll_mcp_server.config import get_limits_config, get_timeout_config
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError

DEEP_TREE_JS = """
(() => {
    const maxDepth = __MAX_DEPTH__;
    const maxNodes = __MAX_NODES__;
    const includeShadow = __INCLUDE_SHADOW__;
    const includeIframes = __INCLUDE_IFRAMES__;
    const prefix = 'el_deep_' + Math.random().toString(36).slice(2, 8) + '_';
    let counter = 0;
    const result = {
        elements: [],
        frames: [],
        shadow_roots: [],
        errors: [],
        partial: false
    };

    function cssEscape(value) {
        if (window.CSS && CSS.escape) return CSS.escape(value);
        return String(value).replace(/([ !"#$%&'()*+,./:;<=>?@[\\\\\\]^`{|}~])/g, '\\\\$1');
    }

    function attrEscape(value) {
        return String(value).replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
    }

    function textOf(el) {
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return el.value || '';
        return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    }

    function attrsOf(el) {
        const allowed = [
            'id', 'class', 'name', 'type', 'placeholder', 'href', 'src',
            'alt', 'title', 'value', 'role', 'aria-label', 'data-testid'
        ];
        const attrs = {};
        for (const attr of el.attributes || []) {
            const name = attr.name.toLowerCase();
            if (!allowed.includes(name)) continue;
            let value = attr.value || '';
            if (name === 'value' && el.tagName === 'INPUT' && el.type === 'password') {
                value = '***';
            }
            attrs[name] = value.slice(0, 500);
        }
        return attrs;
    }

    function selectorHint(el) {
        const tag = (el.tagName || '').toLowerCase();
        if (!tag) return '';
        if (el.id) return '#' + cssEscape(el.id);
        const testId = el.getAttribute('data-testid');
        if (testId) return '[data-testid="' + attrEscape(testId) + '"]';
        const name = el.getAttribute('name');
        if (name) return tag + '[name="' + attrEscape(name) + '"]';
        const aria = el.getAttribute('aria-label');
        if (aria) return tag + '[aria-label="' + attrEscape(aria) + '"]';
        const type = el.getAttribute('type');
        if (type) return tag + '[type="' + attrEscape(type) + '"]';
        return tag;
    }

    function xpathHint(el) {
        if (el.id) return '//*[@id="' + el.id.replace(/"/g, '&quot;') + '"]';
        const tag = (el.tagName || '').toLowerCase();
        const name = el.getAttribute('name');
        if (tag && name) return '//' + tag + '[@name="' + name.replace(/"/g, '&quot;') + '"]';
        return '';
    }

    function boundsOf(el) {
        try {
            const rect = el.getBoundingClientRect();
            return {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            };
        } catch (e) {
            return null;
        }
    }

    function visibleOf(el, bounds) {
        try {
            const style = el.ownerDocument.defaultView.getComputedStyle(el);
            return !!bounds && bounds.width > 0 && bounds.height > 0
                && style.display !== 'none'
                && style.visibility !== 'hidden';
        } catch (e) {
            return false;
        }
    }

    function clickableOf(el) {
        const tag = (el.tagName || '').toLowerCase();
        return ['button', 'a', 'input', 'select', 'textarea', 'option'].includes(tag)
            || !!el.getAttribute('role')
            || typeof el.onclick === 'function';
    }

    function pushElement(el, framePath, shadowPath) {
        if (result.elements.length >= maxNodes) {
            result.partial = true;
            return null;
        }
        const tag = (el.tagName || '').toLowerCase();
        const bounds = boundsOf(el);
        const info = {
            elementId: prefix + counter++,
            tag,
            text: textOf(el).slice(0, 200),
            attrs: attrsOf(el),
            selector_hint: selectorHint(el),
            xpath_hint: xpathHint(el),
            bounding_box: bounds,
            visible: visibleOf(el, bounds),
            enabled: !el.disabled,
            clickable: clickableOf(el),
            frame_path: framePath.slice(),
            shadow_path: shadowPath.slice()
        };
        result.elements.push(info);
        return info;
    }

    function walkRoot(root, framePath, shadowPath, depth, pathLabel) {
        if (depth > maxDepth) {
            result.partial = true;
            return;
        }
        let nodes = [];
        try {
            nodes = Array.from(root.querySelectorAll('*'));
        } catch (e) {
            result.errors.push({path: pathLabel, error: String(e && e.message ? e.message : e)});
            result.partial = true;
            return;
        }

        for (const el of nodes) {
            if (result.elements.length >= maxNodes) {
                result.partial = true;
                return;
            }
            const info = pushElement(el, framePath, shadowPath);
            if (!info) return;

            if (includeIframes && ['iframe', 'frame'].includes(info.tag)) {
                const frameRef = info.selector_hint || info.elementId;
                const nextFramePath = framePath.concat([frameRef]);
                result.frames.push({
                    element_id: info.elementId,
                    selector_hint: info.selector_hint,
                    frame_path: framePath.slice(),
                    target_frame_path: nextFramePath.slice(),
                    src: el.getAttribute('src') || ''
                });
                try {
                    if (el.contentDocument) {
                        walkRoot(
                            el.contentDocument,
                            nextFramePath,
                            shadowPath,
                            depth + 1,
                            nextFramePath.join(' > ')
                        );
                    }
                } catch (e) {
                    result.errors.push({
                        path: nextFramePath.join(' > '),
                        error: String(e && e.message ? e.message : e)
                    });
                    result.partial = true;
                }
            }

            if (includeShadow && el.shadowRoot) {
                const shadowRef = info.selector_hint || info.elementId;
                const nextShadowPath = shadowPath.concat([shadowRef]);
                result.shadow_roots.push({
                    host_element_id: info.elementId,
                    mode: el.shadowRoot.mode || 'open',
                    frame_path: framePath.slice(),
                    shadow_path: shadowPath.slice(),
                    target_shadow_path: nextShadowPath.slice()
                });
                walkRoot(
                    el.shadowRoot,
                    framePath,
                    nextShadowPath,
                    depth + 1,
                    nextShadowPath.join(' > ')
                );
            }
        }
    }

    walkRoot(document, [], [], 0, 'root');
    return result;
})()
"""


DEEP_FIND_JS = """
(() => {
    const selector = __SELECTOR__;
    const strategy = __STRATEGY__;
    const maxDepth = __MAX_DEPTH__;
    const maxNodes = __MAX_NODES__;
    const includeShadow = __INCLUDE_SHADOW__;
    const includeIframes = __INCLUDE_IFRAMES__;
    const prefix = 'el_deep_' + Math.random().toString(36).slice(2, 8) + '_';
    let counter = 0;
    const result = {elements: [], errors: [], partial: false};

    function cssEscape(value) {
        if (window.CSS && CSS.escape) return CSS.escape(value);
        return String(value).replace(/([ !"#$%&'()*+,./:;<=>?@[\\\\\\]^`{|}~])/g, '\\\\$1');
    }

    function attrEscape(value) {
        return String(value).replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
    }

    function selectorHint(el) {
        const tag = (el.tagName || '').toLowerCase();
        if (!tag) return '';
        if (el.id) return '#' + cssEscape(el.id);
        const testId = el.getAttribute('data-testid');
        if (testId) return '[data-testid="' + attrEscape(testId) + '"]';
        const name = el.getAttribute('name');
        if (name) return tag + '[name="' + attrEscape(name) + '"]';
        const aria = el.getAttribute('aria-label');
        if (aria) return tag + '[aria-label="' + attrEscape(aria) + '"]';
        const type = el.getAttribute('type');
        if (type) return tag + '[type="' + attrEscape(type) + '"]';
        return tag;
    }

    function attrsOf(el) {
        const attrs = {};
        for (const attr of el.attributes || []) {
            const name = attr.name.toLowerCase();
            if (['id', 'class', 'name', 'type', 'placeholder', 'role', 'aria-label', 'data-testid'].includes(name)) {
                attrs[name] = (attr.value || '').slice(0, 500);
            }
        }
        return attrs;
    }

    function textOf(el) {
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return el.value || '';
        return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    }

    function pushMatch(el, framePath, shadowPath) {
        if (result.elements.length >= maxNodes) {
            result.partial = true;
            return;
        }
        result.elements.push({
            elementId: prefix + counter++,
            tag: (el.tagName || '').toLowerCase(),
            text: textOf(el).slice(0, 200),
            attrs: attrsOf(el),
            selector_hint: selectorHint(el),
            xpath_hint: el.id ? '//*[@id="' + el.id.replace(/"/g, '&quot;') + '"]' : '',
            frame_path: framePath.slice(),
            shadow_path: shadowPath.slice()
        });
    }

    function queryMatches(root, framePath, shadowPath, pathLabel) {
        try {
            if (strategy === 'css') {
                for (const el of Array.from(root.querySelectorAll(selector))) {
                    pushMatch(el, framePath, shadowPath);
                }
            } else if (strategy === 'xpath') {
                const doc = root.ownerDocument || root;
                const snapshot = doc.evaluate(
                    selector,
                    root,
                    null,
                    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                    null
                );
                for (let i = 0; i < snapshot.snapshotLength; i++) {
                    pushMatch(snapshot.snapshotItem(i), framePath, shadowPath);
                }
            }
        } catch (e) {
            result.errors.push({path: pathLabel, error: String(e && e.message ? e.message : e)});
            result.partial = true;
        }
    }

    function walkRoot(root, framePath, shadowPath, depth, pathLabel) {
        if (depth > maxDepth || result.elements.length >= maxNodes) {
            result.partial = result.elements.length >= maxNodes;
            return;
        }
        queryMatches(root, framePath, shadowPath, pathLabel);

        let nodes = [];
        try {
            nodes = Array.from(root.querySelectorAll('*'));
        } catch (e) {
            result.errors.push({path: pathLabel, error: String(e && e.message ? e.message : e)});
            result.partial = true;
            return;
        }

        for (const el of nodes) {
            if (includeIframes && ['iframe', 'frame'].includes((el.tagName || '').toLowerCase())) {
                const frameRef = selectorHint(el) || ((el.tagName || 'iframe').toLowerCase());
                const nextFramePath = framePath.concat([frameRef]);
                try {
                    if (el.contentDocument) {
                        walkRoot(el.contentDocument, nextFramePath, shadowPath, depth + 1, nextFramePath.join(' > '));
                    }
                } catch (e) {
                    result.errors.push({
                        path: nextFramePath.join(' > '),
                        error: String(e && e.message ? e.message : e)
                    });
                    result.partial = true;
                }
            }
            if (includeShadow && el.shadowRoot) {
                const shadowRef = selectorHint(el) || ((el.tagName || 'shadow-host').toLowerCase());
                const nextShadowPath = shadowPath.concat([shadowRef]);
                walkRoot(el.shadowRoot, framePath, nextShadowPath, depth + 1, nextShadowPath.join(' > '));
            }
        }
    }

    walkRoot(document, [], [], 0, 'root');
    return result;
})()
"""


async def page_get_tree_deep(
    client_id: str,
    tab_id: str,
    max_depth: int = 10,
    max_nodes: int = 1000,
    timeout: float | None = None,
    include_shadow: bool = True,
    include_iframes: bool = True,
) -> dict[str, Any]:
    config = get_timeout_config()
    timeout = timeout or config.deep_tree
    timeout = min(timeout, config.max_timeout)
    limits = get_limits_config()
    max_depth = min(max_depth, limits.max_deep_depth)
    max_nodes = min(max_nodes, limits.max_deep_nodes)
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info._pydoll_tab
    start = time.time()
    errors: list[dict[str, Any]] = []
    partial = False

    try:
        script = (
            DEEP_TREE_JS
            .replace('__MAX_DEPTH__', str(max_depth))
            .replace('__MAX_NODES__', str(max_nodes))
            .replace('__INCLUDE_SHADOW__', 'true' if include_shadow else 'false')
            .replace('__INCLUDE_IFRAMES__', 'true' if include_iframes else 'false')
        )
        response = await asyncio.wait_for(
            pydoll_tab.execute_script(script, return_by_value=True),
            timeout=timeout,
        )
        raw = extract_script_value(response) or {}
    except asyncio.TimeoutError:
        raw = {}
        partial = True
        errors.append({
            'path': 'root',
            'error': f'Deep traversal timed out after {timeout}s',
        })
    except Exception as exc:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Deep traversal failed: {exc}',
            retryable=True,
        ).to_dict()

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}

    raw_elements = raw.get('elements', []) if isinstance(raw, dict) else []
    raw_frames = raw.get('frames', []) if isinstance(raw, dict) else []
    try:
        await _collect_iframe_scope(
            scope=pydoll_tab,
            tab_info=tab_info,
            frame_path=[],
            depth=0,
            max_depth=max_depth,
            remaining=max_nodes - len(raw_elements),
            raw_elements=raw_elements,
            frames=raw_frames,
            errors=errors,
        )
    except Exception as exc:
        partial = True
        errors.append({'path': 'iframes', 'error': str(exc)})

    elements = _cache_deep_nodes(tab_info, raw_elements)
    raw_errors = raw.get('errors', []) if isinstance(raw, dict) else []
    if isinstance(raw_errors, list):
        errors.extend(raw_errors)
    partial = partial or bool(raw.get('partial')) if isinstance(raw, dict) else partial
    duration_ms = (time.time() - start) * 1000

    return {
        'success': True,
        'frames': raw_frames,
        'shadow_roots': raw.get('shadow_roots', []) if isinstance(raw, dict) else [],
        'elements': elements,
        'partial': partial,
        'errors': errors,
        'timing_ms': round(duration_ms, 1),
    }


async def element_find_deep(
    client_id: str,
    tab_id: str,
    selector: str,
    strategy: str = 'css',
    timeout: float | None = None,
) -> dict[str, Any]:
    if strategy not in ('css', 'xpath'):
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message=f'Unknown strategy: {strategy}. Use css or xpath.',
            retryable=False,
        ).to_dict()

    config = get_timeout_config()
    timeout = timeout or config.deep_tree
    timeout = min(timeout, config.max_timeout)
    limits = get_limits_config()
    max_depth = limits.max_deep_depth
    max_nodes = limits.max_deep_nodes
    registry = get_registry()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info._pydoll_tab

    iframe_matches: list[dict[str, Any]] = []
    try:
        await _find_in_iframe_scopes(
            scope=pydoll_tab,
            selector=selector,
            strategy=strategy,
            tab_info=tab_info,
            frame_path=[],
            depth=0,
            max_depth=max_depth,
            remaining=max_nodes,
            matches=iframe_matches,
        )
    except Exception:
        iframe_matches = []

    try:
        script = (
            DEEP_FIND_JS
            .replace('__SELECTOR__', json.dumps(selector))
            .replace('__STRATEGY__', json.dumps(strategy))
            .replace('__MAX_DEPTH__', str(max_depth))
            .replace('__MAX_NODES__', str(max_nodes))
            .replace('__INCLUDE_SHADOW__', 'true')
            .replace('__INCLUDE_IFRAMES__', 'true')
        )
        response = await asyncio.wait_for(
            pydoll_tab.execute_script(script, return_by_value=True),
            timeout=timeout,
        )
        raw = extract_script_value(response) or {}
    except asyncio.TimeoutError:
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message=f'Deep find timed out after {timeout}s',
            retryable=True,
        ).to_dict()
    except Exception as exc:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Deep find failed: {exc}',
            retryable=True,
        ).to_dict()

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}

    raw_elements = iframe_matches + (raw.get('elements', []) if isinstance(raw, dict) else [])
    matches = _cache_deep_nodes(tab_info, raw_elements)
    if not matches:
        return StructuredError(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message=f'No element found for selector: {selector} (deep search)',
            retryable=False,
        ).to_dict()

    return {
        'success': True,
        'selector': selector,
        'strategy': strategy,
        'found': len(matches),
        'elements': matches,
        'partial': bool(raw.get('partial')) if isinstance(raw, dict) else False,
        'errors': raw.get('errors', []) if isinstance(raw, dict) else [],
    }


async def _collect_iframe_scope(
    scope: Any,
    tab_info: Any,
    frame_path: list[str],
    depth: int,
    max_depth: int,
    remaining: int,
    raw_elements: list[Any],
    frames: list[Any],
    errors: list[dict[str, Any]],
) -> None:
    if depth >= max_depth or remaining <= 0:
        return

    frame_elements = await _query_frame_elements(scope)
    for frame_el in frame_elements:
        if remaining <= 0:
            return
        frame_raw = await _raw_from_pydoll_element(frame_el, frame_path, [])
        raw_elements.append(frame_raw)
        remaining -= 1
        frame_ref = frame_raw.get('selector_hint') or frame_raw.get('elementId')
        next_frame_path = frame_path + [str(frame_ref)]
        frames.append({
            'element_id': frame_raw.get('elementId'),
            'selector_hint': frame_raw.get('selector_hint', ''),
            'frame_path': list(frame_path),
            'target_frame_path': list(next_frame_path),
            'src': frame_raw.get('attrs', {}).get('src', ''),
        })

        try:
            child_elements = await frame_el.query(
                '*', timeout=0, find_all=True, raise_exc=False,
            )
            for child in _ensure_list(child_elements):
                if remaining <= 0:
                    return
                raw_elements.append(
                    await _raw_from_pydoll_element(child, next_frame_path, [])
                )
                remaining -= 1
            await _collect_iframe_scope(
                scope=frame_el,
                tab_info=tab_info,
                frame_path=next_frame_path,
                depth=depth + 1,
                max_depth=max_depth,
                remaining=remaining,
                raw_elements=raw_elements,
                frames=frames,
                errors=errors,
            )
        except Exception as exc:
            errors.append({
                'path': ' > '.join(next_frame_path),
                'error': str(exc),
            })


async def _find_in_iframe_scopes(
    scope: Any,
    selector: str,
    strategy: str,
    tab_info: Any,
    frame_path: list[str],
    depth: int,
    max_depth: int,
    remaining: int,
    matches: list[dict[str, Any]],
) -> None:
    if depth >= max_depth or remaining <= 0:
        return

    frame_elements = await _query_frame_elements(scope)
    for frame_el in frame_elements:
        frame_raw = await _raw_from_pydoll_element(frame_el, frame_path, [])
        frame_ref = frame_raw.get('selector_hint') or frame_raw.get('elementId')
        next_frame_path = frame_path + [str(frame_ref)]
        try:
            found = await frame_el.query(
                selector,
                timeout=0 if strategy == 'css' else 1,
                find_all=True,
                raise_exc=False,
            )
            for element in _ensure_list(found):
                if len(matches) >= remaining:
                    return
                matches.append(
                    await _raw_from_pydoll_element(element, next_frame_path, [])
                )
            await _find_in_iframe_scopes(
                scope=frame_el,
                selector=selector,
                strategy=strategy,
                tab_info=tab_info,
                frame_path=next_frame_path,
                depth=depth + 1,
                max_depth=max_depth,
                remaining=remaining,
                matches=matches,
            )
        except Exception:
            continue


async def _query_frame_elements(scope: Any) -> list[Any]:
    elements: list[Any] = []
    for selector in ('iframe', 'frame'):
        try:
            result = await scope.query(
                selector, timeout=0, find_all=True, raise_exc=False,
            )
            elements.extend(_ensure_list(result))
        except Exception:
            continue
    return elements


async def _raw_from_pydoll_element(
    element: Any,
    frame_path: list[str],
    shadow_path: list[str],
) -> dict[str, Any]:
    tag = _safe_tag_name(element)
    attrs = _element_attrs(element)
    selector = _selector_from_attrs(tag, attrs)
    text = await get_element_text(element)
    return {
        'elementId': f'el_deep_{uuid.uuid4().hex[:12]}',
        'tag': tag,
        'text': text[:200],
        'attrs': attrs,
        'selector_hint': selector,
        'xpath_hint': _xpath_from_attrs(tag, attrs),
        'bounding_box': {},
        'visible': True,
        'enabled': attrs.get('disabled') is None,
        'clickable': tag in {'button', 'a', 'input', 'select', 'textarea', 'option'},
        'frame_path': list(frame_path),
        'shadow_path': list(shadow_path),
        '_pydoll_element': element,
    }


def _safe_tag_name(element: Any) -> str:
    try:
        tag = element.tag_name if hasattr(element, 'tag_name') else ''
        return str(tag or '').lower()
    except Exception:
        return ''


def _element_attrs(element: Any) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for name in (
        'id', 'class', 'name', 'type', 'placeholder', 'href', 'src',
        'alt', 'title', 'value', 'role', 'aria-label', 'data-testid',
    ):
        value = get_element_attribute(element, name)
        if value is not None:
            attrs[name] = value[:500]
    return attrs


def _selector_from_attrs(tag: str, attrs: dict[str, str]) -> str:
    if attrs.get('id'):
        return f'#{attrs["id"]}'
    if attrs.get('data-testid'):
        return f'[data-testid="{attrs["data-testid"]}"]'
    if attrs.get('name') and tag:
        return f'{tag}[name="{attrs["name"]}"]'
    if attrs.get('type') and tag:
        return f'{tag}[type="{attrs["type"]}"]'
    return tag


def _xpath_from_attrs(tag: str, attrs: dict[str, str]) -> str:
    if attrs.get('id'):
        return f'//*[@id="{attrs["id"]}"]'
    if attrs.get('name') and tag:
        return f'//{tag}[@name="{attrs["name"]}"]'
    return ''


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _cache_deep_nodes(tab_info: Any, raw_elements: list[Any]) -> list[dict[str, Any]]:
    cache = get_element_cache()
    elements: list[dict[str, Any]] = []
    for raw in raw_elements:
        if not isinstance(raw, dict):
            continue
        element_id = str(raw.get('elementId') or '')
        if not element_id:
            continue
        frame_path = _list_of_strings(raw.get('frame_path'))
        shadow_path = _list_of_strings(raw.get('shadow_path'))
        entry = ElementCacheEntry(
            element_id=element_id,
            tab_id=tab_info.tab_id,
            document_generation=tab_info.document_generation,
            frame_path=frame_path,
            shadow_path=shadow_path,
            selector_hint=str(raw.get('selector_hint') or ''),
            xpath_hint=str(raw.get('xpath_hint') or ''),
            text_summary=str(raw.get('text') or '')[:100],
            bounding_box=raw.get('bounding_box') or {},
            tag_name=str(raw.get('tag') or ''),
            _pydoll_element=raw.get('_pydoll_element'),
        )
        cache.store(entry)
        elements.append({
            'element_id': element_id,
            'tag': entry.tag_name,
            'text': entry.text_summary,
            'attrs': raw.get('attrs') or {},
            'selector_hint': entry.selector_hint,
            'xpath_hint': entry.xpath_hint,
            'frame_path': frame_path,
            'shadow_path': shadow_path,
            'bounding_box': entry.bounding_box,
            'visible': bool(raw.get('visible', False)),
            'enabled': bool(raw.get('enabled', True)),
            'clickable': bool(raw.get('clickable', False)),
        })
    return elements


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
