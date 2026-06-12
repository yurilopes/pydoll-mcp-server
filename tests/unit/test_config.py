"""Tests for configuration management."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from pydoll_mcp_server.config import (
    LimitsConfig,
    ServerConfig,
    TimeoutConfig,
    _default_runtime_dir,
)


class TestServerConfig:
    def test_default_host(self) -> None:
        config = ServerConfig(auth_token='test-token')
        assert config.host == '127.0.0.1'

    def test_default_port(self) -> None:
        config = ServerConfig(auth_token='test-token')
        assert config.port == 8765

    def test_auth_enabled_with_token(self) -> None:
        config = ServerConfig(auth_token='test-token')
        assert config.auth_enabled is True

    def test_auth_disabled_explicit(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_ALLOW_NO_AUTH': 'true'}):
            config = ServerConfig(allow_no_auth=True, auth_token='')
            assert config.auth_enabled is False

    def test_missing_token_raises(self) -> None:
        with pytest.raises(ValueError):
            ServerConfig(auth_token='')

    def test_runtime_dir_windows(self) -> None:
        with patch.object(sys, 'platform', 'win32'), \
                patch.dict(os.environ, {'LOCALAPPDATA': 'C:\\Users\\Test\\AppData\\Local'}):
            result = _default_runtime_dir()
            assert 'pydoll-mcp-server' in str(result)

    def test_runtime_dir_macos(self) -> None:
        with patch.object(sys, 'platform', 'darwin'), \
                patch.object(Path, 'home', return_value=Path('/Users/test')):
            result = _default_runtime_dir()
            assert 'pydoll-mcp-server' in str(result)

    def test_runtime_dir_linux(self) -> None:
        with patch.object(sys, 'platform', 'linux'), \
                patch.object(Path, 'home', return_value=Path('/home/test')):
            result = _default_runtime_dir()
            assert 'pydoll-mcp-server' in str(result)

    def test_port_out_of_range(self) -> None:
        from pydantic_core import ValidationError
        with pytest.raises(ValidationError):
            ServerConfig(auth_token='test-token', port=0)

    def test_port_max(self) -> None:
        config = ServerConfig(auth_token='test-token', port=65535)
        assert config.port == 65535

    def test_path_properties(self) -> None:
        config = ServerConfig(auth_token='test-token')
        assert 'profiles' in str(config.profiles_dir)
        assert 'tmp' in str(config.tmp_dir)
        assert 'downloads' in str(config.downloads_dir)
        assert 'artifacts' in str(config.artifacts_dir)
        assert 'logs' in str(config.logs_dir)


class TestTimeoutConfig:
    def test_defaults(self) -> None:
        config = TimeoutConfig()
        assert config.goto == 30.0
        assert config.reload == 30.0
        assert config.click == 10.0
        assert config.js_execute == 5.0
        assert config.back_forward == 15.0
        assert config.max_timeout == 120.0

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {'PYDOLL_MCP_TIMEOUT_GOTO': '45'}):
            config = TimeoutConfig()
            assert config.goto == 45.0


class TestLimitsConfig:
    def test_defaults(self) -> None:
        config = LimitsConfig()
        assert config.max_tree_depth == 6
        assert config.max_tree_nodes == 300
        assert config.max_deep_depth == 10
        assert config.max_deep_nodes == 1000
        assert config.max_text_chars == 20000
        assert config.max_js_code == 20000
        assert config.max_js_result == 262144
