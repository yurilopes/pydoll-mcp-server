"""Structured logging with redaction support."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    (
        r'("?(?:api[_-]?key|apikey|secret|password|passwd|token|auth)"?\s*[:=]\s*)'
        r'["\']?[^,"\'\s}]+["\']?',
        r'\1"[REDACTED]"',
    ),
    (r'Bearer\s+\S+', 'Bearer [REDACTED]'),
    (
        r'("?(?:authorization|proxy-authorization)"?\s*:\s*)["\']?[^,"\'\s}]+["\']?',
        r'\1"[REDACTED]"',
    ),
    (r'"cookie"\s*:\s*"[^"]*"', '"cookie":"[REDACTED_COOKIE]"'),
    (r'"set-cookie"\s*:\s*"[^"]*"', '"set-cookie":"[REDACTED_COOKIE]"'),
]


def redact(value: str) -> str:
    result = value
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


@dataclass
class OperationLog:
    request_id: str = ''
    client_id: str = ''
    session_id: str = ''
    browser_id: str = ''
    tab_id: str = ''
    tool: str = ''
    operation: str = ''
    duration_ms: float = 0.0
    status: str = 'success'
    error_code: str = ''
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            'request_id': self.request_id,
            'client_id': self.client_id,
            'session_id': self.session_id,
            'browser_id': self.browser_id,
            'tab_id': self.tab_id,
            'tool': self.tool,
            'operation': self.operation,
            'duration_ms': round(self.duration_ms, 2),
            'status': self.status,
            'error_code': self.error_code,
            **self.extra,
        }, default=str, ensure_ascii=False)


class PydollMCPLogger:
    def __init__(self) -> None:
        self._logger = logging.getLogger('pydoll_mcp_server')
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s'
            ))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)

    def set_level(self, level: str) -> None:
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    def log_operation(self, op: OperationLog) -> None:
        self._logger.info(redact(op.to_json()))

    def error(self, msg: str, *args: Any) -> None:
        self._logger.error(redact(msg), *args)

    def warning(self, msg: str, *args: Any) -> None:
        self._logger.warning(redact(msg), *args)

    def info(self, msg: str, *args: Any) -> None:
        self._logger.info(redact(msg), *args)

    def debug(self, msg: str, *args: Any) -> None:
        self._logger.debug(redact(msg), *args)


_logger_instance: PydollMCPLogger | None = None


def get_logger() -> PydollMCPLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = PydollMCPLogger()
    return _logger_instance
