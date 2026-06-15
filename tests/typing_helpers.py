"""Typed assertions for JSON-shaped MCP responses in tests."""

from __future__ import annotations

from pydoll_mcp_server.json_types import JsonArray, JsonObject, JsonValue, require_json_array, require_json_object


def object_at(data: JsonObject, key: str) -> JsonObject:
    return require_json_object(data[key], key)


def array_at(data: JsonObject, key: str) -> JsonArray:
    return require_json_array(data[key], key)


def string_at(data: JsonObject, key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise AssertionError(f'{key} is not a string: {value!r}')
    return value


def int_at(data: JsonObject, key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f'{key} is not an int: {value!r}')
    return value


def bool_at(data: JsonObject, key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise AssertionError(f'{key} is not a bool: {value!r}')
    return value


def value_as_object(value: JsonValue) -> JsonObject:
    return require_json_object(value, 'value')
