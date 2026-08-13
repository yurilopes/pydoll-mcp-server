"""Read-only semantic form discovery and blocker classification."""

from __future__ import annotations

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_bool,
    get_string,
    normalize_json_value,
)
from pydoll_mcp_server.tools.active_surface import page_get_active_surface
from pydoll_mcp_server.tools.form_contracts import form_fingerprint, v2_envelope
from pydoll_mcp_server.tools.form_deep_surface import enrich_surface_from_deep
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

    surface = await page_get_active_surface(client_id, tab_id, scope=scope, include_values=include_values)
    discovery_errors: JsonArray = []
    from pydoll_mcp_server.dom.deep_traversal import page_get_tree_deep

    deep = await page_get_tree_deep(
        client_id,
        tab_id,
        # Long job descriptions and Workable application pages routinely exceed
        # the old 500-node cap before their form controls are reached. Keep
        # the deep pass bounded, but do not turn a complete active form
        # surface into a false partial-discovery blocker.
        max_nodes=2000,
        timeout=8.0,
        include_shadow=True,
        include_iframes=True,
    )
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

    source = enrich_surface_from_deep(source, deep)
    fields = get_array(source, 'fields', [])
    upload_states = await collect_upload_states(client_id, tab_id, fields)
    pending_fields = pending_required(fields, protected)
    security_controls = get_array(source, 'security_controls', [])
    attestations = attestation_handoffs(fields, protected)
    primary = source.get('primary_action') if isinstance(source.get('primary_action'), dict) else {}
    errors = get_array(source, 'errors', [])
    warnings = get_array(source, 'warnings', [])
    from pydoll_mcp_server.tools.form_controls import form_errors

    rendered_errors = await form_errors(client_id, tab_id)
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
    partial = get_bool(source, 'partial', False) or get_bool(deep, 'partial', False) or bool(discovery_errors)
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
        and not get_bool(source, 'partial', False)
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
    discovery_blocked = (
        not get_bool(deep, 'success', False)
        or bool(discovery_errors)
        or get_bool(source, 'partial', False)
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
    domain = normalize_employer_domain(employer_domain)
    restriction = active_domain_restriction(domain) if domain else None
    if restriction:
        blockers.append({'kind': 'domain_restriction', 'domain': domain, 'reason': restriction.reason})
    missing_candidate_data = [
        item for item in pending_fields if isinstance(item, dict) and not covered_by_plans(item, plans)
    ]
    if missing_candidate_data:
        blockers.append({'kind': 'missing_candidate_data', 'fields': _json_array(missing_candidate_data)})
    fingerprint = form_fingerprint(fields, primary if isinstance(primary, dict) else {})
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
            'employer_domain': domain,
            'ready_for_submission': not blockers,
            'do_not_touch': list(do_not_touch or []),
        }
    )
    return result


def _merge_envelope(value: JsonObject, operation: str, status: str, success: bool) -> JsonObject:
    result = dict(value)
    result.update(v2_envelope(operation, status, success))
    return result


def _json_object_list(value: object) -> list[JsonObject]:
    normalized_value = normalize_json_value(value, 'form plan list')
    if not isinstance(normalized_value, list):
        return []
    return [item for item in normalized_value if isinstance(item, dict)]


def _json_array(value: object) -> JsonArray:
    normalized = normalize_json_value(value, 'form result')
    return normalized if isinstance(normalized, list) else []


__all__ = ['form_preflight']
