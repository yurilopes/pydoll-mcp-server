"""JavaScript execution tools with security scanning."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_script_response,
    extract_script_value,
)
from pydoll_mcp_server.config import get_limits_config, get_timeout_config
from pydoll_mcp_server.errors import ErrorCode, ResourceState, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, JsonValue, get_string
from pydoll_mcp_server.logging import OperationLog, get_logger

BLOCKED_PATTERNS = [
    (re.compile(r'\bdocument\.cookie\b'), 'document.cookie access'),
    (re.compile(r'\blocalStorage\.'), 'localStorage access'),
    (re.compile(r'\bsessionStorage\.'), 'sessionStorage access'),
    (re.compile(r'(?:^|\W)submit\s*\('), 'form submission'),
    (re.compile(r'\blocation\s*=\s*["\']'), 'location assignment'),
    (re.compile(r'\blocation\.href\s*='), 'location.href assignment'),
    (re.compile(r'while\s*\(\s*true\s*\)'), 'infinite loop pattern'),
    (re.compile(r'while\s*\(\s*1\s*\)'), 'infinite loop pattern'),
]

FETCH_PATTERN = re.compile(r'\bfetch\s*\(\s*["\'][^"\']*["\']\s*\)')


def scan_script(script: str) -> list[str]:
    warnings: list[str] = []
    for pattern, description in BLOCKED_PATTERNS:
        if pattern.search(script):
            warnings.append(description)
    if FETCH_PATTERN.search(script):
        warnings.append('fetch() call - potential external data exfiltration')
    return warnings


async def js_evaluate_readonly(
    client_id: str,
    tab_id: str,
    script: str,
    timeout: float | None = None,
) -> JsonObject:
    config = get_timeout_config()
    limits = get_limits_config()
    timeout = timeout or config.js_execute
    timeout = min(timeout, config.max_js_timeout)
    get_logger()

    if len(script) > limits.max_js_code:
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message=f'Script too long: {len(script)} chars. Max {limits.max_js_code}.',
            retryable=False,
        ).to_dict()

    warnings = scan_script(script)
    if any(
        w
        in [
            'document.cookie access',
            'localStorage access',
            'sessionStorage access',
            'form submission',
            'location assignment',
            'location.href assignment',
        ]
        for w in warnings
    ):
        warning_values: JsonArray = []
        warning_values.extend(warnings)
        return StructuredError(
            error_code=ErrorCode.BLOCKED_PATTERN,
            message=f'Script contains blocked patterns: {", ".join(warnings)}',
            retryable=False,
            details={'warnings': warning_values},
            recovery_hint='Use js_evaluate for scripts with side effects, or remove the blocked patterns.',
        ).to_dict()

    return await _execute_js(client_id, tab_id, script, timeout, read_only=True)


async def js_evaluate(
    client_id: str,
    tab_id: str,
    script: str,
    timeout: float | None = None,
) -> JsonObject:
    config = get_timeout_config()
    limits = get_limits_config()
    timeout = timeout or config.js_execute
    timeout = min(timeout, config.max_js_timeout)
    logger = get_logger()

    if len(script) > limits.max_js_code:
        return StructuredError(
            error_code=ErrorCode.INVALID_INPUT,
            message=f'Script too long: {len(script)} chars. Max {limits.max_js_code}.',
            retryable=False,
        ).to_dict()

    warnings = scan_script(script)
    if warnings:
        logger.warning(f'JS evaluate warnings for client {client_id}: {warnings}')

    return await _execute_js(client_id, tab_id, script, timeout, read_only=False)


async def _execute_js(
    client_id: str,
    tab_id: str,
    script: str,
    timeout: float,
    read_only: bool,
) -> JsonObject:
    registry = get_registry()
    logger = get_logger()
    limits = get_limits_config()

    try:
        tab_info = registry.get_tab(client_id, tab_id)
    except StructuredError as e:
        return e.to_dict()

    pydoll_tab = tab_info.pydoll_tab
    start = time.time()

    try:
        result = await asyncio.wait_for(
            pydoll_tab.execute_script(script, return_by_value=True),
            timeout=timeout + 2,
        )
    except asyncio.TimeoutError:
        duration_ms = (time.time() - start) * 1000
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message=f'JS execution timed out after {timeout}s',
            retryable=True,
            resource_state=ResourceState.DEGRADED,
            details={'timing_ms': round(duration_ms, 1)},
        ).to_dict()
    except PydollException as e:
        duration_ms = (time.time() - start) * 1000
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'JS execution error: {e}',
            retryable=True,
            details={'error': str(e), 'timing_ms': round(duration_ms, 1)},
        ).to_dict()

    duration_ms = (time.time() - start) * 1000

    try:
        response_info = extract_script_response(result)
        raw_value = extract_script_value(result)
    except InvalidScriptResponseError as exc:
        return StructuredError(
            error_code=ErrorCode.EXECUTION_ERROR,
            message=f'JS execution returned an invalid response: {exc}',
            retryable=False,
        ).to_dict()

    result_str = json.dumps(raw_value, ensure_ascii=False)
    result_size = len(result_str.encode('utf-8'))
    returned_value: JsonValue = raw_value
    truncated = result_size > limits.max_js_result
    if truncated and isinstance(raw_value, str):
        result_bytes = raw_value.encode('utf-8')[: limits.max_js_result]
        returned_value = result_bytes.decode('utf-8', errors='replace')
        result_str = json.dumps(returned_value, ensure_ascii=False)
        result_size = len(result_str.encode('utf-8'))
    elif truncated:
        returned_value = None

    script_hash = hashlib.sha256(script.encode()).hexdigest()[:16]
    value_type = _value_type(raw_value, response_info)
    diagnostic = _diagnostic(raw_value, response_info, truncated)

    logger.log_operation(
        OperationLog(
            client_id=client_id,
            tab_id=tab_id,
            tool='js_evaluate_readonly' if read_only else 'js_evaluate',
            status='success',
            duration_ms=duration_ms,
            extra={
                'script_hash': script_hash,
                'result_size': result_size,
                'truncated': truncated,
                'read_only': read_only,
            },
        )
    )

    return {
        'success': True,
        'value': returned_value,
        'value_type': value_type,
        'truncated': truncated,
        'result_size_bytes': result_size,
        'script_hash': script_hash,
        'timing_ms': round(duration_ms, 1),
        'diagnostic': diagnostic,
        'audit': {
            'script_hash': script_hash,
            'duration_ms': round(duration_ms, 1),
            'result_size_bytes': result_size,
        },
    }


def _value_type(value: JsonValue, response: JsonObject) -> str:
    runtime_type = get_string(response, 'type', '')
    subtype = get_string(response, 'subtype', '')
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
    if subtype == 'null':
        return 'null'
    return 'object'


def _diagnostic(value: JsonValue, response: JsonObject, truncated: bool) -> JsonObject:
    diagnostic: JsonObject = {
        'runtime_type': get_string(response, 'type', ''),
    }
    subtype = get_string(response, 'subtype', '')
    if subtype:
        diagnostic['runtime_subtype'] = subtype
    if value is None and 'value' not in response:
        diagnostic['empty_result'] = True
    if truncated:
        diagnostic['truncated_reason'] = 'result exceeded max_js_result bytes'
    return diagnostic
