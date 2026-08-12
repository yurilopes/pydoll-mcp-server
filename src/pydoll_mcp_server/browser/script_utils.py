"""Helpers to extract values from CDP/Pydoll execute_script responses."""

from __future__ import annotations

from typing import TypedDict

from pydoll_mcp_server.json_types import (
    InvalidJsonValueError,
    JsonArray,
    JsonObject,
    JsonValue,
    normalize_json_value,
)


class InvalidScriptResponseError(ValueError):
    """Raised when Pydoll returns an invalid Runtime.evaluate response."""


class ScriptResult(TypedDict):
    """Normalized result from a Pydoll script boundary."""

    success: bool
    value: JsonValue
    value_type: str
    runtime_type: str
    operation: str
    retryable: bool


def normalize_script_result(
    response: object,
    operation: str,
    expected_type: str = '',
) -> JsonObject:
    """Normalize primitive and structured script results without leaking raw CDP data."""

    response_format = 'cdp_runtime_evaluate'
    try:
        response_info = extract_script_response(response)
        value = extract_script_value(response)
    except InvalidScriptResponseError as exc:
        return {
            'success': False,
            'error_code': 'EXECUTION_ERROR',
            'message': f'Script result normalization failed for {operation}: {exc}',
            'retryable': True,
            'operation': operation,
            'expected_type': expected_type,
            'received_type': 'malformed',
            'response_shape': type(response).__name__,
            'response_format': 'malformed',
            'resource_state': 'unknown',
        }

    value_type = script_value_type(value, response_info)
    runtime_type = str(response_info.get('type', ''))
    if _has_exception_details(response):
        return {
            'success': False,
            'error_code': 'EXECUTION_ERROR',
            'message': f'Script execution raised an exception for {operation}.',
            'retryable': True,
            'operation': operation,
            'expected_type': expected_type,
            'received_type': runtime_type or value_type,
            'response_shape': type(response).__name__,
            'response_format': 'cdp_runtime_exception',
            'resource_state': 'unknown',
        }
    result: JsonObject = {
        'success': True,
        'value': value,
        'value_type': value_type,
        'runtime_type': runtime_type,
        'operation': operation,
        'retryable': False,
        'response_format': response_format,
        'resource_state': 'observed',
    }
    if expected_type and value_type != expected_type:
        result.update(
            {
                'success': False,
                'error_code': 'EXECUTION_ERROR',
                'message': f'Expected {expected_type} from {operation}, received {value_type}.',
                'retryable': True,
                'expected_type': expected_type,
                'received_type': value_type,
            }
        )
    return result


def _has_exception_details(response: object) -> bool:
    try:
        normalized = normalize_json_value(response, 'script response')
    except InvalidJsonValueError:
        return False
    if not isinstance(normalized, dict):
        return False
    inner = normalized.get('result')
    if not isinstance(inner, dict):
        return False
    return inner.get('exceptionDetails') is not None


def script_value_type(value: JsonValue, response: JsonObject | None = None) -> str:
    """Return a stable semantic type for a normalized JavaScript value."""

    response_info = response or {}
    runtime_type = str(response_info.get('type', ''))
    if runtime_type == 'undefined':
        return 'undefined'
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int | float):
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'array'
    return 'object'


def extract_normalized_value(response: object, operation: str, expected_type: str = '') -> JsonValue:
    normalized = normalize_script_result(response, operation, expected_type)
    if normalized.get('success') is not True:
        message = normalized.get('message')
        raise InvalidScriptResponseError(str(message) if isinstance(message, str) else 'Script operation failed')
    return normalized.get('value')


def extract_normalized_object(response: object, operation: str) -> JsonObject:
    value = extract_normalized_value(response, operation, 'object')
    if not isinstance(value, dict):
        raise InvalidScriptResponseError(f'{operation} did not return an object')
    return value


def extract_normalized_array(response: object, operation: str) -> JsonArray:
    value = extract_normalized_value(response, operation, 'array')
    if not isinstance(value, list):
        raise InvalidScriptResponseError(f'{operation} did not return an array')
    return value


def extract_normalized_string(response: object, operation: str) -> str:
    value = extract_normalized_value(response, operation, 'string')
    if not isinstance(value, str):
        raise InvalidScriptResponseError(f'{operation} did not return a string')
    return value


def extract_normalized_bool(response: object, operation: str) -> bool:
    value = extract_normalized_value(response, operation, 'boolean')
    if not isinstance(value, bool):
        raise InvalidScriptResponseError(f'{operation} did not return a boolean')
    return value


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
