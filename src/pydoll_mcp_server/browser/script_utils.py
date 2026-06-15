"""Helpers to extract values from CDP/Pydoll execute_script responses."""

from __future__ import annotations

from pydoll_mcp_server.json_types import (
    InvalidJsonValueError,
    JsonArray,
    JsonObject,
    JsonValue,
    normalize_json_value,
)


class InvalidScriptResponseError(ValueError):
    """Raised when Pydoll returns an invalid Runtime.evaluate response."""


def extract_script_value(response: object) -> JsonValue:
    """Extract the `value` from a CDP Runtime.evaluate response.

    The CDP response nest is:
      {"result": {"result": {"value": <actual>}}}   or
      {"result": {"result": {"objectId": "..."}}}   (without return_by_value)
    """
    evaluate_result = extract_script_response(response)
    if 'value' in evaluate_result:
        try:
            return normalize_json_value(evaluate_result['value'], 'script result')
        except InvalidJsonValueError as exc:
            raise InvalidScriptResponseError(str(exc)) from exc
    return None


def extract_script_response(response: object) -> JsonObject:
    """Return the full evaluate result object (type + value + objectId)."""
    try:
        root = normalize_json_value(response, 'script response')
    except InvalidJsonValueError as exc:
        raise InvalidScriptResponseError(str(exc)) from exc
    if not isinstance(root, dict):
        raise InvalidScriptResponseError('Script response must be a JSON object')
    inner = root.get('result')
    if not isinstance(inner, dict):
        raise InvalidScriptResponseError('Script response result must be a mapping')
    evaluate_result = inner.get('result', inner)
    if not isinstance(evaluate_result, dict):
        raise InvalidScriptResponseError('Runtime.evaluate result must be a mapping')
    return evaluate_result


def extract_script_object(response: object) -> JsonObject:
    value = extract_script_value(response)
    if not isinstance(value, dict):
        raise InvalidScriptResponseError('Script result must be a JSON object')
    return value


def extract_script_array(response: object) -> JsonArray:
    value = extract_script_value(response)
    if not isinstance(value, list):
        raise InvalidScriptResponseError('Script result must be a JSON array')
    return value


def extract_script_string(response: object) -> str:
    value = extract_script_value(response)
    if not isinstance(value, str):
        raise InvalidScriptResponseError('Script result must be a string')
    return value


def extract_script_bool(response: object) -> bool:
    value = extract_script_value(response)
    if not isinstance(value, bool):
        raise InvalidScriptResponseError('Script result must be a boolean')
    return value


def extract_script_number(response: object) -> int | float:
    value = extract_script_value(response)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidScriptResponseError('Script result must be a number')
    return value
