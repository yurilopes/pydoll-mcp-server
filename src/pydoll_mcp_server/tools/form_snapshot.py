from __future__ import annotations

import uuid

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_array
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, require_json_object
from pydoll_mcp_server.tools.form_scripts import form_snapshot_script


async def form_snapshot(client_id: str, tab_id: str, max_fields: int = 100) -> JsonObject:
    try:
        tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
        result = await tab.execute_script(form_snapshot_script(max_fields), return_by_value=True)
        fields = extract_normalized_array(result, 'form_snapshot')
        partial = len(fields) >= max_fields
        return {
            'contract_version': 2,
            'operation_id': f'form_snapshot_{uuid.uuid4().hex[:16]}',
            'success': True,
            'status': 'partial' if partial else 'verified',
            'fields': fields,
            'count': len(fields),
            'partial': partial,
        }
    except StructuredError as exc:
        return exc.to_dict()
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(ErrorCode.EXECUTION_ERROR, f'Form snapshot failed: {exc}', retryable=True).to_dict()


async def form_errors(client_id: str, tab_id: str, max_fields: int = 100) -> JsonObject:
    snapshot = await form_snapshot(client_id, tab_id, max_fields)
    if not snapshot.get('success'):
        return snapshot
    errors: JsonArray = []
    for field_value in get_array(snapshot, 'fields', []):
        field = require_json_object(field_value, 'form field')
        field_errors = field.get('errors')
        if isinstance(field_errors, list) and field_errors:
            errors.append(field)
    return {
        'contract_version': 2,
        'operation_id': f'form_errors_{uuid.uuid4().hex[:16]}',
        'success': True,
        'status': 'verified',
        'errors': errors,
        'count': len(errors),
    }
