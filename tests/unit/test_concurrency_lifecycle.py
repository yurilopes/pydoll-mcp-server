"""Lifecycle concurrency tests split for the source line budget."""

import asyncio
from pathlib import Path

import pytest
from pydoll.browser import Chrome
from pydoll.browser.tab import Tab
from pytest import MonkeyPatch


class _CloseBrowser(Chrome):
    def __init__(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class _CloseTab(Tab):
    def __init__(self) -> None:
        pass


class LaunchTab:
    @property
    async def current_url(self) -> str:
        return 'about:blank'

    @property
    async def title(self) -> str:
        return ''


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_concurrent_launches_with_same_profile_are_locked(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from pydoll_mcp_server.browser.profiles import ProfileManager
        from pydoll_mcp_server.browser.registry import BrowserRegistry
        from pydoll_mcp_server.config import get_config
        from pydoll_mcp_server.tools import browser as browser_tools

        monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
        monkeypatch.setenv('PYDOLL_MCP_RUNTIME_DIR', str(tmp_path))
        get_config.cache_clear()

        profile_manager = ProfileManager()
        registry = BrowserRegistry()

        class FakeChrome:
            def __init__(self, options: object = None, **_: object) -> None:
                self.options = options

            async def start(self, headless: bool = False) -> LaunchTab:
                await asyncio.sleep(0.05)
                return LaunchTab()

            async def stop(self) -> None:
                pass

        monkeypatch.setattr(browser_tools, 'get_profile_manager', lambda: profile_manager)
        monkeypatch.setattr(browser_tools, 'get_registry', lambda: registry)
        monkeypatch.setattr('pydoll.browser.Chrome', FakeChrome)

        results = await asyncio.gather(
            browser_tools.browser_launch('client-lock', headless=True, profile_id='shared'),
            browser_tools.browser_launch('client-lock', headless=True, profile_id='shared'),
        )

        successes = [result for result in results if result.get('success') is True]
        locked = [result for result in results if result.get('error_code') == 'RESOURCE_LOCKED']
        assert len(successes) == 1
        assert len(locked) == 1

    @pytest.mark.asyncio
    async def test_browser_close_removes_temporary_profile_and_registry_state(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        import pydoll_mcp_server.browser.registry as registry_module
        from pydoll_mcp_server.browser.profiles import ProfileManager
        from pydoll_mcp_server.browser.registry import BrowserRegistry
        from pydoll_mcp_server.config import get_config
        from pydoll_mcp_server.tools import browser as browser_tools

        monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
        monkeypatch.setenv('PYDOLL_MCP_RUNTIME_DIR', str(tmp_path))
        get_config.cache_clear()

        profile_manager = ProfileManager()
        registry = BrowserRegistry()
        profile = profile_manager.create_temporary('cleanup-client')
        profile_path = Path(profile.path)
        browser_info = registry.register_browser(
            'cleanup-client',
            _CloseBrowser(),
            profile,
            headless=True,
        )
        registry.register_tab(
            'cleanup-client',
            browser_info.browser_id,
            _CloseTab(),
        )

        monkeypatch.setattr(browser_tools, 'get_registry', lambda: registry)
        monkeypatch.setattr(browser_tools, 'get_profile_manager', lambda: profile_manager)
        monkeypatch.setattr(registry_module, 'get_profile_manager', lambda: profile_manager)

        result = await browser_tools.browser_close(
            'cleanup-client',
            browser_info.browser_id,
        )

        assert result['success'] is True
        assert profile_manager.get(profile.profile_id) is None
        assert not profile_path.exists()
        assert registry.list_browsers('cleanup-client') == []

    @pytest.mark.asyncio
    async def test_second_launch_reuses_healthy_browser(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from pydoll_mcp_server.browser.profiles import ProfileManager
        from pydoll_mcp_server.browser.registry import BrowserRegistry
        from pydoll_mcp_server.config import get_config
        from pydoll_mcp_server.tools import browser as browser_tools

        monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
        monkeypatch.setenv('PYDOLL_MCP_RUNTIME_DIR', str(tmp_path))
        get_config.cache_clear()
        profile_manager = ProfileManager()
        registry = BrowserRegistry()
        starts = 0

        class ReusableChrome:
            def __init__(self, options: object = None, **_: object) -> None:
                pass

            async def start(self, headless: bool = False) -> LaunchTab:
                nonlocal starts
                starts += 1
                return LaunchTab()

            async def get_version(self) -> str:
                return 'test'

            async def stop(self) -> None:
                pass

        monkeypatch.setattr(browser_tools, 'get_profile_manager', lambda: profile_manager)
        monkeypatch.setattr(browser_tools, 'get_registry', lambda: registry)
        monkeypatch.setattr('pydoll_mcp_server.recovery.health.get_registry', lambda: registry)
        monkeypatch.setattr('pydoll.browser.Chrome', ReusableChrome)

        first = await browser_tools.browser_launch('reuse-client', headless=True, profile_id='shared')
        second = await browser_tools.browser_launch('reuse-client', headless=True, profile_id='shared')

        assert first['success'] is True
        assert second['success'] is True
        assert second['reused'] is True
        assert second['browser_id'] == first['browser_id']
        assert starts == 1

        await browser_tools.shutdown_browsers()

    @pytest.mark.asyncio
    async def test_launch_failure_stops_started_browser_and_releases_profile(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from pydoll_mcp_server.browser.profiles import ProfileManager
        from pydoll_mcp_server.browser.registry import BrowserRegistry
        from pydoll_mcp_server.config import get_config
        from pydoll_mcp_server.tools import browser as browser_tools

        monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
        monkeypatch.setenv('PYDOLL_MCP_RUNTIME_DIR', str(tmp_path))
        get_config.cache_clear()
        profile_manager = ProfileManager()
        registry = BrowserRegistry()
        stopped = False

        class FailingChrome:
            def __init__(self, options: object = None, **_: object) -> None:
                pass

            async def start(self, headless: bool = False) -> LaunchTab:
                return LaunchTab()

            async def stop(self) -> None:
                nonlocal stopped
                stopped = True

        async def fail_url(tab: object) -> str:
            raise RuntimeError('url failed')

        monkeypatch.setattr(browser_tools, 'get_profile_manager', lambda: profile_manager)
        monkeypatch.setattr(browser_tools, 'get_registry', lambda: registry)
        monkeypatch.setattr(browser_tools, 'get_tab_url', fail_url)
        monkeypatch.setattr('pydoll.browser.Chrome', FailingChrome)

        result = await browser_tools.browser_launch('failure-client', headless=True, profile_id='shared')

        assert result['error_code'] == 'INTERNAL_ERROR'
        assert stopped is True
        assert registry.list_browsers('failure-client') == []
        assert profile_manager.is_locked('prof_failure-client_shared') is False
