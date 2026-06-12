"""Helpers to extract values from CDP/Pydoll execute_script responses."""

from __future__ import annotations

from typing import Any


def extract_script_value(response: Any) -> Any:
    """Extract the `value` from a CDP Runtime.evaluate response.

    The CDP response nest is:
      {"result": {"result": {"value": <actual>}}}   or
      {"result": {"result": {"objectId": "..."}}}   (without return_by_value)
    """
    try:
        inner = response.get('result', {})
        if isinstance(inner, dict):
            evaluate_result = inner.get('result', inner)
            if isinstance(evaluate_result, dict):
                return evaluate_result.get('value')
    except Exception:
        pass
    return None


def extract_script_response(response: Any) -> Any:
    """Return the full evaluate result object (type + value + objectId)."""
    try:
        inner = response.get('result', {})
        if isinstance(inner, dict):
            return inner.get('result', inner)
    except Exception:
        pass
    return response
