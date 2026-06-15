"""Tests for path traversal blocking in validate_artifact_path."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]


@dataclass
class FakeConfig:
    artifacts_dir: Path
    downloads_dir: Path
    tmp_dir: Path


class TestArtifactPathValidation:
    validate: Callable[[str, FakeConfig], str | None]
    _tmp: str
    artifacts: Path
    downloads: Path
    tmp_dir: Path
    config: FakeConfig

    def setup_method(self) -> None:
        from pydoll_mcp_server.security.paths import validate_artifact_path

        self.validate = validate_artifact_path

        self._tmp = tempfile.mkdtemp()
        self.artifacts = Path(self._tmp) / 'artifacts'
        self.downloads = Path(self._tmp) / 'downloads'
        self.tmp_dir = Path(self._tmp) / 'tmp'
        self.artifacts.mkdir()
        self.downloads.mkdir()
        self.tmp_dir.mkdir()

        self.config = FakeConfig(self.artifacts, self.downloads, self.tmp_dir)

    def teardown_method(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_accepts_relative_simple(self) -> None:
        result = self.validate('screenshot.png', self.config)
        assert result is not None
        assert 'screenshot.png' in str(result)

    def test_accepts_relative_subdir(self) -> None:
        result = self.validate('subdir/screenshot.png', self.config)
        assert result is not None
        assert 'subdir' in str(result)

    def test_rejects_parent_traversal(self) -> None:
        result = self.validate('../escape.png', self.config)
        assert result is None, f'Should reject ../escape.png but got: {result}'

    def test_rejects_nested_parent_traversal(self) -> None:
        result = self.validate('subdir/../../escape.png', self.config)
        assert result is None, f'Should reject subdir/../../escape.png but got: {result}'

    def test_rejects_absolute_outside_allowlist(self) -> None:
        outside = Path(tempfile.gettempdir()) / 'outside.png'
        result = self.validate(str(outside), self.config)
        # Should be None UNLESS tempdir happens to be inside artifacts/downloads/tmp
        if result is not None:
            in_artifacts = str(self.artifacts) in str(result)
            in_downloads = str(self.downloads) in str(result)
            in_tmp = str(self.tmp_dir) in str(result)
            assert in_artifacts or in_downloads or in_tmp

    def test_accepts_absolute_inside_allowlist(self) -> None:
        p = str(self.artifacts / 'screen.png')
        result = self.validate(p, self.config)
        assert result is not None

    def test_accepts_absolute_in_downloads(self) -> None:
        p = str(self.downloads / 'file.png')
        result = self.validate(p, self.config)
        assert result is not None

    def test_accepts_absolute_in_tmp(self) -> None:
        p = str(self.tmp_dir / 'scratch.png')
        result = self.validate(p, self.config)
        assert result is not None

    def test_rejects_absolute_near_prefix(self) -> None:
        result = self.validate('/tmp/artifacts-other/evil.png', self.config)
        assert result is None, f'Should reject prefix bypass but got: {result}'
