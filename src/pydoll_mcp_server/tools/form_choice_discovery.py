"""Read-only discovery of semantic choice groups on application forms."""

from __future__ import annotations

import json

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_object
from pydoll_mcp_server.dom.reference_scripts import ELEMENT_REFERENCE_HELPERS
from pydoll_mcp_server.errors import StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_array
from pydoll_mcp_server.tools.choice_group_scripts import choice_group_helpers_script


async def discover_choice_states(client_id: str, tab_id: str, scope: str = 'auto') -> JsonObject:
    """Return visible native and custom choice groups without mutating the page."""

    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
        raw = await tab_info.pydoll_tab.execute_script(
            choice_discovery_script(scope),
            return_by_value=True,
        )
        data = extract_normalized_object(raw, 'form_choice_discovery')
    except StructuredError as exc:
        return {'success': False, 'error': exc.to_dict()}
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError) as exc:
        return {'success': False, 'error': {'message': str(exc), 'retryable': True}}
    choices = get_array(data, 'choices', [])
    return {'success': True, 'choices': choices}


def choice_discovery_script(scope: str) -> str:
    payload = json.dumps({'scope': scope}, ensure_ascii=False)
    return (
        'const request = '
        + payload
        + r""";
"""
        + ELEMENT_REFERENCE_HELPERS
        + choice_group_helpers_script()
        + r"""
function choiceRoot(scope) {
  const dialog = [...document.querySelectorAll('dialog,[role="dialog"],[aria-modal="true"]')]
    .filter(choiceVisible).pop();
  if (['auto', 'modal', 'dialog'].includes(scope) && dialog) return dialog;
  if (scope === 'form') {
    return [...document.querySelectorAll('form')].find(choiceVisible) || document.body;
  }
  if (scope === 'main') return document.querySelector('main,[role="main"]') || document.body;
  return document.body;
}

function associatedLabelVisible(element) {
  const labels = [];
  const root = choiceOwnerRoot(element);
  if (element.id) {
    const explicit = choiceQueryAll(root, `label[for="${CSS.escape(element.id)}"]`)[0];
    if (explicit) labels.push(explicit);
  }
  const parent = element.closest('label');
  if (parent) labels.push(parent);
  return labels.some(choiceVisible);
}

function optionVisible(element) {
  return choiceVisible(element) || (
    ['INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName) && associatedLabelVisible(element)
  );
}

function uniqueOptions(group) {
  const options = [];
  const seen = new Set();
  for (const option of choiceOptionElements(group)) {
    if (!optionVisible(option)) continue;
    const key = `${choiceSelectorHint(option)}|${choiceOptionText(option)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    options.push(option);
  }
  return options;
}

function optionState(option) {
  const label = choiceOptionText(option);
  const disabled = option.disabled === true || option.getAttribute('aria-disabled') === 'true';
  return {
    label,
    selected: choiceChecked(option),
    checked: choiceChecked(option),
    disabled,
    enabled: !disabled,
    tag: option.tagName.toLowerCase(),
    role: option.getAttribute('role') || choiceType(option),
    selector_hint: choiceSelectorHint(option),
    xpath_hint: structuralXPath(option),
    shadow_path: choiceShadowPath(option),
    frame_path: []
  };
}

const root = choiceRoot(request.scope);
const groups = choiceGroupsFor(root);
const choices = [];
for (const item of groups) {
  const options = uniqueOptions(item.group);
  if (options.length < 2) continue;
  const states = options.map(optionState);
  const selected = states.filter(option => option.selected);
  const required = item.group.required === true
    || item.group.getAttribute('aria-required') === 'true'
    || options.some(option => option.required === true || option.getAttribute('aria-required') === 'true');
  const enabled = states.every(option => option.enabled);
  const selectedState = selected.length === 1 ? 'selected' : selected.length > 1 ? 'indeterminate' : 'unselected';
  const label = choiceQuestionText(item.group, root)
    || choiceText(item.group.getAttribute('aria-label') || '')
    || states.map(option => option.label).filter(Boolean).join(' / ');
  choices.push({
    field_key: `${choiceSelectorHint(item.group)}|${label}`,
    field_label: label,
    tag: item.group.tagName.toLowerCase(),
    type: choiceType(options[0]) === 'checkbox' ? 'checkbox_group' : 'radio_group',
    role: item.group.getAttribute('role') || 'group',
    required,
    visible: true,
    enabled,
    selected_label: selected.length === 1 ? selected[0].label : '',
    selected_state: selectedState,
    checked: selected.length > 0,
    indeterminate: selected.length > 1,
    options: states,
    ready_for_submission: enabled && (!required || selectedState === 'selected'),
    blocker: required && selectedState !== 'selected' ? 'missing_required_choice' : '',
    selector_hint: choiceSelectorHint(item.group),
    xpath_hint: structuralXPath(item.group),
    shadow_path: choiceShadowPath(item.group),
    frame_path: []
  });
}
return {success: true, choices};
"""
    )


__all__ = ['choice_discovery_script', 'discover_choice_states']
