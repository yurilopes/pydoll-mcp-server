"""Path validation helpers shared across tools."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ArtifactPathConfig(Protocol):
    @property
    def artifacts_dir(self) -> Path: ...

    @property
    def downloads_dir(self) -> Path: ...

    @property
    def tmp_dir(self) -> Path: ...


def validate_artifact_path(path: str, config: ArtifactPathConfig) -> str | None:
    p = Path(path)

    if p.is_absolute():
        try:
            resolved = p.resolve(strict=False)
            for allowed_dir in [config.artifacts_dir, config.downloads_dir, config.tmp_dir]:
                try:
                    resolved_base = allowed_dir.resolve(strict=False)
                    resolved.relative_to(resolved_base)
                    return str(resolved)
                except ValueError:
                    continue
        except (OSError, RuntimeError):
            return None
        return None

    base = config.artifacts_dir.resolve(strict=False)
    candidate = (base / p).resolve(strict=False)
    try:
        candidate.relative_to(base)
        return str(candidate)
    except ValueError:
        return None
