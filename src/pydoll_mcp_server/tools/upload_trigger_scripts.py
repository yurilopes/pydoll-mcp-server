"""Small page scripts used by generic upload trigger orchestration."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Protocol

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_object
from pydoll_mcp_server.json_types import JsonObject, get_bool


class UploadTriggerElement(Protocol):
    """Element operations required by upload verification scripts."""

    async def execute_script(self, script: str, *, return_by_value: bool | None = None) -> object: ...

    async def click(self) -> None: ...


async def inspect_upload_surface(trigger: UploadTriggerElement) -> JsonObject:
    """Inspect file input and native picker signals around the trigger."""

    response = await trigger.execute_script(
        """
        const localRoot = this.closest('form, dialog, [role="dialog"]') || document;
        const allInputs = [...document.querySelectorAll('input[type="file"]')];
        const localInputs = [...localRoot.querySelectorAll('input[type="file"]')];
        const triggerIsInput = this.matches && this.matches('input[type="file"]');
        const selectorFor = (node) => {
            const parts = [];
            let current = node;
            while (current && current.nodeType === 1) {
                let index = 1;
                let sibling = current.previousElementSibling;
                while (sibling) {
                    if (sibling.tagName === current.tagName) index += 1;
                    sibling = sibling.previousElementSibling;
                }
                parts.unshift(`${current.tagName.toLowerCase()}:nth-of-type(${index})`);
                current = current.parentElement;
            }
            return parts.join(' > ');
        };
        const relatedInput = localInputs.length === 1 ? localInputs[0] : null;
        return {
            file_input_count: allInputs.length,
            local_file_input_count: localInputs.length + (triggerIsInput && !localInputs.includes(this) ? 1 : 0),
            trigger_is_file_input: Boolean(triggerIsInput),
            related_input_selector: relatedInput ? selectorFor(relatedInput) : '',
            file_system_access_api_available: typeof window.showOpenFilePicker === 'function'
        };
        """,
        return_by_value=True,
    )
    return extract_script_object(response)


async def wait_for_upload_verification(
    trigger: UploadTriggerElement,
    expected_filenames: list[str],
    timeout_ms: int,
) -> JsonObject:
    """Poll for filename, input state, or explicit upload status evidence."""

    names_literal = json.dumps([name.casefold() for name in expected_filenames])
    deadline = time.monotonic() + max(1, timeout_ms) / 1000
    latest: JsonObject = {}
    while time.monotonic() < deadline:
        try:
            response = await trigger.execute_script(
                f"""
                const names = {names_literal};
                const root = this.closest('form, dialog, [role="dialog"]') || document;
                const text = (root.innerText || root.textContent || '').toLowerCase();
                const filenameVisible = names.some((name) => text.includes(name));
                const inputFiles = [...root.querySelectorAll('input[type="file"]')]
                    .reduce((count, input) => count + ((input.files || []).length), 0);
                const statusText = [...root.querySelectorAll('[role="status"], [aria-live], .toast, [class*="toast"]')]
                    .map((node) => node.innerText || node.textContent || '').join(' ').trim();
                const statusNormalized = statusText.toLowerCase();
                const statusTokens = [
                    'uploaded', 'upload complete', 'carregado', 'anexado',
                    'attached', 'selected', 'selecionado'
                ];
                const failureTokens = [
                    'upload failed', 'cannot open', 'file was rejected',
                    'system files', 'falha no upload',
                    'n\\u00e3o \\u00e9 poss\\u00edvel abrir', 'arquivos do sistema'
                ];
                const statusConfirmed = statusTokens.some((token) => statusNormalized.includes(token));
                const failureDetected = failureTokens.some((token) => statusNormalized.includes(token));
                return {{
                    filename_visible: filenameVisible,
                    input_file_count: inputFiles,
                    status_text: statusText,
                    status_confirmed: statusConfirmed,
                    failure_detected: failureDetected,
                    failure_text: failureDetected ? statusText : '',
                    upload_confirmed: !failureDetected && (filenameVisible || inputFiles > 0 || statusConfirmed)
                }};
                """,
                return_by_value=True,
            )
            latest = extract_script_object(response)
            if get_bool(latest, 'upload_confirmed') or get_bool(latest, 'failure_detected'):
                return latest
        except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
            pass
        await asyncio.sleep(0.2)
    latest.setdefault('upload_confirmed', False)
    return latest


__all__ = ['UploadTriggerElement', 'inspect_upload_surface', 'wait_for_upload_verification']
