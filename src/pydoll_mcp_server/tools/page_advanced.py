"""Advanced page observation, scrolling, snapshots, and accessibility."""

from __future__ import annotations

import time

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.pydoll_compat import get_tab_title, get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_script_array,
    extract_script_object,
)
from pydoll_mcp_server.browser.snapshots import get_snapshot_manager
from pydoll_mcp_server.config import get_limits_config
from pydoll_mcp_server.dom.deep_traversal import page_get_tree_deep
from pydoll_mcp_server.dom.tree import build_page_tree, page_get_text
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_string, require_json_object
from pydoll_mcp_server.server_state import SCHEMA_VERSION


async def page_scroll(client_id: str, tab_id: str, delta_x: int = 0, delta_y: int = 500) -> JsonObject:
    return await _scroll(client_id, tab_id, f'window.scrollBy({delta_x},{delta_y})')


async def page_scroll_to(client_id: str, tab_id: str, x: int = 0, y: int = 0) -> JsonObject:
    return await _scroll(client_id, tab_id, f'window.scrollTo({x},{y})')


async def page_snapshot(
    client_id: str,
    tab_id: str,
    max_nodes: int = 100,
    include_accessibility: bool = False,
    include_deep: bool = False,
) -> JsonObject:
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()
    tree = await (
        page_get_tree_deep(client_id, tab_id, max_nodes=max_nodes)
        if include_deep
        else build_page_tree(client_id, tab_id, max_nodes=max_nodes)
    )
    text = await page_get_text(client_id, tab_id, max_chars=5000)
    snapshot: JsonObject = {
        'success': True,
        'schema_version': SCHEMA_VERSION,
        'tab_id': tab_id,
        'url': await get_tab_url(tab_info.pydoll_tab),
        'title': await get_tab_title(tab_info.pydoll_tab),
        'health': tab_info.health.value,
        'text': get_string(text, 'text', ''),
        'nodes': get_array(tree, 'nodes', get_array(tree, 'elements', [])),
        'partial': bool(tree.get('partial', False)),
        'errors': get_array(tree, 'errors', []),
        'created_at': time.time(),
    }
    if include_accessibility:
        accessibility = await page_get_accessibility_tree(client_id, tab_id, max_nodes=max_nodes)
        snapshot['accessibility'] = get_array(accessibility, 'nodes', [])
    get_snapshot_manager().store(client_id, tab_id, snapshot)
    return snapshot


async def page_diff(client_id: str, tab_id: str, previous_snapshot_id: str, max_changes: int = 200) -> JsonObject:
    try:
        old = get_snapshot_manager().get(client_id, tab_id, previous_snapshot_id)
    except StructuredError as exc:
        return exc.to_dict()
    current = await page_snapshot(client_id, tab_id, max_nodes=300)
    old_nodes = _nodes_by_signature(get_array(old, 'nodes', []))
    new_nodes = _nodes_by_signature(get_array(current, 'nodes', []))
    added: JsonArray = []
    for key in list(new_nodes.keys() - old_nodes.keys())[:max_changes]:
        added.append(new_nodes[key])
    removed: JsonArray = []
    for key in list(old_nodes.keys() - new_nodes.keys())[:max_changes]:
        removed.append(old_nodes[key])
    return {
        'success': True,
        'schema_version': SCHEMA_VERSION,
        'previous_snapshot_id': previous_snapshot_id,
        'snapshot_id': get_string(current, 'snapshot_id', ''),
        'url_changed': get_string(old, 'url', '') != get_string(current, 'url', ''),
        'title_changed': get_string(old, 'title', '') != get_string(current, 'title', ''),
        'text_changed': get_string(old, 'text', '') != get_string(current, 'text', ''),
        'added': added,
        'removed': removed,
        'truncated': len(added) + len(removed) >= max_changes,
    }


async def page_get_accessibility_tree(
    client_id: str,
    tab_id: str,
    max_depth: int = 8,
    max_nodes: int = 300,
    interesting_only: bool = True,
) -> JsonObject:
    limits = get_limits_config()
    max_nodes = min(max_nodes, limits.max_deep_nodes)
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
    except StructuredError as exc:
        return exc.to_dict()
    script = f"""(()=>{{const out=[];const role=e=>e.getAttribute('role')||
    ({{BUTTON:'button',A:'link',INPUT:e.type==='checkbox'?'checkbox':'textbox',SELECT:'combobox',
    TEXTAREA:'textbox'}}[e.tagName]||'generic');function walk(e,d){{
    if(!e||d>{max_depth}||out.length>={max_nodes})return;
    const r=role(e),n=e.getAttribute?.('aria-label')||e.alt||e.title||e.innerText?.trim().slice(0,200)||'';
    if(!{str(interesting_only).lower()}||r!=='generic'||n)out.push({{role:r,name:n,
    value:e.type==='password'?'[REDACTED]':(e.value??null),disabled:!!e.disabled,checked:e.checked??null,
    depth:d,actionable:['button','link','textbox','checkbox','combobox'].includes(r)}});
    for(const c of e.children||[])walk(c,d+1);if(e.shadowRoot)for(const c of e.shadowRoot.children)walk(c,d+1);}}
    walk(document.documentElement,0);return out;}})()"""
    try:
        nodes = extract_script_array(await tab.execute_script(script, return_by_value=True))
        return {'success': True, 'nodes': nodes, 'count': len(nodes), 'partial': len(nodes) >= max_nodes}
    except Exception as exc:
        return StructuredError(ErrorCode.UNSUPPORTED, f'Accessibility tree unavailable: {exc}').to_dict()


async def frame_list(client_id: str, tab_id: str) -> JsonObject:
    result = await page_get_tree_deep(client_id, tab_id, max_nodes=1, include_shadow=False, include_iframes=True)
    if not result.get('success'):
        return result
    return {
        'success': True,
        'frames': get_array(result, 'frames', []),
        'partial': bool(result.get('partial', False)),
        'errors': get_array(result, 'errors', []),
    }


async def frame_snapshot(client_id: str, tab_id: str, frame_path: list[str], max_nodes: int = 300) -> JsonObject:
    result = await page_get_tree_deep(client_id, tab_id, max_nodes=max_nodes)
    if not result.get('success'):
        return result
    elements: JsonArray = []
    for element_value in get_array(result, 'elements', []):
        element = require_json_object(element_value, 'deep tree element')
        if get_array(element, 'frame_path', [])[: len(frame_path)] == frame_path:
            elements.append(element)
    return {
        'success': True,
        'frame_path': list(frame_path),
        'elements': elements,
        'count': len(elements),
        'partial': bool(result.get('partial', False)),
        'errors': get_array(result, 'errors', []),
    }


async def _scroll(client_id: str, tab_id: str, expression: str) -> JsonObject:
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        result = await tab.execute_script(
            f'{expression};return {{x:window.scrollX,y:window.scrollY}};',
            return_by_value=True,
        )
        return {'success': True, 'position': extract_script_object(result)}
    except StructuredError as exc:
        return exc.to_dict()
    except (PydollException, InvalidScriptResponseError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Scroll failed: {exc}', retryable=True).to_dict()


def _nodes_by_signature(nodes: JsonArray) -> dict[str, JsonObject]:
    result: dict[str, JsonObject] = {}
    for node_value in nodes:
        node = require_json_object(node_value, 'snapshot node')
        result[_signature(node)] = node
    return result


def _signature(node: JsonObject) -> str:
    return '|'.join(str(node.get(key, '')) for key in ('tag', 'text', 'selector_hint', 'frame_path', 'shadow_path'))
