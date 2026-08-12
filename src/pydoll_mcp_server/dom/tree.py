"""DOM tree building and serialization."""

from __future__ import annotations

import uuid

from pydoll_mcp_server.browser.artifact_registry import artifact_context, register_artifact, valid_evidence_kind
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import extract_normalized_object, extract_normalized_string
from pydoll_mcp_server.config import get_config, get_limits_config
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.dom.models import RawTreeNode, json_from_tree_node, parse_tree_result
from pydoll_mcp_server.dom.reference_scripts import ELEMENT_REFERENCE_HELPERS
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject
from pydoll_mcp_server.security.paths import validate_artifact_path

TREE_BUILDER_JS = """
(() => {
    const includeInvisible = %INCLUDE_INVISIBLE%;
    const includeHead = %INCLUDE_HEAD%;
    const blockedHeadTags = new Set(['head', 'script', 'style', 'meta', 'link', 'noscript', 'template']);
    %REFERENCE_HELPERS%
    function isVisibleElement(node, tag) {
        if (tag === 'html' || tag === 'body') return true;
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return rect.width > 0 && rect.height > 0
            && style.display !== 'none'
            && style.visibility !== 'hidden';
    }
    function collect(node, depth, maxDepth, maxNodes, collected) {
        if (depth > maxDepth || collected.count >= maxNodes) return;
        const tag = node.tagName ? node.tagName.toLowerCase() : '#text';
        if (!includeHead && blockedHeadTags.has(tag)) return;
        const info = {
            tag: tag,
            text: '',
            attrs: {},
            bounds: null,
            children: []
        };
        if (node.nodeType === 3) {
            info.tag = '#text';
            info.text = (node.textContent || '').substring(0, 200);
        } else if (node.nodeType === 1) {
            for (const attr of node.attributes || []) {
                const name = attr.name.toLowerCase();
                if (['id', 'class', 'name', 'type', 'placeholder', 'href', 'src', 'alt', 'title',
                     'role', 'aria-label', 'data-testid'].includes(name)) {
                    const val = attr.value || '';
                    info.attrs[name] = val.substring(0, 500);
                }
            }
            const rect = node.getBoundingClientRect();
            info.bounds = {x: Math.round(rect.x), y: Math.round(rect.y),
                           width: Math.round(rect.width), height: Math.round(rect.height)};
            try {
                info.visible = isVisibleElement(node, info.tag);
            } catch(e) {
                info.visible = false;
            }
            if (!includeInvisible && !info.visible) return;
            if (node.shadowRoot) {
                info.hasShadowRoot = true;
                info.shadowMode = node.shadowRoot.mode || 'open';
            }
            if (['input', 'select', 'textarea', 'button', 'a'].includes(info.tag)) {
                info.interactive = true;
            }
            if (['iframe', 'frame'].includes(info.tag)) {
                info.isFrame = true;
            }
            const reference = elementReference(node);
            info.selector_hint = reference.selector_hint;
            info.xpath_hint = reference.xpath_hint;
            info.match_index = reference.match_index;
            info.role = reference.role;
            info.label = reference.label;
            info.fingerprint = reference.fingerprint;
        }
        collected.count++;
        info.elementId = 'el_' + Math.random().toString(36).substring(2, 14);
        collected.nodes.push(info);
        if (node.shadowRoot && depth < maxDepth && collected.count < maxNodes) {
            for (const child of node.shadowRoot.children || []) {
                const childInfo = collect(child, depth + 1, maxDepth, maxNodes, collected);
                if (childInfo) info.children.push(childInfo.elementId);
            }
        }
        for (const child of node.childNodes) {
            if (collected.count >= maxNodes) break;
            if (child.nodeType !== 1 && child.nodeType !== 3) continue;
            const childInfo = collect(child, depth + 1, maxDepth, maxNodes, collected);
            if (childInfo) info.children.push(childInfo.elementId);
        }
        return info;
    }
    const result = {nodes: [], rootId: null, count: 0};
    const root = includeHead ? document.documentElement : (document.body || document.documentElement);
    if (root) {
        collect(root, 0, %MAX_DEPTH%, %MAX_NODES%, result);
        result.rootId = result.nodes.length > 0 ? result.nodes[0].elementId : null;
    }
    return result;
})()
"""


async def build_page_tree(
    client_id: str,
    tab_id: str,
    max_depth: int = 6,
    max_nodes: int = 300,
    cache_elements: bool = True,
    include_invisible: bool = False,
    include_head: bool = False,
) -> JsonObject:
    registry = get_registry()
    limits = get_limits_config()

    max_depth = min(max_depth, limits.max_tree_depth)
    max_nodes = min(max_nodes, limits.max_tree_nodes)

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab

    try:
        js = (
            TREE_BUILDER_JS.replace('%MAX_DEPTH%', str(max_depth))
            .replace('%MAX_NODES%', str(max_nodes))
            .replace('%INCLUDE_INVISIBLE%', str(include_invisible).lower())
            .replace('%INCLUDE_HEAD%', str(include_head).lower())
            .replace('%REFERENCE_HELPERS%', ELEMENT_REFERENCE_HELPERS)
        )
        result = await pydoll_tab.execute_script(js, return_by_value=True)
        raw_value = extract_normalized_object(result, 'page_get_tree')
        raw = parse_tree_result(raw_value)
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to build page tree: {e}',
            retryable=True,
        ).to_dict()

    raw_nodes = raw['nodes']
    nodes: list[JsonObject] = []
    if cache_elements:
        cache = get_element_cache()
        for node in raw_nodes:
            actionable, confidence = _assess_actionable(node)
            entry = ElementCacheEntry(
                element_id=node['element_id'],
                tab_id=tab_id,
                document_generation=tab_info.document_generation,
                tag_name=node['tag'],
                text_summary=node['text'][:100],
                bounding_box=node['bounds'],
                selector_hint=node.get('selector_hint', _build_selector_hint(node)),
                xpath_hint=node.get('xpath_hint', _build_xpath_hint(node)),
                role=node.get('role', ''),
                label_summary=node.get('label', '')[:160],
                match_index=node.get('match_index', 0),
                fingerprint=_fingerprint_text(node),
            )
            serialized = json_from_tree_node(node)
            serialized['actionable'] = actionable
            serialized['resolution_confidence'] = confidence
            serialized['selector_hint'] = entry.selector_hint
            serialized['xpath_hint'] = entry.xpath_hint
            nodes.append(serialized)
            cache.store(entry)
    else:
        nodes = [json_from_tree_node(node) for node in raw_nodes]

    serialized_nodes: JsonArray = list(nodes)
    return {
        'success': True,
        'root_id': raw['root_id'],
        'nodes': serialized_nodes,
        'count': len(nodes),
        'truncated': raw['count'] >= max_nodes,
    }


def _assess_actionable(node: RawTreeNode) -> tuple[bool, str]:
    tag = node['tag']
    if tag in ('#text', '#document', 'html', 'head', 'body', 'script', 'style', 'meta', 'link'):
        return False, 'none'
    attrs = node['attrs']
    if attrs.get('id') or attrs.get('data-testid'):
        return True, 'high'
    if attrs.get('name'):
        return True, 'high'
    if attrs.get('role') and attrs.get('type'):
        return True, 'medium'
    if (attrs.get('class', '') or '').strip():
        return True, 'medium'
    if tag in ('button', 'a', 'input', 'select', 'textarea'):
        return True, 'low'
    return False, 'none'


def _fingerprint_text(node: RawTreeNode) -> str:
    import json

    fingerprint = node.get('fingerprint', {})
    return json.dumps(fingerprint, ensure_ascii=False, sort_keys=True)


def _build_selector_hint(node: RawTreeNode) -> str:
    tag = node['tag']
    if tag in ('#text', '#document', 'html', 'head', 'body'):
        return ''
    attrs = node['attrs']
    if attrs.get('id'):
        return f'#{attrs["id"]}'
    if attrs.get('data-testid'):
        return f'[data-testid="{attrs["data-testid"]}"]'
    if attrs.get('name') and tag:
        return f'{tag}[name="{attrs["name"]}"]'
    if attrs.get('role') and tag:
        return f'{tag}[role="{attrs["role"]}"]'
    if attrs.get('type') and tag:
        return f'{tag}[type="{attrs["type"]}"]'
    if attrs.get('placeholder') and tag:
        return f'{tag}[placeholder="{attrs["placeholder"]}"]'
    classes = (attrs.get('class', '') or '').strip()
    if classes:
        parts = classes.split()
        if parts:
            return f'{tag}.{parts[0]}'
    if attrs.get('href') and tag == 'a':
        return f'a[href="{attrs["href"]}"]'
    if attrs.get('src') and tag:
        return f'{tag}[src="{attrs["src"]}"]'
    node_text = node['text'].strip()
    if node_text and tag:
        return f'{tag}'
    return tag or ''


def build_selector_hint(node: RawTreeNode) -> str:
    return _build_selector_hint(node)


def _build_xpath_hint(node: RawTreeNode) -> str:
    tag = node['tag']
    if tag in ('#text', '#document', 'html', 'head', 'body'):
        return ''
    attrs = node['attrs']
    if attrs.get('id'):
        return f'//*[@id="{attrs["id"]}"]'
    if attrs.get('data-testid'):
        return f'//*[@data-testid="{attrs["data-testid"]}"]'
    if attrs.get('name'):
        return f'//{tag}[@name="{attrs["name"]}"]'
    if attrs.get('placeholder'):
        return f'//{tag}[@placeholder="{attrs["placeholder"]}"]'
    node_text = node['text'].strip()
    if node_text and tag:
        safe_text = node_text[:50].replace('"', '&quot;')
        return f'//{tag}[contains(text(), "{safe_text}")]'
    return ''


def build_xpath_hint(node: RawTreeNode) -> str:
    return _build_xpath_hint(node)


async def page_get_text(
    client_id: str,
    tab_id: str,
    max_chars: int = 20000,
) -> JsonObject:
    registry = get_registry()
    limits = get_limits_config()
    max_chars = min(max_chars, limits.max_text_chars)

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab

    try:
        result = await pydoll_tab.execute_script(
            'return (document.body ? document.body.innerText : document.documentElement.innerText) || "";',
            return_by_value=True,
        )
        text = extract_normalized_string(result, 'page_get_text')
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Failed to get page text: {e}',
            retryable=True,
        ).to_dict()

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    return {
        'success': True,
        'text': text,
        'length': len(text),
        'truncated': truncated,
    }


async def page_screenshot(
    client_id: str,
    tab_id: str,
    fmt: str = 'png',
    full_page: bool = False,
    as_base64: bool = False,
    path: str = '',
    evidence_kind: str = 'diagnostic',
    return_base64: bool | None = None,
    name: str = '',
) -> JsonObject:
    registry = get_registry()
    config = get_config()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab

    if return_base64 is not None:
        as_base64 = return_base64
    if not valid_evidence_kind(evidence_kind):
        return StructuredError(ErrorCode.INVALID_INPUT, f'Unknown evidence_kind: {evidence_kind}').to_dict()
    if name and not path:
        path = name
    safe_path: str | None = None
    if path:
        safe_path = validate_artifact_path(path, config)
        if safe_path is None:
            return StructuredError(
                error_code=ErrorCode.PERMISSION_DENIED,
                message=f'Screenshot path not allowed: {path}',
                retryable=False,
                recovery_hint='Use a relative path (stored in artifacts dir) or a path in an allowed directory.',
            ).to_dict()

    if not safe_path and not as_base64:
        ext = fmt if fmt in ('png', 'jpeg', 'jpg') else 'png'
        screenshots_dir = config.artifacts_dir / client_id
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        safe_path = str(screenshots_dir / f'screenshot_{uuid.uuid4().hex[:12]}.{ext}')

    try:
        if safe_path:
            await pydoll_tab.take_screenshot(
                path=safe_path,
                beyond_viewport=full_page,
                as_base64=False,
            )
            file_size = 0
            try:
                from pathlib import Path

                file_size = Path(safe_path).stat().st_size
            except OSError:
                pass
            url, viewport = await artifact_context(pydoll_tab)
            mime_type = 'image/jpeg' if fmt in ('jpeg', 'jpg') else 'image/png'
            artifact = register_artifact(client_id, safe_path, mime_type, evidence_kind, url, viewport)
            if not artifact.get('success'):
                return artifact
            return {
                'success': True,
                'path': safe_path,
                'contract_version': 2,
                'operation_id': f'screenshot_{uuid.uuid4().hex[:16]}',
                'status': 'captured',
                'mime_type': mime_type,
                'format': fmt,
                'size': file_size,
                'return_base64': False,
                'data': '',
                'artifact_id': artifact.get('artifact_id', ''),
                'relative_path': artifact.get('relative_path', ''),
                'evidence_kind': evidence_kind,
                'evidence': artifact,
            }
        result = await pydoll_tab.take_screenshot(
            beyond_viewport=full_page,
            as_base64=True,
        )
        return {
            'contract_version': 2,
            'operation_id': f'screenshot_{uuid.uuid4().hex[:16]}',
            'success': True,
            'status': 'captured',
            'data': result if isinstance(result, str) else '',
            'format': fmt,
            'return_base64': True,
            'evidence_kind': evidence_kind,
            'evidence': {},
        }
    except Exception as e:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'Screenshot failed: {e}',
            retryable=True,
        ).to_dict()
