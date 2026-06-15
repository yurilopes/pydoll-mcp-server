"""Security module: redaction, permissions, and policy."""

from __future__ import annotations

import re
from pathlib import Path

from pydoll_mcp_server.json_types import JsonArray, JsonObject

SENSITIVE_FIELD_PATTERNS = [
    re.compile(r'password', re.IGNORECASE),
    re.compile(r'passwd', re.IGNORECASE),
    re.compile(r'secret', re.IGNORECASE),
    re.compile(r'token', re.IGNORECASE),
    re.compile(r'api[_-]?key', re.IGNORECASE),
    re.compile(r'apikey', re.IGNORECASE),
    re.compile(r'authorization', re.IGNORECASE),
    re.compile(r'bearer', re.IGNORECASE),
    re.compile(r'credential', re.IGNORECASE),
    re.compile(r'private[_-]?key', re.IGNORECASE),
    re.compile(r'access[_-]?token', re.IGNORECASE),
    re.compile(r'refresh[_-]?token', re.IGNORECASE),
    re.compile(r'session[_-]?id', re.IGNORECASE),
    re.compile(r'csrf', re.IGNORECASE),
    re.compile(r'xsrf', re.IGNORECASE),
    re.compile(r'cookie', re.IGNORECASE),
]


def is_sensitive_field(name: str) -> bool:
    return any(pattern.search(name) for pattern in SENSITIVE_FIELD_PATTERNS)


def redact_dict(data: JsonObject, redact_all: bool = False) -> JsonObject:
    result: JsonObject = {}
    for key, value in data.items():
        if redact_all or is_sensitive_field(key):
            if isinstance(value, bool):
                result[key] = False
            elif isinstance(value, int | float):
                result[key] = 0
            elif isinstance(value, dict):
                result[key] = redact_dict(value, redact_all=True)
            elif isinstance(value, list):
                result[key] = []
            else:
                result[key] = '[REDACTED]'
        elif isinstance(value, dict):
            result[key] = redact_dict(value, redact_all=redact_all)
        elif isinstance(value, list):
            result[key] = _redact_array(value, redact_all)
        else:
            result[key] = value
    return result


def _redact_array(values: JsonArray, redact_all: bool) -> JsonArray:
    result: JsonArray = []
    for value in values:
        if isinstance(value, dict):
            result.append(redact_dict(value, redact_all=True))
        elif redact_all:
            result.append('[REDACTED]')
        else:
            result.append(value)
    return result


class PathAllowlist:
    def __init__(self, allowed_dirs: list[str]) -> None:
        self._allowed: list[Path] = [Path(d).resolve() for d in allowed_dirs]

    def add(self, directory: str) -> None:
        self._allowed.append(Path(directory).resolve())

    def is_allowed(self, path: str) -> bool:
        try:
            resolved = Path(path).resolve(strict=False)
        except OSError:
            return False
        for allowed in self._allowed:
            try:
                resolved.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False

    def validate_read(self, path: str) -> None:
        if not self.is_allowed(path):
            raise PermissionError(f'Path not in allowlist: {path}')

    def validate_write(self, path: str) -> None:
        if not self.is_allowed(path):
            raise PermissionError(f'Write path not in allowlist: {path}')

    def validate_upload(self, paths: list[str]) -> list[str]:
        return [p for p in paths if not self.is_allowed(p)]


PROHIBITED_METHODS = [
    'execute_cdp_cmd',
    'execute_os_command',
    'read_file_arbitrary',
    'write_file_arbitrary',
]
