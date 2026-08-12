"""Post-click verification for semantic radio and checkbox interactions."""

from __future__ import annotations

import asyncio
import json

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_object
from pydoll_mcp_server.errors import StructuredError


async def wait_for_choice_state(
    client_id: str,
    tab_id: str,
    text: str,
    role: str,
    match_index: int | None,
    selector: str,
    timeout: float | None,
) -> bool:
    """Wait until a fresh native or ARIA choice node reports the requested state."""
    deadline = asyncio.get_running_loop().time() + min(max(timeout or 2.0, 0.1), 3.0)
    payload = json.dumps(
        {
            'text': text,
            'role': role,
            'match_index': match_index,
            'selector': selector,
        }
    )
    script = choice_state_script(payload)
    while asyncio.get_running_loop().time() < deadline:
        try:
            tab = get_registry().get_tab(client_id, tab_id).pydoll_tab
            result = await tab.execute_script(script, return_by_value=True)
            state = extract_normalized_object(result, 'choice_state')
            if state.get('selected') is True:
                return True
        except (StructuredError, PydollException, InvalidScriptResponseError, TypeError, ValueError):
            pass
        await asyncio.sleep(0.05)
    return False


def choice_state_script(payload_json: str) -> str:
    """Build a browser script that re-resolves a choice after React replaces its node."""
    return (
        'const request = '
        + payload_json
        + r""";
const normalize = value => String(value || '').trim().replace(/\s+/g, ' ').toLowerCase();
const visible = element => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none'
        && style.visibility !== 'hidden' && parseFloat(style.opacity || '1') > 0;
};
const checked = element => element.checked === true || element.getAttribute('aria-checked') === 'true';
const optionText = element => normalize(
    element.getAttribute('aria-label') || element.innerText || element.textContent || element.value || ''
);
let selectorMatch = null;
if (request.selector) {
    try {
        selectorMatch = document.querySelector(request.selector);
    } catch (_) {
        selectorMatch = null;
    }
}
if (selectorMatch && visible(selectorMatch) && checked(selectorMatch)) return {selected: true};
const candidates = [...document.querySelectorAll(
    'input[type="radio"], input[type="checkbox"], [role="radio"], [role="checkbox"]'
)].filter(element => visible(element)
    && (element.getAttribute('role') || element.type || '').toLowerCase() === request.role
    && optionText(element) === normalize(request.text));
if (Number.isInteger(request.match_index) && candidates[request.match_index]) {
    return {selected: checked(candidates[request.match_index])};
}
return {selected: candidates.length === 1 && checked(candidates[0])};
"""
    )
