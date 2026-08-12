from __future__ import annotations

from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_string


def surface_disagreement(fields: JsonArray, deep: JsonObject) -> JsonObject:
    if not deep.get('success'):
        return {'status': 'unavailable', 'reason': 'Deep discovery did not complete.'}
    field_tags = {'input', 'textarea', 'select'}
    field_roles = {'combobox', 'textbox', 'checkbox', 'radio', 'switch'}
    deep_interactive = 0
    deep_scoped = 0
    for value in get_array(deep, 'elements', []):
        if not isinstance(value, dict):
            continue
        interactive = (
            get_string(value, 'tag', '').casefold() in field_tags
            or get_string(value, 'role', '').casefold() in field_roles
        )
        if interactive:
            deep_interactive += 1
            if get_array(value, 'shadow_path', []) or get_array(value, 'frame_path', []):
                deep_scoped += 1
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
            'recommendation': 'Refine scope or use a deep element reference before mutating.',
        }
    return {
        'status': 'consistent',
        'surface_field_count': len(fields),
        'deep_interactive_count': deep_interactive,
        'surface_scoped_count': surface_scoped,
        'deep_scoped_count': deep_scoped,
    }
