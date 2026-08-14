"""Pure blockers and action-policy helpers for form preparation."""

from __future__ import annotations

import unicodedata

from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_object, get_string

_SUBMIT_WORDS = (
    'submit',
    'apply',
    'send application',
    'enviar candidatura',
    'candidatar',
    'enviar inscrição',
)


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
        if kind == 'discovery' and get_string(get_object(value, 'details', {}), 'status', '') == 'consistent':
            continue
        if kind == 'discovery' and discovery_is_safe_for_plans(preflight, plans or []):
            continue
        if kind == 'primary_action' and get_string(value, 'reason', '') == 'not_found' and plans:
            continue
        if kind == 'security_control':
            continue
        if kind not in {'required_field', 'missing_candidate_data'}:
            if kind == 'attestation' and attestations:
                protected_attestations = all(
                    _protected(get_string(item, 'label', ''), protected_values)
                    for item in attestations
                    if isinstance(item, dict)
                )
                if protected_attestations:
                    continue
            blockers.append(value)
    return blockers


def discovery_is_safe_for_plans(preflight: JsonObject, plans: list[JsonObject]) -> bool:
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
        has_hints = any(
            get_string(plan, key, '').strip()
            for key in ('field_key', 'field_label', 'label_contains', 'question_contains', 'name')
        )
        if has_hints and len(matches) != 1:
            return False
        if not has_hints:
            return False
    return True


def is_final_submit_text(text: str) -> bool:
    folded = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().casefold().strip()
    normalized_words = {
        unicodedata.normalize('NFKD', word).encode('ascii', 'ignore').decode().casefold() for word in _SUBMIT_WORDS
    }
    normalized_words.add('enviar inscricao')
    return any(word in folded for word in normalized_words)


def _protected(label: str, protected_values: list[str]) -> bool:
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
    label = get_string(field, 'label', get_string(field, 'name', '')).casefold()
    for key in ('field_key', 'field_label', 'label_contains', 'question_contains', 'name'):
        hint = get_string(plan, key, '').casefold()
        if hint and (hint in label or hint in field_key):
            return True
    return False


__all__ = ['hard_prepare_blockers', 'is_final_submit_text']
