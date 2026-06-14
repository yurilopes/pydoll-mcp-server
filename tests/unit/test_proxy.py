"""Proxy validation and browser lifecycle security tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pydoll_mcp_server.security.proxy import proxy_validate, validate_proxy

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize('scheme', ['http', 'https', 'socks4', 'socks5'])
def test_validate_proxy_accepts_supported_schemes(scheme: str) -> None:
    config = validate_proxy(f'{scheme}://proxy.example:8080', 'localhost,*.internal')

    assert config.sanitized_url == f'{scheme}://proxy.example:8080'
    assert config.bypass_list == 'localhost,*.internal'


def test_validate_proxy_sanitizes_credentials() -> None:
    config = validate_proxy('http://user:secret@proxy.example:3128')

    assert config.launch_url == 'http://user:secret@proxy.example:3128'
    assert config.sanitized_url == 'http://proxy.example:3128'
    assert config.has_credentials is True
    assert 'user' not in str(config.summary())
    assert 'secret' not in str(config.summary())


@pytest.mark.parametrize(
    'value',
    [
        'ftp://proxy.example:21',
        'http://proxy.example',
        'http://proxy.example:8080/path',
        'http://proxy.example:8080?token=secret',
        'http://localhost:8080',
        'socks5://127.0.0.1:1080',
        'http://user@proxy.example:8080',
    ],
)
def test_proxy_validate_rejects_unsafe_values(value: str) -> None:
    result = proxy_validate(value)

    assert result['error_code'] in {'INVALID_INPUT', 'PERMISSION_DENIED'}
    assert 'secret' not in str(result)


def test_browser_launch_passes_proxy_to_pydoll_but_returns_sanitized_metadata() -> None:
    from pydoll_mcp_server.tools import browser as browser_tools

    async def run() -> None:
        options_seen = None

        class FakeOptions:
            def __init__(self) -> None:
                self.arguments: list[str] = []
                self.headless = False

            def add_argument(self, value: str) -> None:
                self.arguments.append(value)

        class FakeChrome:
            def __init__(self, options) -> None:
                nonlocal options_seen
                options_seen = options

            async def start(self):
                return SimpleNamespace(current_url=_awaitable('about:blank'), title=_awaitable(''))

        profile = SimpleNamespace(path='profile', mode=SimpleNamespace(value='temporary'), profile_id='profile')
        profile_manager = SimpleNamespace(create_temporary=lambda client_id: profile, unlock=lambda profile_id: None)
        registry = SimpleNamespace(
            register_browser=lambda **kwargs: SimpleNamespace(browser_id='browser', **kwargs),
            register_tab=lambda **kwargs: SimpleNamespace(tab_id='tab'),
        )
        with (
            patch.object(browser_tools, 'get_profile_manager', return_value=profile_manager),
            patch.object(browser_tools, 'get_registry', return_value=registry),
            patch('pydoll.browser.Chrome', FakeChrome),
            patch('pydoll.browser.options.ChromiumOptions', FakeOptions),
        ):
            result = await browser_tools.browser_launch(
                'client', profile_mode='temporary',
                proxy_server='socks5://user:secret@proxy.example:1080',
            )
        assert result['success'] is True
        assert result['proxy_server'] == 'socks5://proxy.example:1080'
        assert 'secret' not in str(result)
        assert '--proxy-server=socks5://user:secret@proxy.example:1080' in options_seen.arguments

    asyncio.run(run())


def test_browser_launch_redacts_proxy_credentials_from_errors() -> None:
    from pydoll_mcp_server.tools import browser as browser_tools

    async def run() -> None:
        class FailingChrome:
            def __init__(self, options) -> None:
                pass

            async def start(self):
                raise RuntimeError('Cannot connect using http://user:secret@proxy.example:8080')

        profile = SimpleNamespace(path='profile', mode=SimpleNamespace(value='temporary'), profile_id='profile')
        profile_manager = SimpleNamespace(create_temporary=lambda client_id: profile, unlock=lambda profile_id: None)
        with (
            patch.object(browser_tools, 'get_profile_manager', return_value=profile_manager),
            patch('pydoll.browser.Chrome', FailingChrome),
        ):
            result = await browser_tools.browser_launch(
                'client', profile_mode='temporary',
                proxy_server='http://user:secret@proxy.example:8080',
            )
        assert result['error_code'] == 'INTERNAL_ERROR'
        assert 'secret' not in str(result)
        assert 'user:' not in str(result)
        assert 'http://proxy.example:8080' in str(result)

    asyncio.run(run())


def _awaitable(value: str):
    async def result() -> str:
        return value

    return result()
