"""Active surface observation for modal, dialog, form, and viewport scopes."""

from __future__ import annotations

import copy
import json
import time
from typing import Annotated

from pydantic import Field
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_object
from pydoll_mcp_server.dom.element_cache import cache_observed_element, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_bool,
    get_object,
    get_string,
    require_json_object,
)
from pydoll_mcp_server.security.site_signals import inspect_site_diagnostics
from pydoll_mcp_server.tools.form_contracts import v2_envelope
from pydoll_mcp_server.tools.form_presets import get_form_preset
from pydoll_mcp_server.tools.form_runtime import (
    SurfaceCacheKey,
    get_cached_deep,
    get_cached_surface,
    store_cached_deep,
    store_cached_surface,
)
from pydoll_mcp_server.tools.surface_scripts import surface_script

VALID_SCOPES = frozenset({'auto', 'modal', 'dialog', 'form', 'main', 'viewport', 'active_element_context'})


async def page_get_active_surface(
    client_id: str,
    tab_id: str,
    scope: Annotated[
        str,
        Field(
            description='Surface scope: auto, modal, dialog, form, main, viewport, or active_element_context.',
            json_schema_extra={
                'enum': ['auto', 'modal', 'dialog', 'form', 'main', 'viewport', 'active_element_context']
            },
        ),
    ] = 'auto',
    max_fields: Annotated[int, Field(description='Maximum form fields to inspect.')] = 100,
    max_controls: Annotated[int, Field(description='Maximum actionable controls to inspect.')] = 120,
    include_values: Annotated[bool, Field(description='Include current input values when true.')] = False,
    text_max_chars: Annotated[int, Field(description='Maximum text excerpt length for surface labels.')] = 300,
    include_diagnostics: Annotated[
        bool,
        Field(description='Include the broad passive diagnostics scan. Disable for focused workflow probes.'),
    ] = True,
    use_cache: Annotated[
        bool,
        Field(description='Reuse a surface snapshot while document and mutation versions are unchanged.'),
    ] = True,
    preset: Annotated[str, Field(description='Semantic workflow preset used for snapshot isolation.')] = 'generic_form',
    diagnostic_mode: Annotated[
        str,
        Field(
            description='Diagnostic depth: compact for workflow probes or full for explicit diagnostics.',
            json_schema_extra={'enum': ['compact', 'full']},
        ),
    ] = 'compact',
    include_shadow: Annotated[
        bool,
        Field(description='Traverse open shadow roots only when the compact surface indicates they may matter.'),
    ] = True,
) -> JsonObject:
    if scope not in VALID_SCOPES:
        return StructuredError(
            ErrorCode.INVALID_INPUT, f'Unsupported scope: {scope}. Use: {", ".join(sorted(VALID_SCOPES))}'
        ).to_dict()
    if diagnostic_mode not in {'compact', 'full'}:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'Unsupported diagnostic_mode. Use compact or full.',
        ).to_dict()
    preset_config = get_form_preset(preset)
    if preset_config is None:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            f'Unsupported preset: {preset}. Use generic_form, linkedin_easy_apply, or external_ats_multistep.',
        ).to_dict()

    safe_max_fields = max(1, min(max_fields, 500))
    safe_max_controls = max(1, min(max_controls, 500))
    safe_text_max_chars = max(50, min(text_max_chars, 2000))

    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    generation = getattr(tab_info, 'document_generation', 0)
    safe_generation = generation if isinstance(generation, int) and not isinstance(generation, bool) else 0
    mutation = getattr(tab_info, 'mutation_epoch', 0)
    safe_mutation = mutation if isinstance(mutation, int) and not isinstance(mutation, bool) else 0
    key = SurfaceCacheKey(
        client_id=client_id,
        tab_id=tab_id,
        connection_identity=id(getattr(tab_info, 'pydoll_tab', None)),
        document_generation=safe_generation,
        mutation_epoch=safe_mutation,
        scope=scope,
        preset=preset,
        include_values=include_values,
        include_diagnostics=include_diagnostics,
        diagnostic_mode=diagnostic_mode,
        include_shadow=include_shadow,
        max_fields=safe_max_fields,
        max_controls=safe_max_controls,
        text_max_chars=safe_text_max_chars,
    )
    if use_cache:
        cached = get_cached_surface(key)
        if cached is not None:
            response = copy.deepcopy(cached.snapshot)
            response['cache_hit'] = True
            response['document_generation'] = key.document_generation
            response['mutation_epoch'] = key.mutation_epoch
            return response

    diagnostics = (
        await inspect_site_diagnostics(tab_info.pydoll_tab, scope, compact=diagnostic_mode != 'full')
        if include_diagnostics
        else _empty_diagnostics(scope)
    )

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
        data = extract_normalized_object(result, 'page_get_active_surface')
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Active surface failed: {exc}',
            retryable=True,
        ).to_dict()

    response = _build_response(
        client_id, tab_id, tab_info.document_generation, data, scope, safe_max_fields, safe_max_controls
    )
    response['security_controls'] = get_array(diagnostics, 'security_controls', [])
    response['site_diagnostics'] = diagnostics
    response['cache_hit'] = False
    response['document_generation'] = safe_generation
    response['mutation_epoch'] = key.mutation_epoch
    if include_shadow and preset_config.deep_on_shadow and _needs_shadow_discovery(response, diagnostics):
        from pydoll_mcp_server.dom.deep_traversal import page_get_tree_deep
        from pydoll_mcp_server.tools.form_deep_surface import enrich_surface_from_deep

        deep = get_cached_deep(key)
        if deep is None:
            deep = await page_get_tree_deep(
                client_id,
                tab_id,
                max_nodes=1500,
                timeout=8.0,
                include_shadow=True,
                include_iframes=True,
            )
            if get_bool(deep, 'success', False):
                store_cached_deep(key, deep)
        if get_bool(deep, 'success', False):
            response = enrich_surface_from_deep(response, deep)
            response['deep_discovery'] = {
                'used': True,
                'success': True,
                'partial': get_bool(deep, 'partial', False),
                'count': len(get_array(deep, 'elements', [])),
                'errors': get_array(deep, 'errors', []),
            }
        else:
            response['partial'] = True
            response['deep_discovery'] = {
                'used': True,
                'success': False,
                'partial': True,
                'count': 0,
                'errors': get_array(deep, 'errors', []),
            }
            warnings = get_array(response, 'warnings', [])
            warnings.append(
                {
                    'kind': 'shadow_discovery',
                    'message': 'Open shadow-root discovery was inconclusive; scoped actions require re-resolution.',
                }
            )
            response['warnings'] = warnings
    else:
        response['deep_discovery'] = {'used': False, 'success': True, 'partial': False, 'count': 0, 'errors': []}
    if use_cache:
        store_cached_surface(key, response, '')
    return response


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

    result: JsonObject = v2_envelope('page_get_active_surface', 'verified')
    result.update(
        {
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
    )
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
    return cache_observed_element(get_element_cache(), tab_id, generation, field)


def _cache_control_entry(client_id: str, tab_id: str, generation: int, control: JsonObject) -> str:
    return cache_observed_element(get_element_cache(), tab_id, generation, control)


def _empty_diagnostics(scope: str) -> JsonObject:
    return {
        'framework_hints': [],
        'security_controls': [],
        'validation_state': {},
        'active_surface': scope,
        'diagnostics_unavailable': False,
        'diagnostics_skipped': True,
    }


def _needs_shadow_discovery(surface: JsonObject, diagnostics: JsonObject) -> bool:
    hints = {item for item in get_array(diagnostics, 'framework_hints', []) if isinstance(item, str)}
    if 'open_shadow_root' in hints:
        return True
    return 'custom_elements' in hints and not get_array(surface, 'fields', [])
