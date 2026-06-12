"""Tests for path traversal blocking in validate_artifact_path."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]


class TestArtifactPathValidation:
    def setup_method(self):
        from pydoll_mcp_server.security.paths import validate_artifact_path

        self.validate = validate_artifact_path

        import tempfile
        self._tmp = tempfile.mkdtemp()
        self.artifacts = Path(self._tmp) / 'artifacts'
        self.downloads = Path(self._tmp) / 'downloads'
        self.tmp_dir = Path(self._tmp) / 'tmp'
        self.artifacts.mkdir()
        self.downloads.mkdir()
        self.tmp_dir.mkdir()

        class FakeConfig:
            def __init__(self, artifacts, downloads, tmp_dir):
                self.artifacts_dir = artifacts
                self.downloads_dir = downloads
                self.tmp_dir = tmp_dir

        self.config = FakeConfig(self.artifacts, self.downloads, self.tmp_dir)

    def teardown_method(self):
        import shutil
        if hasattr(self, '_tmp'):
            shutil.rmtree(self._tmp, ignore_errors=True)

    def test_accepts_relative_simple(self):
        result = self.validate('screenshot.png', self.config)
        assert result is not None
        assert 'screenshot.png' in str(result)

    def test_accepts_relative_subdir(self):
        result = self.validate('subdir/screenshot.png', self.config)
        assert result is not None
        assert 'subdir' in str(result)

    def test_rejects_parent_traversal(self):
        result = self.validate('../escape.png', self.config)
        assert result is None, f'Should reject ../escape.png but got: {result}'

    def test_rejects_nested_parent_traversal(self):
        result = self.validate('subdir/../../escape.png', self.config)
        assert result is None, f'Should reject subdir/../../escape.png but got: {result}'

    def test_rejects_absolute_outside_allowlist(self):
        import tempfile
        outside = Path(tempfile.gettempdir()) / 'outside.png'
        result = self.validate(str(outside), self.config)
        # Should be None UNLESS tempdir happens to be inside artifacts/downloads/tmp
        if result is not None:
            in_artifacts = str(self.artifacts) in str(result)
            in_downloads = str(self.downloads) in str(result)
            in_tmp = str(self.tmp_dir) in str(result)
            assert in_artifacts or in_downloads or in_tmp

    def test_accepts_absolute_inside_allowlist(self):
        p = str(self.artifacts / 'screen.png')
        result = self.validate(p, self.config)
        assert result is not None

    def test_accepts_absolute_in_downloads(self):
        p = str(self.downloads / 'file.png')
        result = self.validate(p, self.config)
        assert result is not None

    def test_accepts_absolute_in_tmp(self):
        p = str(self.tmp_dir / 'scratch.png')
        result = self.validate(p, self.config)
        assert result is not None

    def test_rejects_absolute_near_prefix(self):
        result = self.validate('/tmp/artifacts-other/evil.png', self.config)
        assert result is None, f'Should reject prefix bypass but got: {result}'
