"""Build a safe form surface from deep open-shadow-root discovery."""

from __future__ import annotations

from pydoll_mcp_server.json_types import JsonObject, get_array, get_bool, get_int, get_object, get_string

_FIELD_TAGS = frozenset({'input', 'textarea', 'select'})
_FIELD_ROLES = frozenset({'textbox', 'combobox', 'radio', 'checkbox', 'switch'})
_ACTION_TAGS = frozenset({'button', 'a'})
_FINAL_WORDS = frozenset({'submit', 'apply', 'enviar', 'candidatar', 'continue', 'next', 'avançar', 'avancar'})


def enrich_surface_from_deep(surface: JsonObject, deep: JsonObject) -> JsonObject:
    """Merge interactive nodes missing from light-DOM surface discovery."""

    elements = get_array(deep, 'elements', [])
    original_fields = get_array(surface, 'fields', [])
    fields = list(original_fields)
    primary = surface.get('primary_action') if isinstance(surface.get('primary_action'), dict) else {}
    known_ids = {get_string(item, 'element_id', '') for item in fields if isinstance(item, dict)}
    known_ids.discard('')
    known_refs = {
        (get_string(item, 'selector_hint', ''), get_string(item, 'label', '').casefold())
        for item in fields
        if isinstance(item, dict)
    }
    deep_primary: JsonObject = {}
    security_controls = list(get_array(surface, 'security_controls', []))
    for value in elements:
        if not isinstance(value, dict) or not get_bool(value, 'visible', False):
            continue
        tag = get_string(value, 'tag', '').casefold()
        role = get_string(value, 'role', '').casefold()
        attrs = get_object(value, 'attrs', {})
        label = get_string(value, 'label', '')
        element_id = get_string(value, 'element_id', '')
        if tag in _FIELD_TAGS or role in _FIELD_ROLES:
            input_type = get_string(attrs, 'type', '').casefold()
            if input_type in {'hidden', 'button', 'submit', 'reset'}:
                continue
            reference = (get_string(value, 'selector_hint', ''), label.casefold())
            if (element_id and element_id in known_ids) or (reference[0] and reference in known_refs):
                continue
            value_length = get_int(value, 'value_length', 0)
            required = 'required' in attrs or get_string(attrs, 'aria-required', '') == 'true'
            enabled = get_bool(value, 'enabled', True) and get_string(attrs, 'aria-disabled', '') != 'true'
            field: JsonObject = {
                'field_key': f'{get_string(value, "selector_hint", "")}|{label}',
                'element_id': element_id,
                'tag': tag,
                'type': input_type or role,
                'role': role,
                'label': label,
                'name': get_string(attrs, 'name', ''),
                'required': required,
                'visible': True,
                'enabled': enabled,
                'disabled': not enabled,
                'read_only': 'readonly' in attrs or get_string(attrs, 'aria-readonly', '') == 'true',
                'value_present': value_length > 0,
                'value_length': value_length,
                'selected_label': '',
                'selected_value': '',
                'checked': 'checked' in attrs or get_string(attrs, 'aria-checked', '') == 'true',
                'indeterminate': get_string(attrs, 'aria-checked', '') == 'mixed',
                'validity': 'not_yet_validated',
                'errors': [],
                'blocker': 'missing_required' if required and value_length == 0 else '',
                'ready_for_submission': (not required or value_length > 0) and enabled,
                'selector_hint': get_string(value, 'selector_hint', ''),
                'xpath_hint': get_string(value, 'xpath_hint', ''),
                'frame_path': get_array(value, 'frame_path', []),
                'shadow_path': get_array(value, 'shadow_path', []),
            }
            fields.append(field)
            if element_id:
                known_ids.add(element_id)
            if reference[0]:
                known_refs.add(reference)
            continue
        if tag in _ACTION_TAGS or role in {'button', 'link'}:
            name = label or get_string(value, 'text', '')
            if not deep_primary and _is_primary_name(name, tag, attrs):
                deep_primary = _action_from_deep(value, name, role or ('button' if tag == 'button' else 'link'))
        descriptor = f'{label} {get_string(attrs, "name", "")} {get_string(attrs, "type", "")}'.casefold()
        if any(marker in descriptor for marker in ('captcha', 'recaptcha', 'hcaptcha', 'turnstile', 'one-time', 'otp')):
            security_controls.append({'label': label, 'kind': 'security_control', 'automation_allowed': False})
    result = dict(surface)
    result['fields'] = fields
    if not primary and deep_primary:
        result['primary_action'] = deep_primary
    result['security_controls'] = security_controls
    result['partial'] = get_bool(surface, 'partial', False) or get_bool(deep, 'partial', False)
    warnings = list(get_array(surface, 'warnings', []))
    if len(fields) != len(original_fields):
        warnings.append(
            {'kind': 'deep_surface', 'message': 'Open shadow-root controls were merged into the active surface.'}
        )
    result['warnings'] = warnings
    return result


def _is_primary_name(name: str, tag: str, attrs: JsonObject) -> bool:
    text = ' '.join(name.casefold().split())
    input_type = get_string(attrs, 'type', '').casefold()
    return input_type == 'submit' or (tag == 'button' and text in _FINAL_WORDS)


def _action_from_deep(value: JsonObject, name: str, role: str) -> JsonObject:
    return {
        'element_id': get_string(value, 'element_id', ''),
        'name': name,
        'text': get_string(value, 'text', name),
        'role': role,
        'enabled': get_bool(value, 'enabled', True),
        'selector_hint': get_string(value, 'selector_hint', ''),
        'xpath_hint': get_string(value, 'xpath_hint', ''),
        'frame_path': get_array(value, 'frame_path', []),
        'shadow_path': get_array(value, 'shadow_path', []),
        'fingerprint': value.get('fingerprint', {}),
    }


__all__ = ['enrich_surface_from_deep']
