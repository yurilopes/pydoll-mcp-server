"""Internal helpers for the semantic form workflow."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydoll_mcp_server.json_types import JsonArray, JsonObject, JsonValue, get_array, get_bool, get_int, get_string
from pydoll_mcp_server.tools.elements import element_click, element_fill
from pydoll_mcp_server.tools.files import file_upload_state, upload_files
from pydoll_mcp_server.tools.form_choice import form_select_choice
from pydoll_mcp_server.tools.form_controls import combobox_type_and_select
from pydoll_mcp_server.tools.form_discovery import surface_disagreement
from pydoll_mcp_server.tools.form_fill import FormFillField, form_fill_fields


@dataclass
class DomainRestriction:
    domain: str
    reason: str
    evidence_text: list[str]
    timestamp: float
    expires_at: float | None
    job_identifiers: list[str]


_DOMAIN_RESTRICTIONS: dict[str, DomainRestriction] = {}
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
_SUBMIT_WORDS = ('submit', 'apply', 'send application', 'enviar candidatura', 'candidatar', 'enviar inscrição')


def normalize_employer_domain(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ''
    parsed = urlsplit(candidate if '://' in candidate else f'https://{candidate}')
    return (parsed.hostname or '').lower().rstrip('.')


def record_domain_restriction(
    employer_domain: str,
    reason: str,
    evidence_text: list[str],
    job_identifiers: list[str] | None = None,
    expires_at: float | None = None,
) -> JsonObject:
    domain = normalize_employer_domain(employer_domain)
    if not domain:
        return {'recorded': False, 'reason': 'employer_domain is required'}
    restriction = DomainRestriction(
        domain=domain,
        reason=reason,
        evidence_text=list(evidence_text),
        timestamp=time.time(),
        expires_at=expires_at,
        job_identifiers=list(job_identifiers or []),
    )
    _DOMAIN_RESTRICTIONS[domain] = restriction
    return domain_restriction_to_json(restriction)


def active_domain_restriction(domain: str) -> DomainRestriction | None:
    restriction = _DOMAIN_RESTRICTIONS.get(normalize_employer_domain(domain))
    if restriction is not None and restriction.expires_at is not None and restriction.expires_at <= time.time():
        _DOMAIN_RESTRICTIONS.pop(restriction.domain, None)
        return None
    return restriction


def domain_restriction_to_json(restriction: DomainRestriction) -> JsonObject:
    return {
        'domain': restriction.domain,
        'reason': restriction.reason,
        'evidence_text': list(restriction.evidence_text),
        'timestamp': restriction.timestamp,
        'expires_at': restriction.expires_at,
        'job_identifiers': list(restriction.job_identifiers),
    }


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
        if element_id:
            action = await element_fill(
                client_id,
                tab_id,
                element_id,
                value,
                mode=str(plan.get('mode', 'auto')),
                state_verification=str(plan.get('state_verification', 'submission_ready')),
            )
            actions.append({'kind': 'field', 'label': label, 'result': action})
        else:
            fallback_fields.append(as_fill_field(plan, label, value))
    if fallback_fields:
        actions.append({'kind': 'fields_batch', 'result': await form_fill_fields(client_id, tab_id, fallback_fields)})
    for plan in choices:
        label = str(plan.get('field_label', '') or field_label(match_field(plan, observed_fields), plan))
        option = str(plan.get('option_label', '') or plan.get('option_text', ''))
        if protected(label, do_not_touch):
            actions.append({'kind': 'choice', 'field_label': label, 'status': 'requires_candidate_confirmation'})
            continue
        element_id = str(plan.get('element_id', ''))
        if element_id or (label and option):
            result = (
                await element_click(client_id, tab_id, element_id, click_strategy='auto')
                if element_id
                else await form_select_choice(client_id, tab_id, label, option)
            )
            actions.append({'kind': 'choice', 'result': result})
    for plan in combos:
        field = match_field(plan, observed_fields)
        element_id = str(plan.get('element_id', '') or (field or {}).get('element_id', ''))
        if not element_id:
            actions.append({'kind': 'combobox', 'status': 'stale', 'message': 'No current combobox element_id.'})
            continue
        actions.append(
            {
                'kind': 'combobox',
                'result': await combobox_type_and_select(
                    client_id,
                    tab_id,
                    element_id,
                    str(plan.get('query', '')),
                    str(plan.get('option_text', '')),
                    bool(plan.get('exact', True)),
                    None,
                    bool(plan.get('allow_approximate', False)),
                ),
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


def snapshot_as_surface(snapshot: JsonObject) -> JsonObject:
    return {
        'success': True,
        'surface': 'form',
        'fields': get_array(snapshot, 'fields', []),
        'primary_action': {},
        'security_controls': [],
        'errors': [],
        'warnings': [{'kind': 'fallback', 'message': 'Active surface discovery failed; form snapshot used.'}],
        'partial': get_bool(snapshot, 'partial', False),
    }


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
    key = str(plan.get('field_key', '')).casefold()
    label_hint = str(plan.get('field_label', plan.get('label_contains', plan.get('question_contains', '')))).casefold()
    label_matches: list[JsonObject] = []
    for value in fields:
        if not isinstance(value, dict):
            continue
        field_key = get_string(value, 'field_key', '').casefold()
        label = field_label(value, {}).casefold()
        if key and key == field_key:
            return value
        if label_hint and label_hint in label:
            label_matches.append(value)
    if prefer_direct_control:
        for value in label_matches:
            if _is_direct_control(value):
                return value
    if label_matches:
        return label_matches[0]
    return None


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


def as_fill_field(plan: JsonObject, label: str, value: str) -> FormFillField:
    result: FormFillField = {'value': value}
    for key in ('question_contains', 'placeholder_contains', 'selector', 'role', 'name', 'type', 'state_verification'):
        item = plan.get(key)
        if isinstance(item, str) and item:
            result[key] = item
    if label and 'label_contains' not in result:
        result['label_contains'] = label
    return result


def protected(label: str, protected_values: list[str]) -> bool:
    folded = label.casefold()
    return any(item in folded for item in protected_values)


def _plan_matches_field(plan: JsonObject, field: JsonObject) -> bool:
    element_id = get_string(plan, 'element_id', '')
    if element_id:
        return element_id == get_string(field, 'element_id', '')
    type_hint = get_string(plan, 'type', '').casefold()
    if type_hint:
        field_type = get_string(field, 'type', '').casefold()
        field_tag = get_string(field, 'tag', '').casefold()
        if type_hint not in {field_type, field_tag}:
            return False
    field_key = get_string(field, 'field_key', '').casefold()
    label = field_label(field, {}).casefold()
    for key in ('field_key', 'field_label', 'label_contains', 'question_contains', 'name'):
        hint = get_string(plan, key, '').casefold()
        if hint and (hint in label or hint in field_key):
            return True
    return False


def _discovery_is_safe_for_plans(preflight: JsonObject, plans: list[JsonObject]) -> bool:
    """Allow a disputed deep inventory only for unique active-surface targets."""

    if not plans:
        return False
    fields = [item for item in get_array(preflight, 'fields', []) if isinstance(item, dict)]
    if not fields:
        return False
    for plan in plans:
        matches = [field for field in fields if _plan_matches_field(plan, field)]
        if get_string(plan, 'element_id', ''):
            if len(matches) != 1:
                return False
            continue
        if (
            any(
                get_string(plan, key, '').strip()
                for key in ('field_key', 'field_label', 'label_contains', 'question_contains', 'name')
            )
            and len(matches) != 1
        ):
            return False
        if not any(
            get_string(plan, key, '').strip()
            for key in ('field_key', 'field_label', 'label_contains', 'question_contains', 'name')
        ):
            return False
    return True


def hard_prepare_blockers(preflight: JsonObject, plans: list[JsonObject] | None = None) -> JsonArray:
    blockers: JsonArray = []
    protected_values = [
        item.casefold() for item in get_array(preflight, 'do_not_touch', []) if isinstance(item, str) and item.strip()
    ]
    attestations = get_array(preflight, 'attestation_handoffs', [])
    for value in get_array(preflight, 'blockers', []):
        if not isinstance(value, dict):
            blockers.append(value)
            continue
        kind = get_string(value, 'kind', '')
        if kind == 'discovery' and _discovery_is_safe_for_plans(preflight, plans or []):
            continue
        if kind == 'primary_action' and get_string(value, 'reason', '') == 'not_found' and plans:
            continue
        if kind == 'security_control':
            # A passive CAPTCHA or similar control blocks submission, but it does not
            # make safe field preparation impossible. The review remains blocked and
            # no submit token can be issued until the candidate completes the control.
            continue
        if kind not in {'required_field', 'missing_candidate_data'}:
            if kind == 'attestation' and attestations:
                protected_attestations = all(
                    protected(get_string(item, 'label', ''), protected_values)
                    for item in attestations
                    if isinstance(item, dict)
                )
                if protected_attestations:
                    continue
            blockers.append(value)
    return blockers


def is_final_submit_text(text: str) -> bool:
    folded = text.casefold().strip()
    return any(word in folded for word in _SUBMIT_WORDS)


__all__ = [
    '_DOMAIN_RESTRICTIONS',
    'active_domain_restriction',
    'attestation_handoffs',
    'covered_by_plans',
    'domain_restriction_to_json',
    'field_label',
    'hard_prepare_blockers',
    'is_final_submit_text',
    'match_field',
    'normalize_employer_domain',
    'pending_required',
    'prepare_actions',
    'protected',
    'record_domain_restriction',
    'snapshot_as_surface',
    'surface_disagreement',
]
