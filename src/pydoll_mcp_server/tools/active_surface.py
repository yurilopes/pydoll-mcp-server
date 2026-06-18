"""Active surface observation for modal, dialog, form, and viewport scopes."""

from __future__ import annotations

import json
import time
import uuid

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_object, get_string, require_json_object
from pydoll_mcp_server.tools.surface_scripts import surface_script

VALID_SCOPES = frozenset({'auto', 'modal', 'dialog', 'form', 'main', 'viewport', 'active_element_context'})


async def page_get_active_surface(
    client_id: str,
    tab_id: str,
    scope: str = 'auto',
    max_fields: int = 100,
    max_controls: int = 120,
    include_values: bool = False,
    text_max_chars: int = 300,
) -> JsonObject:
    if scope not in VALID_SCOPES:
        return StructuredError(
            ErrorCode.INVALID_INPUT, f'Unsupported scope: {scope}. Use: {", ".join(sorted(VALID_SCOPES))}'
        ).to_dict()

    safe_max_fields = max(1, min(max_fields, 500))
    safe_max_controls = max(1, min(max_controls, 500))
    safe_text_max_chars = max(50, min(text_max_chars, 2000))

    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    payload = json.dumps(
        {
            'scope': scope,
            'max_fields': safe_max_fields,
            'max_controls': safe_max_controls,
            'include_values': include_values,
            'text_max_chars': safe_text_max_chars,
        }
    )

    try:
        result = await tab_info.pydoll_tab.execute_script(surface_script(payload), return_by_value=True)
        data = extract_script_object(result)
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Active surface failed: {exc}',
            retryable=True,
        ).to_dict()

    return _build_response(
        client_id, tab_id, tab_info.document_generation, data, scope, safe_max_fields, safe_max_controls
    )


def _build_response(
    client_id: str,
    tab_id: str,
    generation: int,
    data: JsonObject,
    scope: str,
    max_fields: int,
    max_controls: int,
) -> JsonObject:
    surface_fields = deserialize_surface_fields(
        get_array(data, 'fields', []),
        client_id,
        tab_id,
        generation,
    )
    surface_controls = _deserialize_controls(
        get_array(data, 'controls', []),
        client_id,
        tab_id,
        generation,
    )
    surface_containers = _deserialize_controls(
        get_array(data, 'containers', []),
        client_id,
        tab_id,
        generation,
    )

    primary = get_object(data, 'primary_action', {})
    if primary:
        primary['element_id'] = _cache_control_entry(client_id, tab_id, generation, primary)

    secondary: JsonArray = []
    for item in get_array(data, 'secondary_actions', []):
        sec = require_json_object(item, 'secondary action')
        sec['element_id'] = _cache_control_entry(client_id, tab_id, generation, sec)
        secondary.append(sec)

    errors_data = get_array(data, 'errors', [])

    evidence: JsonObject = {
        'timestamp': time.time(),
        'scope': scope,
        'surface_label': get_string(data, 'surface_label', ''),
    }

    result: JsonObject = {
        'success': True,
        'surface': {
            'scope': get_string(data, 'surface_scope', scope),
            'reason': get_string(data, 'surface_reason', ''),
            'element_id': _cache_control_entry(
                client_id,
                tab_id,
                generation,
                {
                    'tag': get_string(data, 'surface_tag', ''),
                    'role': get_string(data, 'surface_role', ''),
                    'name': get_string(data, 'surface_label', ''),
                    'text': get_string(data, 'surface_label', ''),
                    'selector_hint': get_string(data, 'surface_selector', ''),
                },
            ),
            'role': get_string(data, 'surface_role', ''),
            'label': get_string(data, 'surface_label', ''),
        },
        'fields': surface_fields,
        'controls': surface_controls,
        'containers': surface_containers,
        'primary_action': primary,
        'secondary_actions': secondary,
        'progress': get_object(data, 'progress', {}),
        'errors': errors_data,
        'pending_required': get_array(data, 'pending_required', []),
        'review_text': get_array(data, 'review_text', []),
        'active_element': get_object(data, 'active_element', {}),
        'count': {
            'fields': len(surface_fields),
            'controls': len(surface_controls),
            'containers': len(surface_containers),
        },
        'partial': len(surface_fields) >= max_fields or len(surface_controls) >= max_controls,
        'warnings': get_array(data, 'warnings', []),
        'evidence': evidence,
    }
    return result


def deserialize_surface_fields(
    raw_fields: JsonArray,
    client_id: str,
    tab_id: str,
    generation: int,
) -> JsonArray:
    out: JsonArray = []
    for item in raw_fields:
        field = require_json_object(item, 'surface field')
        raw_options = get_array(field, 'options', [])
        if raw_options:
            options: JsonArray = []
            for raw_option in raw_options:
                option = require_json_object(raw_option, 'surface field option')
                option['element_id'] = _cache_field_entry(client_id, tab_id, generation, option)
                options.append(option)
            field['options'] = options
            field['element_id'] = ''
        else:
            field['element_id'] = _cache_field_entry(client_id, tab_id, generation, field)
        out.append(field)
    return out


def _deserialize_controls(
    raw_controls: JsonArray,
    client_id: str,
    tab_id: str,
    generation: int,
) -> JsonArray:
    out: JsonArray = []
    for item in raw_controls:
        control = require_json_object(item, 'surface control')
        control['element_id'] = _cache_control_entry(client_id, tab_id, generation, control)
        out.append(control)
    return out


def _cache_field_entry(client_id: str, tab_id: str, generation: int, field: JsonObject) -> str:
    element_id = f'el_{uuid.uuid4().hex[:12]}'
    cache = get_element_cache()
    cache.store(
        ElementCacheEntry(
            element_id=element_id,
            tab_id=tab_id,
            document_generation=generation,
            tag_name=get_string(field, 'tag', ''),
            text_summary=get_string(field, 'label', '')[:100],
            selector_hint=get_string(field, 'selector_hint', ''),
            xpath_hint=get_string(field, 'xpath_hint', ''),
        )
    )
    return element_id


def _cache_control_entry(client_id: str, tab_id: str, generation: int, control: JsonObject) -> str:
    element_id = f'el_{uuid.uuid4().hex[:12]}'
    cache = get_element_cache()
    cache.store(
        ElementCacheEntry(
            element_id=element_id,
            tab_id=tab_id,
            document_generation=generation,
            tag_name=get_string(control, 'tag', ''),
            text_summary=get_string(control, 'name', '')[:100],
            selector_hint=get_string(control, 'selector_hint', ''),
            xpath_hint=get_string(control, 'xpath_hint', ''),
        )
    )
    return element_id
