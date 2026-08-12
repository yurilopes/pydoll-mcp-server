"""Browser lifecycle tools: launch, list, close."""

from __future__ import annotations

import asyncio
from typing import Annotated

from pydantic import Field
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import browser_operation_lock, get_lock_manager
from pydoll_mcp_server.browser.models import ProfileInfo, ProfileMode
from pydoll_mcp_server.browser.process_supervisor import ManagedBrowserProcessManager
from pydoll_mcp_server.browser.profile_index import get_profile_index
from pydoll_mcp_server.browser.profile_leases import (
    ProfileLease,
)
from pydoll_mcp_server.browser.profile_leases import (
    get_profile_lease_manager as get_profile_lease_manager,
)
from pydoll_mcp_server.browser.profiles import get_profile_manager
from pydoll_mcp_server.browser.pydoll_compat import (
    create_chromium_options,
    get_browser_connection_port,
    get_browser_process_id,
    get_tab_target_id,
    get_tab_title,
    get_tab_url,
    install_browser_process_manager,
    stop_browser,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.tab_reconciliation import TabSyncResult, sync_browser_tabs
from pydoll_mcp_server.config import get_limits_config
from pydoll_mcp_server.errors import ErrorCode, ResourceState, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, normalize_json_value
from pydoll_mcp_server.logging import get_logger
from pydoll_mcp_server.recovery.health import check_browser_health
from pydoll_mcp_server.security.proxy import validate_proxy
from pydoll_mcp_server.tools.shutdown import shutdown_browsers

__all__ = ['shutdown_browsers']


async def browser_launch(
    client_id: str,
    headless: Annotated[bool, Field(description='Run without a visible window when true.')] = False,
    profile_mode: Annotated[
        str,
        Field(
            description='Use persistent to preserve login state or temporary for an isolated disposable profile.',
            json_schema_extra={'enum': ['persistent', 'temporary']},
        ),
    ] = 'persistent',
    profile_id: Annotated[
        str,
        Field(description='Explicit managed profile ID. Leave empty to reuse or create the client default.'),
    ] = '',
    proxy_server: Annotated[
        str,
        Field(description='Optional HTTP, HTTPS, SOCKS4, or SOCKS5 proxy URL.'),
    ] = '',
    proxy_bypass_list: Annotated[
        str,
        Field(description='Optional comma-separated hosts that bypass the proxy.'),
    ] = '',
    session_intent: Annotated[
        str,
        Field(description='Set user_authenticated when an existing logged-in profile should be reused.'),
    ] = '',
    site_hint: Annotated[
        str,
        Field(description='Site or domain hint used to match an authenticated persistent profile.'),
    ] = '',
) -> JsonObject:
    logger = get_logger()
    registry = get_registry()
    profile_mgr = get_profile_manager()
    profile_index = (
        get_profile_index() if (profile_id or (session_intent == 'user_authenticated' and site_hint)) else None
    )
    warnings: list[dict[str, str]] = []
    matched_profile_id_for_reuse: str = ''
    matched_client_for_reuse: str = ''
    proxy = None
    lease: ProfileLease | None = None
    browser = None
    browser_info = None

    if proxy_server:
        try:
            proxy = validate_proxy(proxy_server, proxy_bypass_list)
        except StructuredError as exc:
            return exc.to_dict()

    if session_intent == 'user_authenticated' and site_hint:
        assert profile_index is not None
        matched = profile_index.find_matching(client_id, site_hint, mode_filter='persistent')
        if len(matched) == 1:
            matched_profile_id_for_reuse = matched[0].profile_id
            matched_client_for_reuse = matched[0].owner_client_id
        elif len(matched) > 1:
            persistent_profile_ids: JsonArray = [m.profile_id for m in matched[:5]]
            persistent_details: JsonObject = {
                'hint': 'profile_list',
                'site_hint': site_hint,
                'count': len(matched),
                'candidate_profile_ids': persistent_profile_ids,
            }
            return StructuredError(
                ErrorCode.AMBIGUOUS_PROFILE,
                f'Multiple authenticated profiles match site_hint "{site_hint}". '
                'Use profile_list to inspect candidates, then pass an explicit profile_id.',
                details=persistent_details,
                retryable=True,
            ).to_dict()
        else:
            temp_matches = profile_index.find_matching(client_id, site_hint, mode_filter='temporary')
            if temp_matches:
                temporary_profile_ids: JsonArray = [m.profile_id for m in temp_matches[:3]]
                temporary_details: JsonObject = {
                    'recommended_action': 'profile_promote',
                    'candidate_profile_ids': temporary_profile_ids,
                    'site_hint': site_hint,
                }
                return StructuredError(
                    ErrorCode.AMBIGUOUS_PROFILE,
                    f'Temporary profile(s) exist for {site_hint} but are not persistent. '
                    'Call profile_promote to promote one, then retry with the resulting profile_id.',
                    details=temporary_details,
                    retryable=True,
                    recovery_hint='Choose a candidate profile_id and call profile_promote to make it persistent.',
                ).to_dict()
            warnings.append(
                {
                    'code': 'NO_AUTH_PROFILE',
                    'message': f'No authenticated profile found for {site_hint}. '
                    'A new persistent profile will be used. Login may be required.',
                }
            )

    if profile_mode == 'temporary' and site_hint and session_intent == 'user_authenticated':
        warnings.append(
            {
                'code': 'TEMPORARY_PROFILE_FOR_AUTH_SITE',
                'message': f'Temporary profile used for authenticated site {site_hint}. Login state will be lost.',
            }
        )

    if profile_mode == 'temporary':
        profile = profile_mgr.create_temporary(client_id)
    elif matched_profile_id_for_reuse:
        profile = profile_mgr.reuse_existing(matched_profile_id_for_reuse, matched_client_for_reuse)
    elif profile_id:
        assert profile_index is not None
        indexed_profile = profile_index.get(profile_id)
        if indexed_profile is not None and indexed_profile.owner_client_id != client_id:
            return StructuredError(
                ErrorCode.PERMISSION_DENIED,
                f'Profile {profile_id} belongs to another client',
                retryable=False,
            ).to_dict()
        # profile_list returns managed IDs. Reuse those IDs directly instead of
        # treating them as a new logical name and creating a nested profile.
        profile = (
            profile_mgr.reuse_existing(profile_id, client_id)
            if indexed_profile is not None
            else profile_mgr.create_named(client_id, profile_id)
        )
    else:
        profile = profile_mgr.get_or_create_default(client_id)

    existing = registry.find_by_profile(client_id, profile.profile_id)
    if existing is not None:
        if existing.headless != headless or existing.proxy_server != (proxy.sanitized_url if proxy else ''):
            return StructuredError(
                ErrorCode.RESOURCE_CONFLICT,
                f'Profile {profile.profile_id} is already open with incompatible browser settings.',
                details={'browser_id': existing.browser_id, 'profile_id': profile.profile_id},
                resource_state=ResourceState.HEALTHY,
                recovery_hint='Reuse the existing browser or call browser_close before changing settings.',
            ).to_dict()
        health = await check_browser_health(client_id, existing.browser_id)
        if health.get('healthy') is True:
            if hasattr(existing.pydoll_browser, 'get_opened_tabs'):
                async with browser_operation_lock(existing.browser_id):
                    await sync_browser_tabs(client_id, existing.browser_id)
            first_tab = next(iter(existing.tabs.values()), None)
            if first_tab is not None:
                return {
                    'success': True,
                    'reused': True,
                    'browser_id': existing.browser_id,
                    'tab_id': first_tab.tab_id,
                    'profile_id': profile.profile_id,
                    'profile_mode': profile.mode.value,
                    'headless': existing.headless,
                    'proxy_enabled': bool(existing.proxy_server),
                }
        return StructuredError(
            ErrorCode.RESOURCE_UNHEALTHY,
            'A browser already owns this profile but is not healthy.',
            details={'browser_id': existing.browser_id, 'health': existing.health.value},
            retryable=True,
            resource_state=ResourceState.DEGRADED,
            recovery_hint='Call browser_close and retry after the browser is removed.',
        ).to_dict()

    restart_metadata = get_profile_lease_manager().find_metadata(profile.profile_id, client_id)
    if restart_metadata is not None:
        from pydoll_mcp_server.tools.diagnostics import browser_attach

        recovered = await browser_attach(client_id, profile_id=profile.profile_id)
        if recovered.get('success'):
            recovered['reused'] = True
            recovered['recovery_source'] = 'profile_lease'
            return recovered
        if recovered.get('status') in {'profile_locked', 'requires_handoff'}:
            return recovered

    lease = get_profile_lease_manager().acquire(profile.path, client_id, profile.profile_id)
    if lease is None:
        return StructuredError(
            ErrorCode.RESOURCE_LOCKED,
            f'Profile {profile.profile_id} is already owned by another MCP process.',
            details={'profile_id': profile.profile_id},
            retryable=True,
            recovery_hint='Reuse the existing MCP session or wait for its browser to close.',
        ).to_dict()
    if not profile_mgr.lock(profile.profile_id, client_id):
        get_profile_lease_manager().release(lease)
        return StructuredError(
            ErrorCode.RESOURCE_LOCKED,
            f'Profile {profile.profile_id} is locked by another operation.',
            retryable=True,
        ).to_dict()

    try:
        options = create_chromium_options()
        options.add_argument(f'--user-data-dir={profile.path}')
        if proxy:
            options.add_argument(f'--proxy-server={proxy.launch_url}')
            if proxy.bypass_list:
                options.add_argument(f'--proxy-bypass-list={proxy.bypass_list}')
        options.headless = headless

        from pydoll.browser import Chrome

        browser = Chrome(options=options)
        install_browser_process_manager(browser, ManagedBrowserProcessManager())
        pydoll_tab = await asyncio.wait_for(browser.start(), timeout=60.0)
        browser_process_id = get_browser_process_id(browser)
        lease.write_metadata(browser_process_id, get_browser_connection_port(browser))

        url = await get_tab_url(pydoll_tab)
        title = await get_tab_title(pydoll_tab)

        browser_info = registry.register_browser(
            client_id=client_id,
            browser=browser,
            profile=profile,
            headless=headless,
            browser_process_id=browser_process_id,
            proxy_server=proxy.sanitized_url if proxy else '',
            proxy_launch_url=proxy.launch_url if proxy else '',
            proxy_scheme=proxy.scheme if proxy else '',
            proxy_has_credentials=proxy.has_credentials if proxy else False,
            proxy_bypass_list=proxy.bypass_list if proxy else '',
        )

        tab_info = registry.register_tab(
            client_id=client_id,
            browser_id=browser_info.browser_id,
            pydoll_tab=pydoll_tab,
            target_id=get_tab_target_id(pydoll_tab),
            url=url,
            title=title,
        )
        managed_browser = getattr(browser_info, 'pydoll_browser', browser)
        if hasattr(managed_browser, 'get_opened_tabs'):
            async with browser_operation_lock(browser_info.browser_id):
                await sync_browser_tabs(client_id, browser_info.browser_id)
        lease.write_metadata(
            browser_process_id,
            get_browser_connection_port(browser),
            [tab.target_id for tab in registry.list_tabs(client_id, browser_info.browser_id)],
            [tab.url for tab in registry.list_tabs(client_id, browser_info.browser_id)],
        )

        logger.info(f'Browser launched: {browser_info.browser_id} for client {client_id}')
        result: JsonObject = {
            'success': True,
            'reused': False,
            'browser_id': browser_info.browser_id,
            'tab_id': tab_info.tab_id,
            'profile_id': profile.profile_id,
            'profile_mode': profile.mode.value,
            'headless': headless,
            'proxy_enabled': bool(proxy),
            'proxy_server': proxy.sanitized_url if proxy else '',
            'proxy_scheme': proxy.scheme if proxy else '',
            'proxy_has_credentials': proxy.has_credentials if proxy else False,
        }
        if warnings:
            result['warnings'] = [{'code': warning['code'], 'message': warning['message']} for warning in warnings]
        return result
    except asyncio.TimeoutError:
        if browser is not None:
            try:
                await asyncio.wait_for(stop_browser(browser), timeout=15.0)
            except (AttributeError, PydollException, OSError, RuntimeError, asyncio.TimeoutError):
                logger.warning('Failed to stop browser after launch timeout')
            if browser_info is not None and hasattr(registry, 'remove_browser'):
                registry.remove_browser(client_id, browser_info.browser_id, cleanup_profile=False)
        profile_mgr.unlock(profile.profile_id)
        get_profile_lease_manager().release(lease)
        return StructuredError(
            error_code=ErrorCode.TIMEOUT,
            message='Browser launch timed out',
            retryable=True,
            recovery_hint='Check that Chrome/Chromium is installed and accessible.',
        ).to_dict()
    except Exception as e:
        if browser is not None:
            try:
                await asyncio.wait_for(stop_browser(browser), timeout=15.0)
            except (AttributeError, PydollException, OSError, RuntimeError, asyncio.TimeoutError):
                logger.warning('Failed to stop browser after launch failure')
            if browser_info is not None and hasattr(registry, 'remove_browser'):
                registry.remove_browser(client_id, browser_info.browser_id, cleanup_profile=False)
        profile_mgr.unlock(profile.profile_id)
        get_profile_lease_manager().release(lease)
        message = str(e)
        if proxy:
            message = message.replace(proxy.launch_url, proxy.sanitized_url)
        return StructuredError(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f'Failed to launch browser: {message}',
            retryable=True,
            details={'error': message},
        ).to_dict()


async def browser_list(client_id: str, include_health: bool = False) -> JsonObject:
    """List owned browsers and optionally probe their live CDP connection."""
    registry = get_registry()
    browsers = registry.list_browsers(client_id)
    summaries: list[JsonObject] = [b.summary() for b in browsers]
    sync_results: list[TabSyncResult] = []
    for summary, browser in zip(summaries, browsers, strict=True):
        try:
            async with browser_operation_lock(browser.browser_id):
                sync_results.append(await sync_browser_tabs(client_id, browser.browser_id))
        except StructuredError as exc:
            managed_count = len(browser.tabs)
            sync_results.append(
                TabSyncResult(
                    actual_count=managed_count,
                    managed_count=managed_count,
                    added=0,
                    removed=0,
                    stale=0,
                    reconciled=False,
                    last_sync_at=0.0,
                    sync_error=f'Live tab enumeration is unavailable: {exc.message}',
                )
            )
        summary.update(sync_results[-1].summary(get_limits_config().max_tabs_per_browser))
        summary['tabs'] = sync_results[-1].managed_count
        if isinstance(browser.profile, ProfileInfo):
            summary['lease_active'] = get_profile_lease_manager().is_held(browser.profile.path)
    if include_health:
        live_health = await asyncio.gather(
            *(check_browser_health(client_id, browser.browser_id) for browser in browsers)
        )
        for summary, health in zip(summaries, live_health, strict=True):
            summary['live_health'] = health
    return {
        'success': True,
        'browsers': [normalize_json_value(summary, 'browsers[]') for summary in summaries],
    }


async def browser_close(
    client_id: str,
    browser_id: str,
) -> JsonObject:
    registry = get_registry()
    logger = get_logger()
    profile_mgr = get_profile_manager()

    try:
        browser_info = registry.get_browser(client_id, browser_id)
    except StructuredError as e:
        return e.to_dict()

    try:
        pydoll_browser = browser_info.pydoll_browser
        if pydoll_browser:
            try:
                await asyncio.wait_for(stop_browser(pydoll_browser), timeout=15.0)
                # Chrome may release profile files shortly after its process stops on Windows.
                await asyncio.sleep(0.25)
            except asyncio.TimeoutError:
                logger.warning(f'Browser {browser_id} stop timed out, cleaning up registry')
            except (AttributeError, OSError, PydollException, RuntimeError) as exc:
                logger.error(f'Error stopping browser {browser_id}: {exc}')

        tabs_closed = list(browser_info.tabs.keys())
        profile = browser_info.profile
        profile_id = profile.profile_id if profile else ''
        cleanup_errors: JsonArray = []
        if profile:
            if profile.mode == ProfileMode.TEMPORARY:
                try:
                    await asyncio.to_thread(profile_mgr.cleanup_temporary, profile.profile_id)
                except OSError as exc:
                    # Browser ownership must be released even when Windows delays profile file cleanup.
                    profile_mgr.release(profile.profile_id)
                    cleanup_errors.append({'resource': 'temporary_profile', 'error': str(exc)})
            else:
                profile_mgr.unlock(profile.profile_id)
            get_profile_lease_manager().release_by_profile(profile.path)
        registry.remove_browser(client_id, browser_id, cleanup_profile=False)
        from pydoll_mcp_server.browser.inspection import get_inspection_manager

        for tab_id in tabs_closed:
            get_inspection_manager().remove(tab_id)
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
            'partial': bool(cleanup_errors),
            'cleanup_errors': cleanup_errors,
        }
    except Exception as exc:
        return StructuredError(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f'Error closing browser: {exc}',
            retryable=True,
        ).to_dict()
