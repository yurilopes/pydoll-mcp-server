"""Submission confirmation tool with structured status detection."""

from __future__ import annotations

import asyncio
import time

from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.pydoll_compat import get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_script_string
from pydoll_mcp_server.errors import StructuredError
from pydoll_mcp_server.json_types import JsonObject


async def submission_wait_for_confirmation(
    client_id: str,
    tab_id: str,
    success_text_any: list[str] | None = None,
    status_text_any: list[str] | None = None,
    button_text_any: list[str] | None = None,
    expect_url_change: bool = False,
    expect_modal_gone: bool = False,
    card_selector: str = '',
    timeout: float | None = None,
) -> JsonObject:
    success_texts = success_text_any or []
    status_texts = status_text_any or []
    button_texts = button_text_any or []

    limit = min(timeout or 15.0, 60.0)
    deadline = time.monotonic() + limit

    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    pre_url = await get_tab_url(tab_info.pydoll_tab) or ''
    confirmed = False
    evidence_text: list[str] = []
    url_changed = False
    modal_gone = False
    matched_patterns: list[str] = []
    status = 'submitted_uncertain'

    while time.monotonic() < deadline:
        try:
            page_text = await tab_info.pydoll_tab.execute_script(
                "return document.body.innerText || '';",
                return_by_value=True,
            )
            body = extract_script_string(page_text)
        except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
            body = ''

        body_lower = body.lower()

        for pattern in success_texts:
            if pattern.lower() in body_lower:
                confirmed = True
                evidence_text.append(pattern)
                matched_patterns.append('success_text_any')

        if not confirmed:
            for pattern in status_texts:
                if pattern.lower() in body_lower:
                    status = (
                        'blocked'
                        if 'error' in pattern.lower() or 'required' in pattern.lower()
                        else 'submitted_uncertain'
                    )
                    evidence_text.append(pattern)
                    matched_patterns.append('status_text_any')

        for pattern in button_texts:
            if pattern.lower() in body_lower:
                matched_patterns.append('button_text_any')

        if expect_url_change:
            current_url = await get_tab_url(tab_info.pydoll_tab) or ''
            if current_url != pre_url:
                url_changed = True
                matched_patterns.append('expect_url_change')

        if expect_modal_gone:
            try:
                dialog_result = await tab_info.pydoll_tab.execute_script(
                    'const d=document.querySelector(\'[role="dialog"]:not([style*="display: none"])'
                    ', dialog[open], [aria-modal="true"]\');'
                    "return d ? d.getAttribute('aria-label') || d.tagName : '';",
                    return_by_value=True,
                )
                dialog_text = extract_script_string(dialog_result)
                if not dialog_text:
                    modal_gone = True
                    matched_patterns.append('expect_modal_gone')
            except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
                pass

        if confirmed or (url_changed and expect_url_change) or (modal_gone and expect_modal_gone):
            break

        await asyncio.sleep(0.3)

    if confirmed:
        status = 'confirmed'
    elif url_changed or modal_gone:
        status = 'submitted_uncertain'
    elif status == 'blocked':
        pass
    elif time.monotonic() >= deadline:
        status = 'failed'

    evidence: JsonObject = {
        'timestamp': time.time(),
        'status': status,
        'url_changed': url_changed,
        'modal_gone': modal_gone,
    }

    result: JsonObject = {
        'success': True,
        'status': status,
        'confirmed': confirmed,
        'evidence_text': list(evidence_text),
        'url_changed': url_changed,
        'modal_gone': modal_gone,
        'matched_patterns': list(matched_patterns),
        'warnings': [],
        'evidence': evidence,
    }
    return result
