"""Typed DOM models and parsers for JavaScript boundary results."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypedDict

from pydoll.elements.web_element import WebElement
from typing_extensions import NotRequired

from pydoll_mcp_server.json_types import (
    JsonObject,
    get_array,
    get_bool,
    get_int,
    get_object,
    get_string,
    require_json_object,
)

ElementBounds = dict[str, float]


class RawTreeNode(TypedDict):
    element_id: str
    tag: str
    text: str
    attrs: dict[str, str]
    bounds: ElementBounds
    visible: bool
    children: list[str]


class RawTreeResult(TypedDict):
    nodes: list[RawTreeNode]
    root_id: str | None
    count: int


class DeepRawElement(TypedDict):
    element_id: str
    tag: str
    text: str
    attrs: dict[str, str]
    selector_hint: str
    xpath_hint: str
    bounding_box: ElementBounds
    visible: bool
    enabled: bool
    clickable: bool
    frame_path: list[str]
    shadow_path: list[str]
    pydoll_element: NotRequired[WebElement]


def parse_tree_result(value: object) -> RawTreeResult:
    root = require_json_object(value, 'tree result')
    nodes = [parse_tree_node(item) for item in get_array(root, 'nodes', [])]
    root_value = root.get('rootId')
    if root_value is not None and not isinstance(root_value, str):
        raise ValueError('tree result.rootId must be a string or null')
    return {'nodes': nodes, 'root_id': root_value, 'count': get_int(root, 'count')}


def parse_tree_node(value: object) -> RawTreeNode:
    node = require_json_object(value, 'tree node')
    return {
        'element_id': get_string(node, 'elementId'),
        'tag': get_string(node, 'tag'),
        'text': get_string(node, 'text'),
        'attrs': _string_map(get_object(node, 'attrs', {}), 'tree node.attrs'),
        'bounds': _bounds(node.get('bounds')),
        'visible': get_bool(node, 'visible'),
        'children': _string_list(get_array(node, 'children', []), 'tree node.children'),
    }


def json_from_tree_node(node: RawTreeNode) -> JsonObject:
    return {
        'elementId': node['element_id'],
        'tag': node['tag'],
        'text': node['text'],
        'attrs': dict(node['attrs']),
        'bounds': dict(node['bounds']),
        'visible': node['visible'],
        'children': list(node['children']),
    }


def parse_deep_element(value: object) -> DeepRawElement:
    node = require_json_object(value, 'deep element')
    return {
        'element_id': get_string(node, 'elementId'),
        'tag': get_string(node, 'tag'),
        'text': get_string(node, 'text'),
        'attrs': _string_map(get_object(node, 'attrs', {}), 'deep element.attrs'),
        'selector_hint': get_string(node, 'selector_hint'),
        'xpath_hint': get_string(node, 'xpath_hint'),
        'bounding_box': _bounds(node.get('bounding_box')),
        'visible': get_bool(node, 'visible'),
        'enabled': get_bool(node, 'enabled', True),
        'clickable': get_bool(node, 'clickable'),
        'frame_path': _string_list(get_array(node, 'frame_path', []), 'deep element.frame_path'),
        'shadow_path': _string_list(get_array(node, 'shadow_path', []), 'deep element.shadow_path'),
    }


def _string_map(value: JsonObject, context: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str):
            raise ValueError(f'{context}.{key} must be a string')
        result[key] = item
    return result


def _string_list(value: Iterable[object], context: str) -> list[str]:
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f'{context} must contain only strings')
        result.append(item)
    return result


def _bounds(value: object) -> ElementBounds:
    if value is None:
        return {}
    raw = require_json_object(value, 'element bounds')
    bounds: ElementBounds = {}
    for key in ('x', 'y', 'width', 'height'):
        item = raw.get(key)
        if isinstance(item, bool) or not isinstance(item, int | float):
            continue
        bounds[key] = float(item)
    return bounds
