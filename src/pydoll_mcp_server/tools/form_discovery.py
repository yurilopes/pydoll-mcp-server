from __future__ import annotations

from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_bool, get_object, get_string


def surface_disagreement(fields: JsonArray, deep: JsonObject) -> JsonObject:
    if not deep.get('success'):
        return {'status': 'unavailable', 'reason': 'Deep discovery did not complete.'}
    field_tags = {'input', 'textarea', 'select'}
    field_roles = {'combobox', 'textbox', 'checkbox', 'radio', 'switch'}
    deep_identities: set[tuple[str, str]] = set()
    deep_scoped = 0
    ignored_hidden = 0
    ignored_frame = 0
    for value in get_array(deep, 'elements', []):
        if not isinstance(value, dict):
            continue
        attrs = get_object(value, 'attrs', {})
        input_type = get_string(attrs, 'type', '').casefold()
        if input_type in {'hidden', 'button', 'submit', 'reset'}:
            ignored_hidden += 1
            continue
        if not get_bool(value, 'visible', True):
            ignored_hidden += 1
            continue
        if get_array(value, 'frame_path', []):
            ignored_frame += 1
            continue
        interactive = (
            get_string(value, 'tag', '').casefold() in field_tags
            or get_string(value, 'role', '').casefold() in field_roles
        )
        if interactive:
            tag = get_string(value, 'tag', '').casefold()
            role = get_string(value, 'role', '').casefold()
            name = get_string(attrs, 'name', '')
            label = get_string(value, 'label', '').casefold()
            selector = get_string(value, 'selector_hint', '')
            if tag == 'input' and role in {'radio', 'checkbox'} and name:
                identity = (role, name)
            else:
                identity = (tag or role, selector or label or get_string(value, 'element_id', ''))
            deep_identities.add(identity)
            if get_array(value, 'shadow_path', []) or get_array(value, 'frame_path', []):
                deep_scoped += 1
    deep_interactive = len(deep_identities)
    surface_scoped = sum(
        1
        for value in fields
        if isinstance(value, dict) and (get_array(value, 'shadow_path', []) or get_array(value, 'frame_path', []))
    )
    if deep_interactive > len(fields) + 1 or deep_scoped != surface_scoped:
        return {
            'status': 'disagreement',
            'surface_field_count': len(fields),
            'deep_interactive_count': deep_interactive,
            'surface_scoped_count': surface_scoped,
            'deep_scoped_count': deep_scoped,
            'ignored_hidden_count': ignored_hidden,
            'ignored_frame_count': ignored_frame,
            'recommendation': 'Refine scope or use a deep element reference before mutating.',
        }
    return {
        'status': 'consistent',
        'surface_field_count': len(fields),
        'deep_interactive_count': deep_interactive,
        'surface_scoped_count': surface_scoped,
        'deep_scoped_count': deep_scoped,
        'ignored_hidden_count': ignored_hidden,
        'ignored_frame_count': ignored_frame,
    }
