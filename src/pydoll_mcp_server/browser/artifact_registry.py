"""In-memory artifact registry with hashes and client-scoped paths."""

from __future__ import annotations

import hashlib
import mimetypes
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydoll.browser.tab import Tab
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.pydoll_compat import get_tab_url
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_object
from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.security.paths import validate_artifact_path


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    client_id: str
    relative_path: str
    absolute_path: str
    mime_type: str
    size: int
    sha256: str
    timestamp: float
    url: str
    viewport: JsonObject
    evidence_kind: str

    def to_json(self, include_absolute_path: bool = False) -> JsonObject:
        result: JsonObject = {
            'artifact_id': self.artifact_id,
            'relative_path': self.relative_path,
            'mime_type': self.mime_type,
            'size': self.size,
            'sha256': self.sha256,
            'timestamp': self.timestamp,
            'url': self.url,
            'viewport': self.viewport,
            'evidence_kind': self.evidence_kind,
        }
        if include_absolute_path:
            result['path'] = self.absolute_path
        return result


_ARTIFACTS: dict[tuple[str, str], ArtifactRecord] = {}
_EVIDENCE_KINDS = frozenset({'form_initial', 'pre_submission_review', 'submission_confirmation', 'diagnostic'})


def valid_evidence_kind(value: str) -> bool:
    return value in _EVIDENCE_KINDS


async def artifact_context(tab: Tab) -> tuple[str, JsonObject]:
    try:
        url = await get_tab_url(tab) or ''
    except (PydollException, TypeError, ValueError, AttributeError):
        url = ''
    try:
        result = await tab.execute_script(
            'return {width: window.innerWidth, height: window.innerHeight, '
            'device_pixel_ratio: window.devicePixelRatio || 1};',
            return_by_value=True,
        )
        viewport = extract_normalized_object(result, 'artifact_context')
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        viewport = {}
    return url, viewport


def register_artifact(
    client_id: str,
    path: str,
    mime_type: str = '',
    evidence_kind: str = 'diagnostic',
    url: str = '',
    viewport: JsonObject | None = None,
) -> JsonObject:
    config = get_config()
    safe_path = validate_artifact_path(path, config)
    if safe_path is None:
        return {'success': False, 'error_code': 'PERMISSION_DENIED', 'message': 'Artifact path is not allowlisted.'}
    if evidence_kind not in _EVIDENCE_KINDS:
        return {'success': False, 'error_code': 'INVALID_INPUT', 'message': 'Unknown evidence_kind.'}
    file_path = Path(safe_path)
    try:
        file_size = file_path.stat().st_size
        digest = _sha256(file_path)
    except OSError as exc:
        return {'success': False, 'error_code': 'RESOURCE_NOT_FOUND', 'message': f'Artifact is unavailable: {exc}'}
    artifact_id = f'artifact_{uuid.uuid4().hex[:16]}'
    base = config.artifacts_dir.resolve(strict=False)
    try:
        relative_path = file_path.resolve(strict=False).relative_to(base).as_posix()
    except ValueError:
        relative_path = file_path.name
    record = ArtifactRecord(
        artifact_id=artifact_id,
        client_id=client_id,
        relative_path=relative_path,
        absolute_path=str(file_path.resolve(strict=False)),
        mime_type=mime_type or mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream',
        size=file_size,
        sha256=digest,
        timestamp=time.time(),
        url=url,
        viewport=viewport or {},
        evidence_kind=evidence_kind,
    )
    _ARTIFACTS[(client_id, artifact_id)] = record
    return {'success': True, **record.to_json()}


def get_artifact(client_id: str, artifact_id: str) -> ArtifactRecord | None:
    return _ARTIFACTS.get((client_id, artifact_id))


def artifact_summary(client_id: str, artifact_id: str) -> JsonObject:
    record = get_artifact(client_id, artifact_id)
    if record is None:
        return {'success': False, 'error_code': 'RESOURCE_NOT_FOUND', 'message': 'Artifact not found.'}
    return {'success': True, **record.to_json()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    'ArtifactRecord',
    'artifact_context',
    'artifact_summary',
    'get_artifact',
    'register_artifact',
    'valid_evidence_kind',
]
