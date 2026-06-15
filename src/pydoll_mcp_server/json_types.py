"""JSON-compatible values and strict boundary validators."""

from __future__ import annotations

from typing import TypeAlias, TypeGuard

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list['JsonValue'] | dict[str, 'JsonValue']
JsonArray: TypeAlias = list[JsonValue]
JsonObject: TypeAlias = dict[str, JsonValue]


class InvalidJsonValueError(ValueError):
    """Raised when an external value cannot be represented safely as JSON."""


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return isinstance(value, tuple)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def normalize_json_value(value: object, context: str = 'value') -> JsonValue:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if _is_object_list(value) or _is_object_tuple(value):
        return [normalize_json_value(item, f'{context}[]') for item in value]
    if _is_object_dict(value):
        result: JsonObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise InvalidJsonValueError(f'{context} contains a non-string object key')
            result[key] = normalize_json_value(item, f'{context}.{key}')
        return result
    raise InvalidJsonValueError(f'{context} is not JSON serializable: {type(value).__name__}')


def require_json_object(value: object, context: str = 'value') -> JsonObject:
    normalized = normalize_json_value(value, context)
    if not isinstance(normalized, dict):
        raise InvalidJsonValueError(f'{context} must be a JSON object')
    return normalized


def require_json_array(value: object, context: str = 'value') -> JsonArray:
    normalized = normalize_json_value(value, context)
    if not isinstance(normalized, list):
        raise InvalidJsonValueError(f'{context} must be a JSON array')
    return normalized


def get_object(data: JsonObject, key: str, default: JsonObject | None = None) -> JsonObject:
    value = data.get(key)
    if value is None and default is not None:
        return default
    return require_json_object(value, key)


def get_array(data: JsonObject, key: str, default: JsonArray | None = None) -> JsonArray:
    value = data.get(key)
    if value is None and default is not None:
        return default
    return require_json_array(value, key)


def get_string(data: JsonObject, key: str, default: str = '') -> str:
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise InvalidJsonValueError(f'{key} must be a string')
    return value


def get_bool(data: JsonObject, key: str, default: bool = False) -> bool:
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise InvalidJsonValueError(f'{key} must be a boolean')
    return value


def get_int(data: JsonObject, key: str, default: int = 0) -> int:
    value = data.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidJsonValueError(f'{key} must be an integer')
    return value


def get_float(data: JsonObject, key: str, default: float = 0.0) -> float:
    value = data.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidJsonValueError(f'{key} must be a number')
    return float(value)
