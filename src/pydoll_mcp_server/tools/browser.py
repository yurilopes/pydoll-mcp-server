"""Browser lifecycle tools: launch, list, close."""

from __future__ import annotations

import asyncio
from typing import Any

from pydoll_mcp_server.browser.locks import get_lock_manager
from pydoll_mcp_server.browser.profiles import get_profile_manager
from pydoll_mcp_server.browser.pydoll_compat import get_tab_title, get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, ResourceState, StructuredError
from pydoll_mcp_server.logging import get_logger
from pydoll_mcp_server.security.proxy import validate_proxy


async def browser_launch(
    client_id: str,
    headless: bool = False,
    profile_mode: str = 'persistent',
    profile_id: str = '',
    proxy_server: str = '',
    proxy_bypass_list: str = '',
) -> dict[str, Any]:
    logger = get_logger()
    registry = get_registry()
    profile_mgr = get_profile_manager()
    proxy = None
    if proxy_server:
        try:
            proxy = validate_proxy(proxy_server, proxy_bypass_list)
        except StructuredError as exc:
            return exc.to_dict()

    if profile_mode == 'temporary':
        profile = profile_mgr.create_temporary(client_id)
    elif profile_id:
        profile = profile_mgr.create_named(client_id, profile_id)
        if not profile_mgr.lock(profile.profile_id, client_id):
            return StructuredError(
                error_code=ErrorCode.RESOURCE_LOCKED,
                message=f'Profile {profile_id} is locked by another client',
                retryable=True,
                resource_state=ResourceState.UNKNOWN,
                recovery_hint=(
                    'Wait for the other client to release the profile '
                    'or use a different profile_id.'
                ),
            ).to_dict()
    else:
        profile = profile_mgr.get_or_create_default(client_id)
        if not profile_mgr.lock(profile.profile_id, client_id):
            return StructuredError(
                error_code=ErrorCode.RESOURCE_LOCKED,
                message=f'Default profile for {client_id} is locked by another client',
                retryable=True,
                resource_state=ResourceState.UNKNOWN,
                recovery_hint='Wait for the lock to be released.',
            ).to_dict()

    try:
        from pydoll.browser import Chrome
        from pydoll.browser.options import ChromiumOptions

        options = ChromiumOptions()
        options.add_argument(f'--user-data-dir={profile.path}')
        if proxy:
            options.add_argument(f'--proxy-server={proxy.launch_url}')
            if proxy.bypass_list:
                options.add_argument(f'--proxy-bypass-list={proxy.bypass_list}')
        options.headless = headless

        browser = Chrome(options=options)
        pydoll_tab = await asyncio.wait_for(browser.start(), timeout=60.0)

        url = await get_tab_url(pydoll_tab)
        title = await get_tab_title(pydoll_tab)

        browser_info = registry.register_browser(
            client_id=client_id,
            browser=browser,
            profile=profile,
            headless=headless,
            proxy_server=proxy.sanitized_url if proxy else '',
            proxy_scheme=proxy.scheme if proxy else '',
            proxy_has_credentials=proxy.has_credentials if proxy else False,
            proxy_bypass_list=proxy.bypass_list if proxy else '',
        )

        tab_info = registry.register_tab(
            client_id=client_id,
            browser_id=browser_info.browser_id,
            pydoll_tab=pydoll_tab,
            url=url,
            title=title,
        )

        logger.info(
            f'Browser launched: {browser_info.browser_id} for client {client_id}'
        )
        return {
            'success': True,
            'browser_id': browser_info.browser_id,
            'tab_id': tab_info.tab_id,
            'profile_mode': profile.mode.value,
            'headless': headless,
            'proxy_enabled': bool(proxy),
            'proxy_server': proxy.sanitized_url if proxy else '',
            'proxy_scheme': proxy.scheme if proxy else '',
            'proxy_has_credentials': proxy.has_credentials if proxy else False,
        }
    except asyncio.TimeoutError:
        profile_mgr.unlock(profile.profile_id)
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message='Browser launch timed out',
            retryable=True,
            recovery_hint='Check that Chrome/Chromium is installed and accessible.',
        ).to_dict()
    except Exception as e:
        profile_mgr.unlock(profile.profile_id)
        message = str(e)
        if proxy:
            message = message.replace(proxy.launch_url, proxy.sanitized_url)
        return StructuredError(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f'Failed to launch browser: {message}',
            retryable=True,
            details={'error': message},
        ).to_dict()


async def browser_list(client_id: str) -> dict[str, Any]:
    registry = get_registry()
    browsers = registry.list_browsers(client_id)
    return {
        'success': True,
        'browsers': [b.summary() for b in browsers],
    }


async def proxy_get(client_id: str, browser_id: str) -> dict[str, Any]:
    try:
        browser = get_registry().get_browser(client_id, browser_id)
    except StructuredError as exc:
        return exc.to_dict()
    return {
        'success': True,
        'browser_id': browser_id,
        'proxy_enabled': bool(browser.proxy_server),
        'proxy_server': browser.proxy_server,
        'proxy_scheme': browser.proxy_scheme,
        'proxy_has_credentials': browser.proxy_has_credentials,
        'proxy_bypass_list': browser.proxy_bypass_list,
    }


async def browser_close(
    client_id: str,
    browser_id: str,
) -> dict[str, Any]:
    registry = get_registry()
    logger = get_logger()

    try:
        browser_info = registry.get_browser(client_id, browser_id)
    except StructuredError as e:
        return e.to_dict()

    try:
        pydoll_browser = browser_info._pydoll_browser
        if pydoll_browser:
            try:
                await asyncio.wait_for(pydoll_browser.stop(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning(
                    f'Browser {browser_id} stop timed out, cleaning up registry'
                )
            except Exception as exc:
                logger.error(f'Error stopping browser {browser_id}: {exc}')

        tabs_closed = list(browser_info.tabs.keys())
        profile_id = browser_info.profile.profile_id if browser_info.profile else ''
        registry.remove_browser(client_id, browser_id)
        lock_manager = get_lock_manager()
        lock_manager.clear_browser(browser_id)
        for tab_id in tabs_closed:
            lock_manager.clear_tab(tab_id)
        if profile_id:
            lock_manager.clear_profile(profile_id)

        logger.info(f'Browser closed: {browser_id}')
        return {
            'success': True,
            'browser_id': browser_id,
            'tabs_closed': len(tabs_closed),
        }
    except Exception as exc:
        return StructuredError(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f'Error closing browser: {exc}',
            retryable=True,
        ).to_dict()
