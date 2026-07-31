"""Generic upload orchestration for custom browser upload triggers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydoll.browser.tab import Tab
from pydoll.exceptions import PydollException
from pydoll.protocol.page.events import PageEvent

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.native_file_picker import (
    BrowserIdentity,
    native_picker_dialog_present,
    native_picker_is_available,
    select_native_file,
)
from pydoll_mcp_server.browser.native_file_picker_focus import focus_native_browser_window
from pydoll_mcp_server.browser.pydoll_compat import (
    bring_tab_to_front,
    disable_intercept_file_chooser_dialog,
    disable_page_events,
    enable_intercept_file_chooser_dialog,
    enable_page_events,
    register_runtime_callback,
    remove_tab_callback,
    set_input_files_by_backend_node,
)
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_bool,
    get_object,
    get_string,
    require_json_object,
)
from pydoll_mcp_server.security.upload_policy import UploadPathError
from pydoll_mcp_server.tools.element_resolver import resolve_element
from pydoll_mcp_server.tools.upload_paths import NativePickerUpload, prepare_native_picker_upload
from pydoll_mcp_server.tools.upload_trigger_helpers import (
    PickerStrategy,
    direct_input_available,
    finish_upload_result,
    set_strategy_requested,
    set_surface_diagnostics,
    should_try_desktop_fallback,
    upload_direct_input,
    validate_upload_paths,
)
from pydoll_mcp_server.tools.upload_trigger_scripts import (
    UploadTriggerElement,
    inspect_upload_surface,
)


@dataclass
class ChooserObservation:
    """State collected from one temporary Page.fileChooserOpened listener."""

    event_seen: bool = False
    backend_node_id: int | None = None
    error_reason: str = ''
    completed: asyncio.Event = field(default_factory=asyncio.Event)


@asynccontextmanager
async def _file_chooser_interceptor(tab: Tab, paths: list[str]) -> AsyncGenerator[ChooserObservation, None]:
    observation = ChooserObservation()
    page_events_were_enabled = tab.page_events_enabled
    interception_was_enabled = tab.intercept_file_chooser_dialog_enabled

    async def handle_event(raw_event: object) -> None:
        try:
            event = require_json_object(raw_event, 'file chooser event')
            params = get_object(event, 'params', {})
            observation.event_seen = True
            backend_node_id = params.get('backendNodeId')
            if isinstance(backend_node_id, int) and not isinstance(backend_node_id, bool):
                observation.backend_node_id = backend_node_id
                await set_input_files_by_backend_node(tab, backend_node_id, paths)
            else:
                observation.error_reason = 'file_system_access_picker'
        except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
            observation.error_reason = 'file_chooser_event_invalid'
        finally:
            observation.completed.set()

    callback_id: int | None = None
    try:
        if not page_events_were_enabled:
            await enable_page_events(tab)
        if not interception_was_enabled:
            await enable_intercept_file_chooser_dialog(tab)
        callback_id = await register_runtime_callback(tab, PageEvent.FILE_CHOOSER_OPENED.value, handle_event)
        yield observation
    finally:
        if callback_id is not None:
            with suppress(PydollException, OSError, TypeError, ValueError):
                await remove_tab_callback(tab, callback_id)
        if not interception_was_enabled and tab.intercept_file_chooser_dialog_enabled:
            with suppress(PydollException, OSError, TypeError, ValueError):
                await disable_intercept_file_chooser_dialog(tab)
        if not page_events_were_enabled and tab.page_events_enabled:
            with suppress(PydollException, OSError, TypeError, ValueError):
                await disable_page_events(tab)


async def upload_files_from_trigger(
    client_id: str,
    tab_id: str,
    trigger_element_id: Annotated[str, Field(description='Cached element that starts the upload picker.')],
    paths: Annotated[list[str], Field(description='Permitted local file paths to upload.')],
    picker_strategy: Annotated[
        PickerStrategy,
        Field(
            description='Upload strategy: auto, intercept, or desktop.',
            json_schema_extra={'enum': ['auto', 'intercept', 'desktop']},
        ),
    ] = 'auto',
    expected_filenames: Annotated[
        list[str] | None, Field(description='Filenames expected to become visible after the upload.')
    ] = None,
    timeout_ms: Annotated[
        int, Field(description='Maximum time for picker interaction and upload verification.')
    ] = 30000,
) -> JsonObject:
    """Upload files through a custom trigger using browser or local native picker automation."""

    if picker_strategy not in {'auto', 'intercept', 'desktop'}:
        return StructuredError(ErrorCode.INVALID_INPUT, f'Unknown picker strategy: {picker_strategy}').to_dict()
    if not trigger_element_id:
        return StructuredError(ErrorCode.INVALID_INPUT, 'trigger_element_id is required').to_dict()
    if not paths:
        return StructuredError(ErrorCode.INVALID_INPUT, 'At least one upload path is required').to_dict()

    path_error = validate_upload_paths(paths)
    if path_error is not None:
        return path_error
    if picker_strategy == 'desktop' and len(paths) != 1:
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            'The Windows native picker fallback supports one file per operation',
            details={'reason': 'native_picker_multiple_files_unsupported'},
            retryable=False,
        ).to_dict()

    try:
        tab_info, browser_info = get_registry().resolve_tab_with_browser(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    expected = expected_filenames or [Path(path).name for path in paths]
    timeout_ms = max(1, timeout_ms)
    try:
        async with tab_operation_lock(tab_id):
            trigger = await resolve_element(tab_info, trigger_element_id)
            if trigger is None:
                return StructuredError(
                    ErrorCode.STALE_ELEMENT,
                    f'Element {trigger_element_id} is stale or not found',
                    retryable=False,
                ).to_dict()
            surface = await inspect_upload_surface(trigger)
            if picker_strategy == 'auto' and direct_input_available(surface):
                result = await upload_direct_input(
                    client_id,
                    tab_id,
                    trigger_element_id,
                    surface,
                    paths,
                    timeout_ms,
                    picker_strategy,
                )
                set_surface_diagnostics(result, surface)
                if get_bool(result, 'success'):
                    return await finish_upload_result(trigger, result, expected, timeout_ms)
                # Auto mode treats a direct-input failure as a strategy failure,
                # then continues to chooser interception before native fallback.

            attempts: JsonArray = []
            if picker_strategy in {'auto', 'intercept'}:
                intercept_result = await upload_with_intercept(
                    tab_info.pydoll_tab,
                    trigger,
                    paths,
                    timeout_ms,
                    picker_strategy,
                )
                set_strategy_requested(intercept_result, picker_strategy)
                set_surface_diagnostics(intercept_result, surface)
                attempts.append(intercept_result)
                if get_bool(intercept_result, 'success'):
                    return await finish_upload_result(trigger, intercept_result, expected, timeout_ms)
                if picker_strategy == 'intercept':
                    intercept_result['strategy_attempts'] = attempts
                    return intercept_result
                if not should_try_desktop_fallback(intercept_result):
                    return intercept_result

            native_stage: NativePickerUpload | None = None
            try:
                picker_path = paths[0]
                if native_picker_is_available(browser_info):
                    native_stage = await prepare_native_picker_upload(paths[0])
                    picker_path = str(native_stage.picker_path)
                desktop_result = await upload_with_desktop(
                    tab_info.pydoll_tab,
                    browser_info,
                    trigger,
                    picker_path,
                    timeout_ms,
                    picker_strategy,
                )
                set_strategy_requested(desktop_result, picker_strategy)
                set_surface_diagnostics(desktop_result, surface)
                if native_stage is not None:
                    desktop_result['source_path'] = native_stage.source.requested_path
                    desktop_result['native_picker_staged'] = native_stage.staged
                attempts.append(dict(desktop_result))
                if get_bool(desktop_result, 'success'):
                    result = await finish_upload_result(trigger, desktop_result, expected, timeout_ms)
                    result['strategy_attempts'] = attempts
                    return result
                desktop_result['strategy_attempts'] = attempts
                return desktop_result
            finally:
                if native_stage is not None:
                    await native_stage.cleanup()
    except UploadPathError as exc:
        return exc.to_dict()
    except (PydollException, InvalidScriptResponseError, KeyError, OSError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Upload through trigger failed: {exc}',
            retryable=True,
        ).to_dict()


async def upload_with_intercept(
    tab: Tab,
    trigger: UploadTriggerElement,
    paths: list[str],
    timeout_ms: int,
    strategy_requested: PickerStrategy = 'intercept',
) -> JsonObject:
    started = time.monotonic()
    try:
        async with _file_chooser_interceptor(tab, paths) as observation:
            click = await _click_trigger(trigger)
            if not get_bool(click, 'success'):
                return click
            remaining = max(0.05, timeout_ms / 1000 - (time.monotonic() - started))
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(observation.completed.wait(), timeout=min(1.5, remaining))
    except (PydollException, OSError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'File chooser interception failed: {exc}',
            details={'reason': 'file_chooser_interception_error'},
            retryable=True,
        ).to_dict()

    if not observation.event_seen:
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            'The upload trigger did not produce a compatible file chooser event',
            details={
                'reason': 'file_system_access_picker',
                'file_chooser_event_seen': False,
                'native_dialog_used': False,
            },
            retryable=True,
        ).to_dict()
    if observation.backend_node_id is None:
        return StructuredError(
            ErrorCode.UNSUPPORTED,
            'The upload trigger opened a picker without an input[type=file] node',
            details={
                'reason': observation.error_reason or 'file_system_access_picker',
                'file_chooser_event_seen': True,
                'backend_node_id_available': False,
                'native_dialog_used': False,
            },
            retryable=True,
        ).to_dict()
    if observation.error_reason:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            'The file chooser event could not receive the selected file',
            details={'reason': observation.error_reason},
            retryable=True,
        ).to_dict()
    return {
        'success': True,
        'uploaded': True,
        'strategy_requested': strategy_requested,
        'strategy_used': 'chooser_intercept',
        'file_input_detected': True,
        'file_chooser_event_seen': True,
        'native_dialog_used': False,
    }


async def upload_with_desktop(
    tab: Tab,
    browser: BrowserIdentity,
    trigger: UploadTriggerElement,
    path: str,
    timeout_ms: int,
    strategy_requested: PickerStrategy = 'desktop',
) -> JsonObject:
    if not native_picker_is_available(browser):
        return await select_native_file(browser, path, timeout_ms=timeout_ms)
    await bring_tab_to_front(tab)
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    attempt_budget = max(1000, timeout_ms // 2)
    last_result: JsonObject = {}
    for attempt in range(2):
        remaining = max(1, int((deadline - time.monotonic()) * 1000))
        dialog_is_open = await native_picker_dialog_present(browser, timeout_ms=min(250, remaining))
        if not dialog_is_open:
            focus = await focus_native_browser_window(browser, timeout_ms=min(remaining, 5000))
            if not get_bool(focus, 'success'):
                return focus
            click = await _click_trigger(trigger)
            if not get_bool(click, 'success'):
                return click
        native = await select_native_file(
            browser,
            path,
            timeout_ms=min(remaining, attempt_budget if attempt == 0 else remaining),
        )
        last_result = native
        if get_bool(native, 'success'):
            native['uploaded'] = True
            native['strategy_requested'] = strategy_requested
            native['strategy_used'] = 'desktop_picker'
            native['file_input_detected'] = False
            native['file_chooser_event_seen'] = False
            native['native_picker_attempts'] = attempt + 1
            return native
        details = get_object(native, 'details', {})
        if get_string(details, 'reason') != 'native_picker_timeout' or attempt == 1:
            return native
    return last_result


async def _click_trigger(trigger: UploadTriggerElement) -> JsonObject:
    await trigger.execute_script("this.scrollIntoView({block:'center'}); return true;", return_by_value=True)
    await trigger.click()
    return {'success': True, 'clicked': True}


__all__ = ['upload_files_from_trigger']
