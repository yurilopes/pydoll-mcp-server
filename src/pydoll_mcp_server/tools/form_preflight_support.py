"""Pure helpers for the semantic form preflight workflow."""

from __future__ import annotations

import unicodedata

from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_bool,
    get_object,
    get_string,
    normalize_json_value,
)
from pydoll_mcp_server.tools.form_contracts import new_operation_id, v2_envelope


def merge_envelope(value: JsonObject, operation: str, status: str, success: bool) -> JsonObject:
    result = dict(value)
    result.update(v2_envelope(operation, status, success))
    return result


def restricted_preflight(
    client_id: str,
    tab_id: str,
    domain: str,
    reason: str,
    document_generation: int,
    mutation_epoch: int,
    preset: str,
    do_not_touch: list[str],
    performance: JsonObject,
) -> JsonObject:
    result = v2_envelope('form_preflight', 'blocked')
    result.update(
        {
            'client_id': client_id,
            'tab_id': tab_id,
            'stage': 'unknown',
            'fields': [],
            'choices': [],
            'choice_states': [],
            'upload_states': [],
            'pending_required': [],
            'missing_candidate_data': [],
            'security_controls': [],
            'attestation_handoffs': [],
            'primary_action': {},
            'blockers': [{'kind': 'domain_restriction', 'domain': domain, 'reason': reason}],
            'errors': [],
            'warnings': [],
            'partial': False,
            'discovery_errors': [],
            'discovery_skipped': 'domain_restriction',
            'form_fingerprint': '',
            'document_generation': document_generation,
            'mutation_epoch': mutation_epoch,
            'snapshot_id': new_operation_id('snapshot'),
            'cache_hit': False,
            'preset': preset,
            'employer_domain': domain,
            'ready_for_submission': False,
            'do_not_touch': list(do_not_touch),
            'performance': performance,
        }
    )
    return result


def json_object_list(value: object) -> list[JsonObject]:
    normalized_value = normalize_json_value(value, 'form plan list')
    if not isinstance(normalized_value, list):
        return []
    return [item for item in normalized_value if isinstance(item, dict)]


def json_array(value: object) -> JsonArray:
    normalized = normalize_json_value(value, 'form result')
    return normalized if isinstance(normalized, list) else []


def semantic_field_states(fields: JsonArray, include_values: bool = False) -> JsonArray:
    """Add stable field-state keys without turning discovery into value collection."""

    result: JsonArray = []
    for value in fields:
        if not isinstance(value, dict):
            continue
        field = dict(value)
        value_length = field.get('value_length', 0)
        has_value = get_bool(field, 'value_present', False) or (
            isinstance(value_length, int) and not isinstance(value_length, bool) and value_length > 0
        )
        selected = get_string(field, 'selected', '')
        if not get_string(field, 'selected_label', '') and selected:
            field['selected_label'] = selected
        field.setdefault('validity', 'not_yet_validated')
        field.setdefault('errors', [])
        field.setdefault('framework_value', 'unknown')
        field.setdefault('framework_event', False)
        field.setdefault('controlled_value_survived', False)
        field.setdefault('blurred', False)
        field.setdefault('indeterminate', False)
        field.setdefault('verification', 'inconclusive')
        if include_values and not get_bool(field, 'redacted', False):
            field['dom_value'] = get_string(field, 'value_preview', '')
        else:
            field['dom_value'] = ''
        required = get_bool(field, 'required', False)
        enabled = get_bool(field, 'enabled', True) and not get_bool(field, 'read_only', False)
        selected_state = get_string(field, 'selected_state', '')
        if get_string(field, 'type', '').endswith('_group'):
            has_value = selected_state == 'selected' or get_bool(field, 'checked', False)
        ready = enabled and (not required or has_value)
        field.setdefault('ready_for_submission', ready)
        if not get_string(field, 'blocker', '') and not ready:
            field['blocker'] = 'missing_required' if required and not has_value else 'disabled_or_read_only'
        result.append(field)
    return result


def match_choice_plan(plan: JsonObject, choices: JsonArray) -> JsonObject | None:
    hints = [
        str(plan.get('field_label', '') or ''),
        str(plan.get('field_key', '') or ''),
        str(plan.get('question_contains', '') or ''),
    ]
    normalized_hints = [choice_text(item) for item in hints if item.strip()]
    if not normalized_hints:
        return None
    candidates: list[JsonObject] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        label = choice_text(get_string(choice, 'field_label', ''))
        key = choice_text(get_string(choice, 'field_key', ''))
        if any(hint == label or hint in label or hint in key for hint in normalized_hints):
            candidates.append(choice)
    return candidates[0] if len(candidates) == 1 else None


def choice_text(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def nonblocking_discovery_errors(
    errors: JsonArray,
    disagreement: JsonObject,
    fields: JsonArray,
    active_surface: JsonObject,
) -> bool:
    if not errors or get_string(disagreement, 'status', '') != 'consistent':
        return False
    if not get_bool(active_surface, 'success', False) or get_bool(active_surface, 'partial', False):
        return False
    if any(isinstance(field, dict) and get_array(field, 'frame_path', []) for field in fields):
        return False
    return all(
        isinstance(error, dict) and get_string(error, 'path', '').casefold() in {'iframe', 'iframes'}
        for error in errors
    )


def choice_discovery_required(fields: JsonArray, planned_choices: list[JsonObject]) -> bool:
    if planned_choices:
        return True
    choice_roles = {'radio', 'checkbox', 'switch', 'radiogroup', 'group'}
    choice_types = {'radio', 'checkbox', 'radio_group', 'checkbox_group'}
    for value in fields:
        if not isinstance(value, dict):
            continue
        if get_string(value, 'type', '').casefold() in choice_types:
            return True
        if get_string(value, 'role', '').casefold() in choice_roles:
            return True
    return False


def deep_discovery_required(surface: JsonObject, plans: list[JsonObject]) -> bool:
    """Run deep discovery only when the compact surface cannot prove coverage."""

    if not get_bool(surface, 'success', False):
        return True
    fields = [item for item in get_array(surface, 'fields', []) if isinstance(item, dict)]
    if not fields or get_bool(surface, 'partial', False):
        return True
    diagnostics = get_object(surface, 'site_diagnostics', {})
    framework_hints: set[str] = set()
    for item in get_array(diagnostics, 'framework_hints', []):
        if isinstance(item, str):
            framework_hints.add(item)
        elif isinstance(item, dict):
            hint = get_string(item, 'kind', '')
            if hint:
                framework_hints.add(hint)
    if 'open_shadow_root' in framework_hints:
        return True
    return any(not plan_matches_surface(plan, fields) for plan in plans)


def plan_matches_surface(plan: JsonObject, fields: list[JsonObject]) -> bool:
    element_id = get_string(plan, 'element_id', '')
    selector = get_string(plan, 'selector', '')
    field_key = get_string(plan, 'field_key', '').casefold()
    label_hint = get_string(
        plan,
        'field_label',
        get_string(plan, 'label_contains', get_string(plan, 'question_contains', '')),
    ).casefold()
    name_hint = get_string(plan, 'name', '').casefold()
    candidates: list[JsonObject] = []
    for field in fields:
        if element_id and element_id == get_string(field, 'element_id', ''):
            candidates.append(field)
            continue
        if selector and selector == get_string(field, 'selector_hint', ''):
            candidates.append(field)
            continue
        field_label = get_string(field, 'label', '').casefold()
        field_name = get_string(field, 'name', '').casefold()
        field_key_value = get_string(field, 'field_key', '').casefold()
        if (
            (field_key and field_key == field_key_value)
            or (label_hint and label_hint in field_label)
            or (name_hint and name_hint == field_name)
        ):
            candidates.append(field)
    if not candidates:
        return False
    if element_id or selector or field_key or name_hint:
        return len(candidates) == 1
    return True


__all__ = [
    'choice_discovery_required',
    'choice_text',
    'deep_discovery_required',
    'json_array',
    'json_object_list',
    'match_choice_plan',
    'merge_envelope',
    'nonblocking_discovery_errors',
    'restricted_preflight',
    'semantic_field_states',
]
