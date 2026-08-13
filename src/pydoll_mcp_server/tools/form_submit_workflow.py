"""Final submission operation guarded by a short-lived review token."""

from __future__ import annotations

import time
from typing import Annotated, Literal

from pydantic import Field

from pydoll_mcp_server.browser.registry import get_registry
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject, get_array, get_bool, get_string
from pydoll_mcp_server.tools.elements import element_click
from pydoll_mcp_server.tools.form_contracts import consume_review_token, get_review_token
from pydoll_mcp_server.tools.form_workflow_helpers import is_final_submit_text, record_domain_restriction
from pydoll_mcp_server.tools.submission import submission_wait_for_confirmation


async def form_submit_after_review(
    client_id: str,
    tab_id: str,
    review_token: str,
    authorization_mode: Annotated[
        Literal['session_autonomous', 'user_approved'],
        Field(description='Explicit authorization: session_autonomous or user_approved.'),
    ],
    timeout: float | None = None,
) -> JsonObject:
    from pydoll_mcp_server.tools.form_workflow import form_review

    if authorization_mode not in {'session_autonomous', 'user_approved'}:
        return _error(
            'authorization_mode must be session_autonomous or user_approved.',
            ErrorCode.SUBMISSION_AUTHORIZATION_REQUIRED,
        )
    record = get_review_token(review_token)
    if record is None or record.client_id != client_id or record.tab_id != tab_id:
        return _error(
            'Review token is expired, used, or scoped to another client or tab.', ErrorCode.REVIEW_TOKEN_INVALID
        )
    try:
        tab_info = get_registry().get_tab(client_id, tab_id)
    except StructuredError as exc:
        return _merge_envelope(exc.to_dict(), 'blocked', False)
    if tab_info.document_generation != record.document_generation:
        return _error(
            'The document changed after review.',
            ErrorCode.REVIEW_TOKEN_INVALID,
            {'expected_generation': record.document_generation, 'actual_generation': tab_info.document_generation},
        )
    employer_domain = get_string(record.review, 'employer_domain', '')
    review = await form_review(client_id, tab_id, employer_domain=employer_domain, capture_evidence=True)
    if not review.get('success'):
        return review
    current_fingerprint = get_string(review, 'form_fingerprint', '')
    if current_fingerprint != record.form_fingerprint:
        return _error(
            'The form changed after review.',
            ErrorCode.REVIEW_TOKEN_INVALID,
            {'expected_fingerprint': record.form_fingerprint, 'actual_fingerprint': current_fingerprint},
        )
    if not get_bool(review, 'ready_for_submission', False):
        return _merge_envelope(
            {'blockers': get_array(review, 'blockers', []), 'review': review, 'handoff': True},
            'blocked',
            True,
        )
    primary = review.get('primary_action') if isinstance(review.get('primary_action'), dict) else {}
    primary_id = get_string(primary if isinstance(primary, dict) else {}, 'element_id', '')
    primary_name = get_string(primary if isinstance(primary, dict) else {}, 'name', '')
    if not primary_id or not is_final_submit_text(primary_name):
        return _error(
            'The reviewed primary action is not an explicit final submit action.',
            ErrorCode.FORM_NOT_READY,
            {'primary_action': primary or {}},
        )

    consumed = consume_review_token(review_token)
    if consumed is None:
        return _error('The review token was already used.', ErrorCode.REVIEW_TOKEN_INVALID)
    record = consumed
    click_result = await element_click(client_id, tab_id, primary_id, timeout=timeout, click_strategy='auto')
    attempt_id = f'submit_{int(time.time() * 1000)}'
    if not click_result.get('success'):
        result = _merge_envelope(click_result, 'unknown', False)
        result.update({'submission_attempt_id': attempt_id, 'outcome': 'unknown', 'confirmed': False, 'handoff': True})
        return result
    confirmation = await submission_wait_for_confirmation(
        client_id,
        tab_id,
        success_text_any=[
            'application submitted',
            'application successfully submitted',
            'application was successfully submitted',
            'your application was successfully submitted',
            'your application has been successfully submitted',
            'thank you for applying',
            'thanks for applying',
            'received your application',
            'candidatura enviada',
            'inscrição recebida',
        ],
        status_text_any=[
            'captcha',
            'verify your identity',
            'sign in',
            'required field',
            'application limit',
            'already applied',
            'cannot submit',
        ],
        expect_url_change=False,
        timeout=timeout,
        capture_evidence=True,
    )
    outcome = get_string(confirmation, 'outcome', get_string(confirmation, 'status', 'unknown'))
    if outcome == 'portal_limit' and employer_domain:
        evidence_values = confirmation.get('evidence_text')
        evidence = (
            [item for item in evidence_values if isinstance(item, str)] if isinstance(evidence_values, list) else []
        )
        confirmation['domain_restriction'] = record_domain_restriction(
            employer_domain,
            'portal_limit',
            evidence,
        )
    result = _merge_envelope(confirmation, outcome, True)
    result.update(
        {
            'submission_attempt_id': attempt_id,
            'outcome': outcome,
            'confirmed': outcome == 'confirmed',
            'review_token_consumed': record.consumed,
            'pre_submit_review': review,
            'click': click_result,
        }
    )
    return result


def _error(
    message: str, code: ErrorCode = ErrorCode.SUBMISSION_AUTHORIZATION_REQUIRED, details: JsonObject | None = None
) -> JsonObject:
    return _merge_envelope(StructuredError(code, message, details=details or {}).to_dict(), 'blocked', False)


def _merge_envelope(value: JsonObject, status: str, success: bool) -> JsonObject:
    result = dict(value)
    result.update(
        {
            'contract_version': 2,
            'operation_id': f'submit_{int(time.time() * 1000)}',
            'success': success,
            'status': status,
        }
    )
    return result


__all__ = ['form_submit_after_review']
