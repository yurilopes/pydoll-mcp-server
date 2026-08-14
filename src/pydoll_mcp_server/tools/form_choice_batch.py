"""One-call semantic selection for independent radio and checkbox groups."""

from __future__ import annotations

import json
import time
import uuid

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.locks import tab_operation_lock
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_array
from pydoll_mcp_server.dom.element_cache import ElementCacheEntry, get_element_cache
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject, get_array, get_bool, get_string
from pydoll_mcp_server.tools.choice_group_scripts import choice_group_helpers_script
from pydoll_mcp_server.tools.form_contracts import invalidate_review_tokens
from pydoll_mcp_server.tools.form_runtime import advance_mutation_epoch


async def select_choices_batch(
    client_id: str,
    tab_id: str,
    choices: list[JsonObject],
    scope: str = 'auto',
) -> JsonObject:
    started_at = time.monotonic()
    if not choices:
        return _result([], True, started_at, 0)
    if any(
        not get_string(choice, 'field_label', '').strip()
        or not get_string(choice, 'option_label', get_string(choice, 'option_text', '')).strip()
        for choice in choices
    ):
        return StructuredError(
            ErrorCode.INVALID_INPUT,
            'Each choice requires field_label and option_label.',
        ).to_dict()
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    payload = json.dumps(
        {
            'scope': scope,
            'choices': [
                {
                    'field': get_string(choice, 'field_label', ''),
                    'option': get_string(choice, 'option_label', get_string(choice, 'option_text', '')),
                }
                for choice in choices
            ],
        },
        ensure_ascii=False,
    )
    invalidate_review_tokens(client_id, tab_id)
    advance_mutation_epoch(client_id, tab_id, 'choices_batch', tab_info)
    browser_calls = 1
    try:
        async with tab_operation_lock(tab_id):
            raw = await tab_info.pydoll_tab.execute_script(_batch_script(payload), return_by_value=True)
        values = extract_normalized_array(raw, 'form_select_choices_batch')
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return StructuredError(
            ErrorCode.EXECUTION_ERROR,
            f'Choice batch failed: {exc}',
            retryable=True,
        ).to_dict()

    results: JsonArray = []
    for value in values:
        if not isinstance(value, dict):
            continue
        if get_bool(value, 'verified', False):
            value['element_id'] = _cache_choice(tab_info.tab_id, tab_info.document_generation, value)
        results.append(value)
    verified_count = sum(1 for item in results if isinstance(item, dict) and get_bool(item, 'verified', False))
    return _result(
        results,
        verified_count == len(choices) and len(results) == len(choices),
        started_at,
        browser_calls,
    )


def _result(results: JsonArray, verified: bool, started_at: float, browser_calls: int) -> JsonObject:
    return {
        'contract_version': 2,
        'operation_id': f'choices_batch_{uuid.uuid4().hex[:16]}',
        'success': verified,
        'status': 'verified' if verified else 'inconclusive',
        'choices': results,
        'verified': verified,
        'verification': 'verified' if verified else 'inconclusive',
        'ready_for_submission': verified,
        'performance': {
            'total_ms': round(max(0.0, (time.monotonic() - started_at) * 1000), 1),
            'discovery_ms': 0.0,
            'mutation_ms': 0.0,
            'verification_ms': 0.0,
            'wait_ms': 0.0,
            'browser_calls': browser_calls,
            'full_scans': 0,
            'deep_scans': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'fallbacks': 0,
            'round_trips_saved': max(0, len(results) - 1),
        },
    }


def _cache_choice(tab_id: str, generation: int, result: JsonObject) -> str:
    element_id = f'el_{uuid.uuid4().hex[:12]}'
    get_element_cache().store(
        ElementCacheEntry(
            element_id=element_id,
            tab_id=tab_id,
            document_generation=generation,
            frame_path=[value for value in get_array(result, 'frame_path', []) if isinstance(value, str)],
            shadow_path=[value for value in get_array(result, 'shadow_path', []) if isinstance(value, str)],
            selector_hint=get_string(result, 'selector_hint', ''),
            xpath_hint=get_string(result, 'xpath_hint', ''),
            text_summary=get_string(result, 'selected_label', '')[:100],
            label_summary=get_string(result, 'field_label', '')[:160],
        )
    )
    return element_id


def _batch_script(payload: str) -> str:
    return (
        f'const request = {payload};'
        + choice_group_helpers_script()
        + r"""
function choiceRoot(scope) {
  const dialogs = choiceQueryAll(document, 'dialog,[role="dialog"],[aria-modal="true"]')
    .filter(choiceVisible);
  const dialog = dialogs[dialogs.length - 1];
  if (['auto', 'modal', 'dialog'].includes(scope) && dialog) return dialog;
  if (scope === 'form') return choiceQueryAll(document, 'form').find(choiceVisible) || document;
  if (scope === 'main') return choiceQueryAll(document, 'main,[role="main"]').find(choiceVisible) || document;
  return document;
}
const output = [];
for (const item of request.choices || []) {
  const root = choiceRoot(request.scope || 'auto');
  const match = choiceFindGroup(root, item.field || '');
  if (!match.group) {
    output.push({field_label: item.field || '', option_label: item.option || '',
      verified: false, error: match.reason === 'ambiguous_question' ? 'ambiguous_field' : 'field_not_found',
      candidates: match.candidates.map((candidate) => ({label: candidate.label, score: candidate.score}))});
    continue;
  }
  const wantedOption = choiceFold(item.option || '');
  const options = match.group.options.filter((option) => choiceFold(choiceOptionText(option)) === wantedOption);
  if (options.length !== 1) {
    output.push({field_label: match.label, option_label: item.option || '', verified: false,
      error: options.length ? 'ambiguous_option' : 'option_not_found'});
    continue;
  }
  const target = options[0];
  if (target.disabled || target.getAttribute('aria-disabled') === 'true') {
    output.push({field_label: match.label, option_label: item.option || '', verified: false,
      error: 'disabled_control'});
    continue;
  }
  try { target.click(); } catch (error) {
    output.push({field_label: match.label, option_label: item.option || '', verified: false,
      error: 'click_failed'});
    continue;
  }
  const checked = choiceChecked(target);
  output.push({
    field_label: match.label,
    option_label: item.option || '',
    selected_label: choiceOptionText(target),
    selected_state: checked ? 'selected' : 'inconclusive',
    checked,
    indeterminate: target.indeterminate === true || target.getAttribute('aria-checked') === 'mixed',
    verified: checked,
    selector_hint: choiceSelectorHint(target),
    xpath_hint: structuralXPath(target),
    shadow_path: choiceShadowPath(target),
    frame_path: []
  });
}
return output;
"""
    )


__all__ = ['select_choices_batch']
