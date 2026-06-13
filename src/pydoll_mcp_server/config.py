"""Configuration management with Pydantic v2."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_runtime_dir() -> Path:
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))
        return Path(base) / 'pydoll-mcp-server'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'pydoll-mcp-server'
    return Path.home() / '.local' / 'share' / 'pydoll-mcp-server'


class ServerConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='PYDOLL_MCP_',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    host: str = Field(default='127.0.0.1', description='Host to bind the server to')
    port: int = Field(default=8765, ge=1, le=65535, description='Port to listen on')
    log_level: str = Field(default='info', description='Logging level')

    auth_token: str = Field(
        default='',
        description='Required bearer token for MCP requests',
    )
    allow_no_auth: bool = Field(
        default=False,
        description='Allow requests without authentication (development only)',
    )

    runtime_dir: Path = Field(
        default_factory=_default_runtime_dir,
        description='Base directory for runtime data',
    )

    @model_validator(mode='after')
    def validate_auth(self) -> ServerConfig:
        env_token = os.environ.get('PYDOLL_MCP_AUTH_TOKEN', '')
        env_allow = os.environ.get('PYDOLL_MCP_ALLOW_NO_AUTH', '')
        env_transport = os.environ.get('PYDOLL_MCP_TRANSPORT', '')
        if env_token:
            self.auth_token = env_token
        if env_allow and env_allow.lower() in ('true', '1', 'yes'):
            self.allow_no_auth = True
        if env_transport == 'stdio':
            self.allow_no_auth = True
        if not self.allow_no_auth and not self.auth_token:
            raise ValueError(
                'PYDOLL_MCP_AUTH_TOKEN is required when auth is enabled. '
                'Set PYDOLL_MCP_ALLOW_NO_AUTH=true only for development.'
            )
        return self

    @property
    def auth_enabled(self) -> bool:
        return not self.allow_no_auth

    @property
    def profiles_dir(self) -> Path:
        return self.runtime_dir / 'profiles'

    @property
    def tmp_dir(self) -> Path:
        return self.runtime_dir / 'tmp'

    @property
    def downloads_dir(self) -> Path:
        return self.runtime_dir / 'downloads'

    @property
    def artifacts_dir(self) -> Path:
        return self.runtime_dir / 'artifacts'

    @property
    def logs_dir(self) -> Path:
        return self.runtime_dir / 'logs'

    def ensure_directories(self) -> None:
        for d in [
            self.profiles_dir,
            self.tmp_dir,
            self.downloads_dir,
            self.artifacts_dir,
            self.logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


class TimeoutConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='PYDOLL_MCP_TIMEOUT_',
        extra='ignore',
    )

    goto: float = Field(default=30.0, description='Default timeout for page_goto')
    reload: float = Field(default=30.0, description='Default timeout for page_reload')
    back_forward: float = Field(default=15.0, description='Default timeout for page_back/forward')
    wait_selector: float = Field(default=15.0, description='Default timeout for wait_for_selector')
    click: float = Field(default=10.0, description='Default timeout for element_click')
    js_execute: float = Field(default=5.0, description='Default timeout for JS execution')
    deep_tree: float = Field(default=20.0, description='Default timeout for deep tree traversal')
    download: float = Field(default=60.0, description='Default timeout for downloads')

    max_timeout: float = Field(default=120.0, description='Maximum allowed timeout override')
    max_js_timeout: float = Field(default=15.0, description='Maximum JS execution timeout')


class LimitsConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='PYDOLL_MCP_LIMIT_',
        extra='ignore',
    )

    max_tree_depth: int = Field(default=6, description='Default max depth for page_get_tree')
    max_tree_nodes: int = Field(default=300, description='Default max nodes for page_get_tree')
    max_deep_depth: int = Field(default=10, description='Default max depth for page_get_tree_deep')
    max_deep_nodes: int = Field(default=1000, description='Default max nodes for page_get_tree_deep')
    max_text_chars: int = Field(default=20000, description='Default max chars for page_get_text')
    max_js_code: int = Field(default=20000, description='Max JS code characters')
    max_js_result: int = Field(default=262144, description='Max JS result size in bytes (256 KiB)')


@lru_cache
def get_config() -> ServerConfig:
    return ServerConfig()


@lru_cache
def get_timeout_config() -> TimeoutConfig:
    return TimeoutConfig()


@lru_cache
def get_limits_config() -> LimitsConfig:
    return LimitsConfig()
