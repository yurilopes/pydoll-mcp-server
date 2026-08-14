"""Typed submission outcome detection with conservative confirmation rules."""

from __future__ import annotations

import asyncio
import time
import uuid
from enum import Enum
from typing import Annotated

from pydantic import Field
from pydoll.browser.tab import Tab
from pydoll.exceptions import PydollException

from pydoll_mcp_server.browser.pydoll_compat import get_tab_url
from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.browser.script_utils import InvalidScriptResponseError, extract_normalized_string
from pydoll_mcp_server.dom.tree import page_screenshot
from pydoll_mcp_server.errors import StructuredError
from pydoll_mcp_server.json_types import JsonArray, JsonObject


class SubmissionOutcome(str, Enum):
    CONFIRMED = 'confirmed'
    VALIDATION_FAILED = 'validation_failed'
    PORTAL_LIMIT = 'portal_limit'
    AUTHENTICATION_REQUIRED = 'authentication_required'
    SECURITY_CHALLENGE = 'security_challenge'
    REQUIRES_CANDIDATE_CONFIRMATION = 'requires_candidate_confirmation'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'
    UNKNOWN = 'unknown'


_SECURITY_MARKERS = ('captcha', 'recaptcha', 'hcaptcha', 'turnstile', 'security check', 'challenge')
_AUTH_MARKERS = ('sign in', 'log in', 'login required', 'authentication required', 'session expired')
_ATTESTATION_MARKERS = (
    'attest',
    'certify',
    'consent',
    'legal declaration',
    'terms and conditions',
    'application terms',
)
_LIMIT_MARKERS = (
    'application limit',
    'too many applications',
    'already applied',
    'limit reached',
    'maximum applications',
)
_VALIDATION_MARKERS = (
    'required field',
    'field is required',
    'invalid field',
    'please correct',
    'error',
    'cannot submit',
)
_REJECTION_MARKERS = ('application rejected', 'not selected', 'no longer accepting')
_CANCEL_MARKERS = ('cancelled', 'canceled', 'application withdrawn')
_VALIDATION_SETTLE_GRACE_SECONDS = 4.0


async def submission_wait_for_confirmation(
    client_id: str,
    tab_id: str,
    success_text_any: Annotated[
        list[str] | None,
        Field(description='Text patterns that prove a successful submission on a visible surface.'),
    ] = None,
    status_text_any: Annotated[
        list[str] | None,
        Field(description='Text patterns that describe submitted, blocked, or uncertain status.'),
    ] = None,
    button_text_any: Annotated[
        list[str] | None,
        Field(description='Button text patterns used as additional evidence.'),
    ] = None,
    expect_url_change: Annotated[
        bool, Field(description='Observe URL change but never use it alone as confirmation.')
    ] = False,
    expect_modal_gone: Annotated[
        bool, Field(description='Observe modal closure but never use it alone as confirmation.')
    ] = False,
    card_selector: Annotated[str, Field(description='Optional CSS selector for a result card to inspect.')] = '',
    timeout: Annotated[float | None, Field(description='Maximum confirmation wait in seconds.')] = None,
    capture_evidence: Annotated[bool, Field(description='Capture a screenshot artifact after classification.')] = False,
) -> JsonObject:
    del card_selector
    success_texts = [item.casefold() for item in success_text_any or [] if item.strip()]
    status_texts = [item.casefold() for item in status_text_any or [] if item.strip()]
    button_texts = [item.casefold() for item in button_text_any or [] if item.strip()]
    limit = min(timeout or 15.0, 60.0)
    deadline = time.monotonic() + limit
    attempt_id = f'submission_{uuid.uuid4().hex[:16]}'

    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return exc.to_dict()

    pre_url = await get_tab_url(tab_info.pydoll_tab) or ''
    evidence_text: list[str] = []
    matched_patterns: list[str] = []
    url_changed = False
    modal_gone = False
    outcome = SubmissionOutcome.UNKNOWN
    body = ''
    validation_started_at: float | None = None
    poll_delay = 0.12

    while time.monotonic() < deadline:
        body = await _visible_body_text(tab_info.pydoll_tab)
        body_lower = body.casefold()
        evidence_text = _matching_text(body_lower, success_texts, status_texts, button_texts)
        matched_patterns = _matching_kinds(body_lower, success_texts, status_texts, button_texts)
        url_changed = bool(expect_url_change and (await get_tab_url(tab_info.pydoll_tab) or '') != pre_url)
        if expect_modal_gone:
            modal_gone = not bool(await _visible_dialog_text(tab_info.pydoll_tab))

        outcome = classify_submission_outcome(body_lower, success_texts, status_texts)
        if outcome is SubmissionOutcome.VALIDATION_FAILED and success_texts:
            if validation_started_at is None:
                validation_started_at = time.monotonic()
            if any(text in body_lower for text in success_texts):
                outcome = SubmissionOutcome.CONFIRMED
                break
            if time.monotonic() - validation_started_at < min(_VALIDATION_SETTLE_GRACE_SECONDS, limit):
                await asyncio.sleep(poll_delay)
                poll_delay = min(1.0, poll_delay * 1.5)
                continue
        if outcome is not SubmissionOutcome.UNKNOWN or (url_changed and not expect_url_change and modal_gone):
            break
        if outcome is SubmissionOutcome.UNKNOWN and not (url_changed or modal_gone):
            await asyncio.sleep(poll_delay)
            poll_delay = min(1.0, poll_delay * 1.5)
        else:
            break

    if outcome is SubmissionOutcome.UNKNOWN and time.monotonic() >= deadline:
        outcome = SubmissionOutcome.UNKNOWN
    status = _legacy_status(outcome, url_changed, modal_gone)
    post_url = await get_tab_url(tab_info.pydoll_tab) or ''
    screenshot: JsonObject = {}
    if capture_evidence:
        screenshot = await page_screenshot(
            client_id,
            tab_id,
            full_page=True,
            evidence_kind='submission_confirmation' if outcome is SubmissionOutcome.CONFIRMED else 'diagnostic',
        )
    evidence: JsonObject = {
        'timestamp': time.time(),
        'outcome': outcome.value,
        'url_before': pre_url,
        'url_after': post_url,
        'url_changed': url_changed,
        'modal_gone': modal_gone,
        'surface': 'active_application_surface',
    }
    return {
        'contract_version': 2,
        'operation_id': f'submission_wait_{uuid.uuid4().hex[:16]}',
        'success': True,
        'status': status,
        'outcome': outcome.value,
        'confirmed': outcome is SubmissionOutcome.CONFIRMED,
        'evidence_text': _text_array(evidence_text),
        'url_changed': url_changed,
        'modal_gone': modal_gone,
        'matched_patterns': _text_array(matched_patterns),
        'submission_attempt_id': attempt_id,
        'warnings': _warnings(outcome, url_changed, modal_gone),
        'evidence': evidence,
        'screenshot': screenshot,
    }


def classify_submission_outcome(body: str, success_texts: list[str], status_texts: list[str]) -> SubmissionOutcome:
    """Apply the safety precedence before considering positive confirmation text."""

    if any(marker in body for marker in _SECURITY_MARKERS):
        return SubmissionOutcome.SECURITY_CHALLENGE
    if any(marker in body for marker in _AUTH_MARKERS):
        return SubmissionOutcome.AUTHENTICATION_REQUIRED
    if any(marker in body for marker in _ATTESTATION_MARKERS):
        return SubmissionOutcome.REQUIRES_CANDIDATE_CONFIRMATION
    if any(marker in body for marker in _LIMIT_MARKERS):
        return SubmissionOutcome.PORTAL_LIMIT
    if any(marker in body for marker in _VALIDATION_MARKERS):
        return SubmissionOutcome.VALIDATION_FAILED
    if any(marker in body for marker in _REJECTION_MARKERS):
        return SubmissionOutcome.REJECTED
    if any(marker in body for marker in _CANCEL_MARKERS):
        return SubmissionOutcome.CANCELLED
    if any(text in body for text in success_texts):
        return SubmissionOutcome.CONFIRMED
    if any(text in body for text in status_texts):
        return SubmissionOutcome.UNKNOWN
    return SubmissionOutcome.UNKNOWN


async def _visible_body_text(tab: Tab) -> str:
    try:
        result = await tab.execute_script(
            """
            (() => {
                const visible = (element) => {
                    if (!element) return false;
                    const rect = element.getBoundingClientRect();
                    const style = getComputedStyle(element);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none' && style.visibility !== 'hidden'
                        && parseFloat(style.opacity || '1') > 0;
                };
                const candidates = [
                    ...document.querySelectorAll(
                        '[role="dialog"], dialog[open], [aria-modal="true"], form, main, [role="main"]'
                    )
                ].filter(visible);
                const dialog = candidates.find((element) =>
                    element.matches('[role="dialog"], dialog[open], [aria-modal="true"]')
                );
                const surface = dialog || candidates.find((element) => element.matches('form'))
                    || candidates.find((element) => element.matches('main,[role="main"]'))
                    || document.body;
                return surface ? (surface.innerText || surface.textContent || '') : '';
            })()
            """,
            return_by_value=True,
        )
        return extract_normalized_string(result, 'submission_visible_body')
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        return ''


async def _visible_dialog_text(tab: Tab) -> str:
    try:
        result = await tab.execute_script(
            'const d=document.querySelector(\'[role="dialog"],dialog[open],[aria-modal="true"]\');'
            "return d ? (d.innerText || d.textContent || '') : '';",
            return_by_value=True,
        )
        return extract_normalized_string(result, 'submission_visible_dialog')
    except (PydollException, InvalidScriptResponseError, TypeError, ValueError):
        return ''


def _matching_text(body: str, *groups: list[str]) -> list[str]:
    return [text for group in groups for text in group if text in body]


def _matching_kinds(body: str, success: list[str], status: list[str], buttons: list[str]) -> list[str]:
    kinds: list[str] = []
    if any(item in body for item in success):
        kinds.append('success_text_any')
    if any(item in body for item in status):
        kinds.append('status_text_any')
    if any(item in body for item in buttons):
        kinds.append('button_text_any')
    for name, markers in (
        ('security', _SECURITY_MARKERS),
        ('authentication', _AUTH_MARKERS),
        ('attestation', _ATTESTATION_MARKERS),
        ('portal_limit', _LIMIT_MARKERS),
        ('validation', _VALIDATION_MARKERS),
    ):
        if any(marker in body for marker in markers):
            kinds.append(name)
    return kinds


def _legacy_status(outcome: SubmissionOutcome, url_changed: bool, modal_gone: bool) -> str:
    if outcome is SubmissionOutcome.CONFIRMED:
        return 'confirmed'
    if outcome in {
        SubmissionOutcome.SECURITY_CHALLENGE,
        SubmissionOutcome.AUTHENTICATION_REQUIRED,
        SubmissionOutcome.REQUIRES_CANDIDATE_CONFIRMATION,
        SubmissionOutcome.PORTAL_LIMIT,
        SubmissionOutcome.VALIDATION_FAILED,
    }:
        return 'blocked'
    if outcome is SubmissionOutcome.UNKNOWN and (url_changed or modal_gone):
        return 'submitted_uncertain'
    if outcome is SubmissionOutcome.UNKNOWN:
        return 'failed'
    return 'failed'


def _warnings(outcome: SubmissionOutcome, url_changed: bool, modal_gone: bool) -> JsonArray:
    warnings: JsonArray = []
    if outcome is SubmissionOutcome.UNKNOWN and (url_changed or modal_gone):
        warnings.append('Navigation or modal closure was observed without high-confidence confirmation text.')
    if outcome is not SubmissionOutcome.CONFIRMED:
        warnings.append(f'Submission outcome is {outcome.value}; do not retry without reviewing the evidence.')
    return warnings


def _text_array(values: list[str]) -> JsonArray:
    return list(values)


__all__ = ['SubmissionOutcome', 'classify_submission_outcome', 'submission_wait_for_confirmation']
