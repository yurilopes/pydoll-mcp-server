"""Browser lifecycle tools: launch, list, close."""

from __future__ import annotations

import asyncio

from pydoll_mcp_server.browser.locks import get_lock_manager
from pydoll_mcp_server.browser.models import ProfileMode
from pydoll_mcp_server.browser.profile_index import get_profile_index
from pydoll_mcp_server.browser.profiles import get_profile_manager
from pydoll_mcp_server.browser.pydoll_compat import (
    create_chromium_options,
    get_tab_title,
    get_tab_url,
    stop_browser,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, ResourceState, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject
from pydoll_mcp_server.logging import get_logger
from pydoll_mcp_server.security.proxy import validate_proxy


async def browser_launch(
    client_id: str,
    headless: bool = False,
    profile_mode: str = 'persistent',
    profile_id: str = '',
    proxy_server: str = '',
    proxy_bypass_list: str = '',
    session_intent: str = '',
    site_hint: str = '',
) -> JsonObject:
    logger = get_logger()
    registry = get_registry()
    profile_mgr = get_profile_manager()
    profile_index = get_profile_index()
    warnings: list[dict[str, object]] = []
    matched_profile_id_for_reuse: str = ''
    matched_client_for_reuse: str = ''
    proxy = None

    if proxy_server:
        try:
            proxy = validate_proxy(proxy_server, proxy_bypass_list)
        except StructuredError as exc:
            return exc.to_dict()

    if session_intent == 'user_authenticated' and site_hint:
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
        if not profile_mgr.lock(profile.profile_id, matched_client_for_reuse):
            return StructuredError(
                error_code=ErrorCode.RESOURCE_LOCKED,
                message=f'Profile {profile.profile_id} is locked by another client',
                retryable=True,
                resource_state=ResourceState.UNKNOWN,
                recovery_hint=('Wait for the other client to release the profile or use a different profile_id.'),
            ).to_dict()
    elif profile_id:
        profile = profile_mgr.create_named(client_id, profile_id)
        if not profile_mgr.lock(profile.profile_id, client_id):
            return StructuredError(
                error_code=ErrorCode.RESOURCE_LOCKED,
                message=f'Profile {profile_id} is locked by another client',
                retryable=True,
                resource_state=ResourceState.UNKNOWN,
                recovery_hint=('Wait for the other client to release the profile or use a different profile_id.'),
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

        options = create_chromium_options()
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

        logger.info(f'Browser launched: {browser_info.browser_id} for client {client_id}')
        result: JsonObject = {
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
        if warnings:
            result['warnings'] = [
                {'code': str(w.get('code', '')), 'message': str(w.get('message', ''))} for w in warnings
            ]
        return result
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


async def browser_list(client_id: str) -> JsonObject:
    registry = get_registry()
    browsers = registry.list_browsers(client_id)
    return {
        'success': True,
        'browsers': [b.summary() for b in browsers],
    }


async def proxy_get(client_id: str, browser_id: str) -> JsonObject:
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
            except Exception as exc:
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
        registry.remove_browser(client_id, browser_id, cleanup_profile=False)
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
