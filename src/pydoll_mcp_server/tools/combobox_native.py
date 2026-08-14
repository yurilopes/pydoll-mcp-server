"""Native select handling used by the semantic combobox operation."""

from __future__ import annotations

import json
import time
import unicodedata

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_object
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_bool, get_string
from pydoll_mcp_server.tools.element_resolver import resolve_element
from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens
from pydoll_mcp_server.tools.form_runtime import advance_mutation_epoch


async def select_native_option(
    client_id: str,
    tab_id: str,
    element_id: str,
    option_text: str,
    allow_approximate: bool,
) -> JsonObject:
    target = json.dumps(unicodedata.normalize('NFC', option_text))
    approximate = 'true' if allow_approximate else 'false'
    script = f"""
    (() => {{
        if (this.disabled) return {{error:'disabled_control'}};
        const normalize = (value) => String(value || '').normalize('NFC').replace(/\\s+/g, ' ').trim();
        const fold = (value) => normalize(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
        const wanted = normalize({target});
        const exact = [...this.options].filter((option) =>
            normalize(option.text) === wanted || normalize(option.value) === wanted
        );
        let matches = exact;
        let approximate = false;
        if (!matches.length && {approximate}) {{
            const folded = fold(wanted);
            matches = [...this.options].filter((option) =>
                fold(option.text) === folded || fold(option.value) === folded
            );
            approximate = matches.length > 0;
        }}
        if (matches.length !== 1) return {{error: matches.length ? 'ambiguous_option' : 'option_not_found'}};
        const option = matches[0];
        this.value = option.value;
        option.selected = true;
        this.dispatchEvent(new Event('input', {{bubbles:true}}));
        this.dispatchEvent(new Event('change', {{bubbles:true}}));
        this.dispatchEvent(new Event('blur', {{bubbles:true}}));
        return {{selected_label:normalize(option.text),selected_value:option.value,
            approximate_match:approximate,verified:this.value===option.value,
            popup_open:false}};
    }})()
    """
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
        element = await resolve_element(tab_info, element_id)
        if element is None:
            return StructuredError(ErrorCode.STALE_ELEMENT, f'Element {element_id} is stale').to_dict()
        invalidate_review_tokens(client_id, tab_id)
        advance_mutation_epoch(client_id, tab_id, 'combobox', tab_info)
        async with tab_operation_lock(tab_id):
            result = extract_normalized_object(
                await element.execute_script(script, return_by_value=True),
                'native_combobox_select',
            )
    except StructuredError as exc:
        return exc.to_dict()
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Native option selection failed: {exc}',
            retryable=True,
        ).to_dict()
    error = get_string(result, 'error', '')
    if error:
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            f'Native option selection failed: {error}',
            details={'option_text': option_text},
        ).to_dict()
    verified = get_bool(result, 'verified', False)
    return {
        'contract_version': 2,
        'operation_id': f'combobox_{int(time.time() * 1000)}',
        'success': True,
        'status': 'verified' if verified else 'inconclusive',
        'selected_label': get_string(result, 'selected_label', option_text),
        'selected_value': get_string(result, 'selected_value', ''),
        'selected_state': 'selected' if verified else 'inconclusive',
        'verified': verified,
        'verification': 'verified' if verified else 'inconclusive',
        'approximate_match': get_bool(result, 'approximate_match', False),
        'mode_used': 'native_select',
        'new_element_id': element_id,
        'state': result,
    }


__all__ = ['select_native_option']
