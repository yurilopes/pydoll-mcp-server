"""Read-only semantic form discovery and blocker classification."""

from __future__ import annotations

import time

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_bool,
    get_int,
    get_object,
    get_string,
)
from pydoll_mcp_server.tools.active_surface import page_get_active_surface
from pydoll_mcp_server.tools.form_choice_discovery import discover_choice_states
from pydoll_mcp_server.tools.form_contracts import form_fingerprint, new_operation_id, v2_envelope
from pydoll_mcp_server.tools.form_deep_surface import enrich_surface_from_deep
from pydoll_mcp_server.tools.form_preflight_support import (
    choice_discovery_required as _choice_discovery_required,
)
from pydoll_mcp_server.tools.form_preflight_support import (
    choice_text as _choice_text,
)
from pydoll_mcp_server.tools.form_preflight_support import (
    deep_discovery_required as _deep_discovery_required,
)
from pydoll_mcp_server.tools.form_preflight_support import (
    json_array as _json_array,
)
from pydoll_mcp_server.tools.form_preflight_support import (
    json_object_list as _json_object_list,
)
from pydoll_mcp_server.tools.form_preflight_support import (
    match_choice_plan as _match_choice_plan,
)
from pydoll_mcp_server.tools.form_preflight_support import (
    merge_envelope as _merge_envelope,
)
from pydoll_mcp_server.tools.form_preflight_support import (
    nonblocking_discovery_errors as _nonblocking_discovery_errors,
)
from pydoll_mcp_server.tools.form_preflight_support import restricted_preflight as _restricted_preflight
from pydoll_mcp_server.tools.form_preflight_support import semantic_field_states as _semantic_field_states
from pydoll_mcp_server.tools.form_presets import get_form_preset
from pydoll_mcp_server.tools.form_runtime import (
    PerformanceSummary,
    cache_key,
    get_cached_deep,
    get_cached_preflight,
    store_cached_deep,
    store_cached_preflight,
)
from pydoll_mcp_server.tools.form_workflow_helpers import (
    active_domain_restriction,
    attestation_handoffs,
    collect_upload_states,
    covered_by_plans,
    normalize_employer_domain,
    pending_required,
    snapshot_as_surface,
    surface_disagreement,
)


async def form_preflight(
    client_id: str,
    tab_id: str,
    scope: str = 'auto',
    planned_fields: list[dict[str, object]] | None = None,
    planned_choices: list[dict[str, object]] | None = None,
    planned_comboboxes: list[dict[str, object]] | None = None,
    planned_uploads: list[dict[str, object]] | None = None,
    do_not_touch: list[str] | None = None,
    employer_domain: str = '',
    include_values: bool = False,
    preset: str = 'generic_form',
    force_refresh: bool = False,
) -> JsonObject:
    plans = _json_object_list(planned_fields or [])
    plans.extend(_json_object_list(planned_choices or []))
    plans.extend(_json_object_list(planned_comboboxes or []))
    plans.extend(_json_object_list(planned_uploads or []))
    protected = [item.casefold() for item in do_not_touch or [] if item.strip()]
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return _merge_envelope(exc.to_dict(), 'form_preflight', 'blocked', False)

    if get_form_preset(preset) is None:
        return _merge_envelope(
            StructuredError(
                ErrorCode.INVALID_INPUT,
                f'Unsupported preset: {preset}. Use generic_form, linkedin_easy_apply, or external_ats_multistep.',
            ).to_dict(),
            'form_preflight',
            'blocked',
            False,
        )

    metrics = PerformanceSummary()
    domain = normalize_employer_domain(employer_domain)
    restriction = active_domain_restriction(domain) if domain else None
    if restriction is not None:
        return _restricted_preflight(
            client_id,
            tab_id,
            domain,
            restriction.reason,
            tab_info.document_generation,
            getattr(tab_info, 'mutation_epoch', 0),
            preset,
            list(do_not_touch or []),
            metrics.to_json(),
        )

    cache_version = cache_key(
        client_id,
        tab_id,
        scope,
        preset,
        include_values,
        True,
        tab_info=tab_info,
    )
    cached_preflight = None
    if not force_refresh and not plans and not include_values:
        cached_preflight = get_cached_preflight(
            cache_version,
            do_not_touch or [],
            domain,
        )
    if cached_preflight is not None:
        metrics.cache_hits += 1
        cached_preflight['cache_hit'] = True
        cached_preflight['performance'] = metrics.to_json()
        return cached_preflight

    discovery_started = time.monotonic()
    surface = await page_get_active_surface(
        client_id,
        tab_id,
        scope=scope,
        include_values=include_values,
        preset=preset,
        use_cache=not force_refresh,
        include_shadow=False,
    )
    metrics.browser_call()
    if get_bool(surface, 'cache_hit', False):
        metrics.cache_hits += 1
    else:
        metrics.cache_misses += 1
        metrics.full_scans += 1
        metrics.browser_call(2)
    metrics.add_phase('discovery', discovery_started)
    discovery_errors: JsonArray = []
    from pydoll_mcp_server.dom.deep_traversal import page_get_tree_deep

    deep_required = _deep_discovery_required(surface, plans)
    deep: JsonObject | None = get_cached_deep(cache_version) if deep_required and not force_refresh else None
    if deep is None and deep_required:
        deep_started = time.monotonic()
        deep = await page_get_tree_deep(
            client_id,
            tab_id,
            # Long job descriptions and Workable application pages routinely exceed
            # the old 500-node cap before their form controls are reached. Keep
            # surface into a false partial-discovery blocker.
            max_nodes=2000,
            timeout=8.0,
            include_shadow=True,
            include_iframes=True,
        )
        metrics.browser_call()
        metrics.deep_scans += 1
        metrics.add_phase('discovery', deep_started)
        if get_bool(deep, 'success', False):
            store_cached_deep(cache_version, deep)
    if deep is None:
        deep = {
            'success': True,
            'partial': False,
            'elements': [],
            'frames': [],
            'errors': [],
            'timing_ms': 0.0,
            'skipped': True,
        }
    deep_discovery: JsonObject = {
        'success': bool(deep.get('success', False)),
        'partial': get_bool(deep, 'partial', False),
        'count': len(get_array(deep, 'elements', [])),
        'errors': get_array(deep, 'errors', []),
    }
    if not deep.get('success'):
        discovery_errors.append({'deep': deep.get('message', 'Deep discovery failed')})
    elif get_bool(deep, 'partial', False):
        discovery_errors.extend(get_array(deep, 'errors', []))
    source = surface
    if not surface.get('success'):
        from pydoll_mcp_server.tools.form_controls import form_snapshot

        snapshot = await form_snapshot(client_id, tab_id)
        if snapshot.get('success'):
            source = snapshot_as_surface(snapshot)
        else:
            discovery_errors.extend(
                [
                    {'surface': surface.get('message', 'active surface failed')},
                    {'snapshot': snapshot.get('message', 'form snapshot failed')},
                ]
            )
            return _merge_envelope(
                {
                    'error_code': ErrorCode.EXECUTION_ERROR.value,
                    'message': 'Form discovery failed on both active surface and snapshot.',
                    'errors': discovery_errors,
                    'partial': True,
                },
                'form_preflight',
                'inconclusive',
                False,
            )
    active_surface_partial = (
        get_bool(surface, 'partial', False)
        if get_bool(surface, 'success', False)
        else get_bool(source, 'partial', False)
    )
    source = enrich_surface_from_deep(source, deep)
    fields = _semantic_field_states(get_array(source, 'fields', []), include_values=include_values)
    source['fields'] = fields
    upload_states = await collect_upload_states(client_id, tab_id, fields)
    if upload_states:
        metrics.browser_call(len(upload_states))
    choice_surface = [*fields, *get_array(source, 'controls', [])]
    choice_discovery: JsonObject
    if _choice_discovery_required(choice_surface, _json_object_list(planned_choices or [])):
        choice_discovery = await discover_choice_states(client_id, tab_id, scope)
        metrics.browser_call()
    else:
        choice_discovery = {'success': True, 'choices': [], 'skipped': True}
    choices = get_array(choice_discovery, 'choices', [])
    pending_fields = pending_required(fields, protected)
    security_controls = get_array(source, 'security_controls', [])
    attestations = attestation_handoffs(fields, protected)
    primary = source.get('primary_action') if isinstance(source.get('primary_action'), dict) else {}
    errors = get_array(source, 'errors', [])
    warnings = get_array(source, 'warnings', [])
    if not choice_discovery.get('success'):
        warnings.append(
            {
                'kind': 'choice_discovery',
                'message': 'Semantic choice discovery failed; review the choice controls manually.',
                'error': choice_discovery.get('error', {}),
            }
        )
    from pydoll_mcp_server.tools.form_controls import form_errors

    validation_state = get_object(get_object(source, 'site_diagnostics', {}), 'validation_state', {})
    should_read_rendered_errors = bool(errors) or get_int(validation_state, 'invalid_count', 0) > 0
    rendered_errors: JsonObject = (
        await form_errors(client_id, tab_id)
        if should_read_rendered_errors
        else {'success': True, 'errors': [], 'skipped': True}
    )
    if should_read_rendered_errors:
        metrics.browser_call()
    if rendered_errors.get('success'):
        for item in get_array(rendered_errors, 'errors', []):
            if not isinstance(item, dict):
                continue
            errors.append(
                {
                    'kind': 'validation_error',
                    'field_key': get_string(item, 'field_key', ''),
                    'label': get_string(item, 'nearest_heading', '') or get_string(item, 'name', ''),
                    'selector_hint': get_string(item, 'selector_hint', ''),
                    'validity': get_string(item, 'validity', ''),
                    'errors': get_array(item, 'errors', []),
                }
            )
    else:
        warnings.append(
            {
                'kind': 'validation_observation',
                'message': rendered_errors.get('message', 'Rendered form error inspection failed.'),
            }
        )
    partial = active_surface_partial or get_bool(deep, 'partial', False) or bool(discovery_errors)
    blockers: JsonArray = []
    if security_controls:
        blockers.append({'kind': 'security_control', 'reason': 'requires_candidate_action'})
    if attestations:
        blockers.append({'kind': 'attestation', 'reason': 'requires_candidate_confirmation'})
    for item in pending_fields:
        blockers.append({'kind': 'required_field', 'field': item})
    protected_required = [
        item
        for item in fields
        if isinstance(item, dict)
        and get_bool(item, 'required', False)
        and any(marker in get_string(item, 'label', '').casefold() for marker in protected)
    ]
    if protected_required:
        blockers.append({'kind': 'do_not_touch_required', 'fields': _json_array(protected_required)})
    if not primary:
        blockers.append({'kind': 'primary_action', 'reason': 'not_found'})
    if errors:
        blockers.append({'kind': 'validation_error', 'fields': _json_array(errors)})
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        if get_bool(choice, 'required', False) and get_string(choice, 'selected_state', '') != 'selected':
            blockers.append(
                {
                    'kind': 'required_choice',
                    'field_label': get_string(choice, 'field_label', ''),
                    'reason': get_string(choice, 'blocker', 'missing_required_choice'),
                }
            )
    for plan in _json_object_list(planned_choices or []):
        expected = str(plan.get('option_label', '') or plan.get('option_text', ''))
        matched = _match_choice_plan(plan, choices)
        if matched is None:
            blockers.append(
                {
                    'kind': 'choice',
                    'reason': 'not_found',
                    'field_label': str(plan.get('field_label', '') or plan.get('field_key', '')),
                    'option_label': expected,
                }
            )
        elif _choice_text(get_string(matched, 'selected_label', '')) != _choice_text(expected):
            blockers.append(
                {
                    'kind': 'choice',
                    'reason': 'not_verified',
                    'field_label': get_string(matched, 'field_label', ''),
                    'expected_option': expected,
                    'selected_label': get_string(matched, 'selected_label', ''),
                }
            )
    if not fields:
        blockers.append(
            {
                'kind': 'form_surface',
                'reason': 'no_interactive_form_fields',
                'recommendation': 'Open or resolve the application form before preparing fields.',
            }
        )
    disagreement = surface_disagreement(fields, deep)
    discovery_status = get_string(disagreement, 'status', '')
    deep_partial_without_errors = (
        get_bool(deep, 'success', False)
        and get_bool(deep, 'partial', False)
        and not discovery_errors
        and discovery_status == 'consistent'
        and not active_surface_partial
    )
    if deep_partial_without_errors:
        warnings.append(
            {
                'kind': 'discovery_partial',
                'message': (
                    'Deep discovery reached its bounded node limit, but the active form surface '
                    'was internally consistent. Review the returned partial flag before submission.'
                ),
            }
        )
    nonblocking_discovery_errors = _nonblocking_discovery_errors(
        discovery_errors,
        disagreement,
        fields,
        surface,
    )
    if nonblocking_discovery_errors:
        warnings.append(
            {
                'kind': 'discovery_partial',
                'message': (
                    'An iframe discovery error was retained as evidence, but it does not cover the active '
                    'form surface or any frame-scoped field.'
                ),
                'errors': discovery_errors,
            }
        )
    discovery_blocked = (
        not get_bool(deep, 'success', False)
        or (bool(discovery_errors) and not nonblocking_discovery_errors)
        or active_surface_partial
        or discovery_status == 'disagreement'
    )
    if discovery_blocked:
        blockers.append(
            {
                'kind': 'discovery',
                'reason': 'partial_or_disputed_surface',
                'details': disagreement,
            }
        )
    missing_candidate_data = [
        item for item in pending_fields if isinstance(item, dict) and not covered_by_plans(item, plans)
    ]
    if missing_candidate_data:
        blockers.append({'kind': 'missing_candidate_data', 'fields': _json_array(missing_candidate_data)})
    fingerprint = form_fingerprint(fields, primary if isinstance(primary, dict) else {}, choices)
    result = v2_envelope('form_preflight', 'ready' if not blockers else 'blocked')
    surface_value = source.get('surface')
    surface_descriptor: JsonObject = surface_value if isinstance(surface_value, dict) else {}
    stage = get_string(source, 'stage', '') or get_string(surface_descriptor, 'scope', 'form')
    result.update(
        {
            'client_id': client_id,
            'tab_id': tab_id,
            'stage': stage,
            'fields': fields,
            'choices': choices,
            'choice_states': choices,
            'upload_states': upload_states,
            'pending_required': pending_fields,
            'missing_candidate_data': _json_array(missing_candidate_data),
            'security_controls': security_controls,
            'attestation_handoffs': attestations,
            'primary_action': primary if isinstance(primary, dict) else {},
            'blockers': blockers,
            'errors': errors,
            'warnings': warnings,
            'partial': partial or bool(discovery_errors),
            'discovery_errors': discovery_errors,
            'deep_discovery': deep_discovery,
            'surface_disagreement': disagreement,
            'form_fingerprint': fingerprint,
            'document_generation': tab_info.document_generation,
            'mutation_epoch': getattr(tab_info, 'mutation_epoch', 0),
            'snapshot_id': new_operation_id('snapshot'),
            'cache_hit': False,
            'preset': preset,
            'employer_domain': domain,
            'ready_for_submission': not blockers,
            'do_not_touch': list(do_not_touch or []),
            'performance': metrics.to_json(),
        }
    )
    if not force_refresh and not plans and not include_values:
        store_cached_preflight(cache_version, do_not_touch or [], domain, result)
    return result
