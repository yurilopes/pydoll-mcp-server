"""Internal helpers for the semantic form workflow."""

from __future__ import annotations

from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    JsonValue,
    get_array,
    get_bool,
    get_int,
    get_string,
)
from pydoll_mcp_server.tools import form_discovery as _form_discovery
from pydoll_mcp_server.tools import form_workflow_support as _workflow_support
from pydoll_mcp_server.tools.elements import element_click, element_fill
from pydoll_mcp_server.tools.files import file_upload_state, upload_files
from pydoll_mcp_server.tools.form_choice_batch import select_choices_batch
from pydoll_mcp_server.tools.form_controls import combobox_type_and_select
from pydoll_mcp_server.tools.form_fill import FormFillField, form_fill_fields
from pydoll_mcp_server.tools.form_prepare_support import (
    hard_prepare_blockers as _hard_prepare_blockers,
)
from pydoll_mcp_server.tools.form_prepare_support import (
    is_final_submit_text as _is_final_submit_text,
)

DOMAIN_RESTRICTIONS = _workflow_support.DOMAIN_RESTRICTIONS
_DOMAIN_RESTRICTIONS = DOMAIN_RESTRICTIONS
active_domain_restriction = _workflow_support.active_domain_restriction
domain_restriction_to_json = _workflow_support.domain_restriction_to_json
normalize_employer_domain = _workflow_support.normalize_employer_domain
record_domain_restriction = _workflow_support.record_domain_restriction
snapshot_as_surface = _workflow_support.snapshot_as_surface
surface_disagreement = _form_discovery.surface_disagreement

_SENSITIVE_CONFIRMATION_WORDS = (
    'attest',
    'certif',
    'consent',
    'declaration',
    'legal statement',
    'terms and conditions',
    'application terms',
    'acknowledge',
    'accurate and complete',
    'authorize',
    'background check',
)


async def collect_upload_states(client_id: str, tab_id: str, fields: JsonArray) -> JsonArray:
    states: JsonArray = []
    for value in fields:
        if not isinstance(value, dict) or get_string(value, 'type', '').casefold() != 'file':
            continue
        element_id = get_string(value, 'element_id', '')
        if not element_id:
            continue
        states.append(await file_upload_state(client_id, tab_id, element_id))
    return states


async def prepare_actions(
    client_id: str,
    tab_id: str,
    fields: list[JsonObject],
    choices: list[JsonObject],
    combos: list[JsonObject],
    uploads: list[JsonObject],
    observed_fields: JsonArray,
    do_not_touch: list[str],
    preset: str = 'generic_form',
) -> JsonArray:
    actions: JsonArray = []
    fallback_fields: list[FormFillField] = []
    for plan in fields:
        field = match_field(plan, observed_fields, prefer_direct_control=True)
        label = field_label(field, plan)
        if protected(label, do_not_touch):
            actions.append({'kind': 'field', 'label': label, 'status': 'requires_candidate_confirmation'})
            continue
        if 'value' not in plan:
            continue
        value = scalar_text(plan.get('value'))
        element_id = str(plan.get('element_id', '') or (field or {}).get('element_id', ''))
        scoped = bool(field and (get_array(field, 'shadow_path', []) or get_array(field, 'frame_path', [])))
        if element_id and scoped:
            action = await element_fill(
                client_id,
                tab_id,
                element_id,
                value,
                mode=str(plan.get('mode', 'auto')),
                state_verification=str(plan.get('state_verification', 'submission_ready')),
            )
            actions.append({'kind': 'field', 'label': label, 'result': action})
        elif field is not None:
            fallback_fields.append(as_fill_field(plan, label, value, field))
        else:
            fallback_fields.append(as_fill_field(plan, label, value))
    if fallback_fields:
        actions.append({'kind': 'fields_batch', 'result': await form_fill_fields(client_id, tab_id, fallback_fields)})
    pending_choices: list[JsonObject] = []
    for plan in choices:
        label = str(plan.get('field_label', '') or field_label(match_field(plan, observed_fields), plan))
        option = str(plan.get('option_label', '') or plan.get('option_text', ''))
        if protected(label, do_not_touch):
            actions.append({'kind': 'choice', 'field_label': label, 'status': 'requires_candidate_confirmation'})
            continue
        element_id = str(plan.get('element_id', ''))
        if element_id:
            actions.append(
                {
                    'kind': 'choice',
                    'result': await element_click(client_id, tab_id, element_id, click_strategy='auto'),
                }
            )
            continue
        if label and option:
            pending_choices.append({**plan, 'field_label': label, 'option_label': option})
            continue
        actions.append({'kind': 'choice', 'status': 'stale', 'message': 'Choice requires field_label and option.'})
    if pending_choices:
        actions.append(
            {
                'kind': 'choices_batch',
                'result': await select_choices_batch(client_id, tab_id, pending_choices),
            }
        )
    combo_fields = (
        await _refresh_active_fields(client_id, tab_id, observed_fields, preset) if combos else observed_fields
    )
    for plan in combos:
        field = match_field(plan, combo_fields)
        re_resolved = False
        if field is None:
            original_field = match_field(plan, observed_fields)
            if original_field is not None:
                replacement_plan = stable_re_resolution_plan(plan, original_field)
                field = match_field(replacement_plan, combo_fields)
                re_resolved = field is not None
        planned_element_id = get_string(plan, 'element_id', '')
        current_element_id = get_string(field or {}, 'element_id', '')
        if current_element_id and current_element_id != planned_element_id:
            re_resolved = True
        element_id = current_element_id or planned_element_id
        if not element_id:
            actions.append({'kind': 'combobox', 'status': 'stale', 'message': 'No current combobox element_id.'})
            continue
        result = await combobox_type_and_select(
            client_id,
            tab_id,
            element_id,
            str(plan.get('query', '')),
            str(plan.get('option_text', '')),
            bool(plan.get('exact', True)),
            None,
            bool(plan.get('allow_approximate', False)),
        )
        if re_resolved:
            result['re_resolved'] = True
            result['previous_element_id'] = str(plan.get('element_id', ''))
        actions.append(
            {
                'kind': 'combobox',
                'result': result,
            }
        )
    for plan in uploads:
        element_id = str(plan.get('element_id', '') or (match_field(plan, observed_fields) or {}).get('element_id', ''))
        raw_paths = plan.get('paths', [])
        paths = [item for item in raw_paths if isinstance(item, str)] if isinstance(raw_paths, list) else []
        clear_existing = bool(plan.get('clear_existing', False))
        if not element_id or (not paths and not clear_existing):
            actions.append(
                {
                    'kind': 'upload',
                    'status': 'stale',
                    'message': 'Upload requires a current element_id and paths, or clear_existing=true.',
                }
            )
            continue
        actions.append(
            {
                'kind': 'upload',
                'result': await upload_files(
                    client_id,
                    tab_id,
                    element_id,
                    paths,
                    replace_existing=bool(plan.get('replace_existing', False)),
                    clear_existing=clear_existing,
                ),
            }
        )
    return actions


def pending_required(fields: JsonArray, protected_values: list[str]) -> JsonArray:
    pending: JsonArray = []
    for value in fields:
        if not isinstance(value, dict):
            continue
        label = field_label(value, {})
        if not get_bool(value, 'required', False) or protected(label, protected_values):
            continue
        kind = get_string(value, 'type', '')
        has_value = get_bool(value, 'value_present', False) or get_int(value, 'value_length', 0) > 0
        has_value = has_value or bool(value.get('selected')) or get_bool(value, 'checked', False)
        if kind.endswith('_group'):
            has_value = get_bool(value, 'checked', False)
        if not has_value:
            pending.append({'label': label, 'field_key': get_string(value, 'field_key', ''), 'type': kind})
    return pending


def attestation_handoffs(fields: JsonArray, protected_values: list[str]) -> JsonArray:
    handoffs: JsonArray = []
    for value in fields:
        if not isinstance(value, dict):
            continue
        label = field_label(value, {})
        folded = label.casefold()
        if any(word in folded for word in _SENSITIVE_CONFIRMATION_WORDS):
            handoff: JsonObject = {'label': label, 'requires_candidate_confirmation': True}
            if protected(label, protected_values):
                handoff['protected_by_do_not_touch'] = True
            handoffs.append(handoff)
    return handoffs


def covered_by_plans(field: JsonObject, plans: list[JsonObject]) -> bool:
    label = field_label(field, {}).casefold()
    key = get_string(field, 'field_key', '').casefold()
    element_id = get_string(field, 'element_id', '')
    for plan in plans:
        if element_id and str(plan.get('element_id', '')) == element_id:
            return True
        hints = [
            str(plan.get(name, ''))
            for name in (
                'field_key',
                'field_label',
                'label_contains',
                'question_contains',
                'placeholder_contains',
                'name',
                'selector',
                'element_id',
            )
        ]
        if any(hint and (hint.casefold() in label or hint.casefold() in key) for hint in hints):
            return True
    return False


def match_field(plan: JsonObject, fields: JsonArray, prefer_direct_control: bool = False) -> JsonObject | None:
    element_id = get_string(plan, 'element_id', '')
    fingerprint = get_string(plan, 'fingerprint', '')
    selector = get_string(plan, 'selector', '')
    key = get_string(plan, 'field_key', '').casefold()
    label_hint = get_string(
        plan,
        'field_label',
        get_string(plan, 'label_contains', get_string(plan, 'question_contains', '')),
    ).casefold()
    placeholder_hint = get_string(plan, 'placeholder_contains', '').casefold()
    name_hint = get_string(plan, 'name', '').casefold()
    label_matches: list[JsonObject] = []
    for value in fields:
        if not isinstance(value, dict):
            continue
        if element_id and element_id == get_string(value, 'element_id', ''):
            return value
        field_key = get_string(value, 'field_key', '').casefold()
        label = field_label(value, {}).casefold()
        placeholder = get_string(value, 'placeholder', '').casefold()
        name = get_string(value, 'name', '').casefold()
        field_selector = get_string(value, 'selector_hint', '')
        if fingerprint and fingerprint == get_string(value, 'fingerprint', ''):
            return value
        if selector and selector == field_selector:
            return value
        if key and key == field_key:
            return value
        if (
            (label_hint and label_hint in label)
            or (placeholder_hint and placeholder_hint in placeholder)
            or (name_hint and name_hint == name)
        ):
            label_matches.append(value)
    if prefer_direct_control:
        for value in label_matches:
            if _is_direct_control(value):
                return value
    if label_matches:
        return label_matches[0]
    return None


async def _refresh_active_fields(
    client_id: str,
    tab_id: str,
    fallback: JsonArray,
    preset: str = 'generic_form',
) -> JsonArray:
    from pydoll_mcp_server.tools.active_surface import page_get_active_surface

    surface = await page_get_active_surface(
        client_id,
        tab_id,
        scope='auto',
        include_diagnostics=True,
        preset=preset,
        include_shadow=True,
    )
    if not surface.get('success'):
        return fallback
    fields = get_array(surface, 'fields', [])
    return fields if fields else fallback


def stable_re_resolution_plan(plan: JsonObject, field: JsonObject) -> JsonObject:
    result = dict(plan)
    result['element_id'] = ''
    for plan_key, field_key in (
        ('field_key', 'field_key'),
        ('field_label', 'label'),
        ('placeholder_contains', 'placeholder'),
        ('name', 'name'),
        ('role', 'role'),
        ('type', 'type'),
        ('selector', 'selector_hint'),
        ('fingerprint', 'fingerprint'),
    ):
        if not get_string(result, plan_key, ''):
            value = get_string(field, field_key, '')
            if value:
                result[plan_key] = value
    return result


def _is_direct_control(field: JsonObject) -> bool:
    tag = get_string(field, 'tag', '').casefold()
    return tag in {'input', 'textarea', 'select'} or get_bool(field, 'contenteditable', False)


def field_label(field: JsonObject | None, plan: JsonObject) -> str:
    if field:
        label = get_string(field, 'label', '')
        if label:
            return label
        labels = field.get('labels')
        if isinstance(labels, list):
            for value in labels:
                if isinstance(value, str) and value:
                    return value
    return str(plan.get('field_label', plan.get('label_contains', plan.get('question_contains', ''))))


def scalar_text(value: JsonValue) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, str | int | float):
        return str(value)
    raise ValueError('Form values must be scalar and confirmed by the caller.')


def as_fill_field(
    plan: JsonObject,
    label: str,
    value: str,
    observed_field: JsonObject | None = None,
) -> FormFillField:
    result: FormFillField = {'value': value}
    for key in (
        'field_key',
        'question_contains',
        'placeholder_contains',
        'selector',
        'role',
        'name',
        'type',
        'state_verification',
    ):
        item = plan.get(key)
        if isinstance(item, str) and item:
            if key == 'field_key':
                result['field_key'] = item
            elif key == 'question_contains':
                result['question_contains'] = item
            elif key == 'placeholder_contains':
                result['placeholder_contains'] = item
            elif key == 'selector':
                result['selector'] = item
            elif key == 'role':
                result['role'] = item
            elif key == 'name':
                result['name'] = item
            elif key == 'type':
                result['type'] = item
            elif key == 'state_verification':
                result['state_verification'] = item
    if observed_field is not None:
        for key in ('selector_hint', 'role', 'name', 'type'):
            observed_value = get_string(observed_field, key, '')
            if observed_value and key not in result:
                if key == 'selector_hint':
                    result['selector'] = observed_value
                elif key == 'role':
                    result['role'] = observed_value
                elif key == 'name':
                    result['name'] = observed_value
                elif key == 'type':
                    result['type'] = observed_value
    if label and 'label_contains' not in result:
        result['label_contains'] = label
    return result


def protected(label: str, protected_values: list[str]) -> bool:
    folded = label.casefold()
    return any(item in folded for item in protected_values)


def hard_prepare_blockers(preflight: JsonObject, plans: list[JsonObject] | None = None) -> JsonArray:
    return _hard_prepare_blockers(preflight, plans)


def is_final_submit_text(text: str) -> bool:
    return _is_final_submit_text(text)
