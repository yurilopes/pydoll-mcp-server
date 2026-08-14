"""Semantic, review-gated form workflow tools for job applications."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from pydoll_mcp_server.dom.tree import page_screenshot
from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    get_array,
    get_bool,
    get_int,
    get_object,
    get_string,
    normalize_json_value,
)
from pydoll_mcp_server.tools.form_contracts import issue_review_token, token_summary, v2_envelope
from pydoll_mcp_server.tools.form_preflight_workflow import form_preflight
from pydoll_mcp_server.tools.form_prepare_support import hard_prepare_blockers, is_final_submit_text
from pydoll_mcp_server.tools.form_runtime import FormExecutionContext
from pydoll_mcp_server.tools.form_submit_workflow import form_submit_after_review
from pydoll_mcp_server.tools.form_workflow_helpers import (
    active_domain_restriction,
    domain_restriction_to_json,
    normalize_employer_domain,
    prepare_actions,
    record_domain_restriction,
)


async def application_domain_status(
    employer_domain: Annotated[str, Field(description='Explicit employer domain to inspect.')],
) -> JsonObject:
    domain = normalize_employer_domain(employer_domain)
    if not domain:
        return _error('application_domain_status', ErrorCode.INVALID_INPUT, 'A non-empty employer_domain is required.')
    restriction = active_domain_restriction(domain)
    result = v2_envelope('application_domain_status', 'blocked' if restriction else 'allowed')
    result.update(
        {
            'domain': domain,
            'restricted': restriction is not None,
            'restriction': domain_restriction_to_json(restriction) if restriction else {},
        }
    )
    return result


async def form_review(
    client_id: str,
    tab_id: str,
    scope: str = 'auto',
    do_not_touch: list[str] | None = None,
    employer_domain: str = '',
    capture_evidence: bool = True,
    preset: str = 'generic_form',
    force_refresh: bool = False,
) -> JsonObject:
    preflight = await form_preflight(
        client_id=client_id,
        tab_id=tab_id,
        scope=scope,
        do_not_touch=do_not_touch,
        employer_domain=employer_domain,
        include_values=False,
        preset=preset,
        force_refresh=force_refresh,
    )
    if not preflight.get('success'):
        return preflight
    return await _review_from_preflight(
        client_id,
        tab_id,
        preflight,
        employer_domain=employer_domain,
        capture_evidence=capture_evidence,
    )


async def _review_from_preflight(
    client_id: str,
    tab_id: str,
    preflight: JsonObject,
    employer_domain: str,
    capture_evidence: bool,
) -> JsonObject:
    screenshot: JsonObject = {}
    warnings = get_array(preflight, 'warnings', [])
    if capture_evidence:
        screenshot = await page_screenshot(
            client_id,
            tab_id,
            full_page=True,
            evidence_kind='pre_submission_review',
        )
        if not screenshot.get('success'):
            warnings.append({'kind': 'screenshot', 'message': screenshot.get('message', 'capture failed')})
            screenshot = {}
    review = v2_envelope('form_review', get_string(preflight, 'status', 'inconclusive'))
    review.update(
        {
            'stage': get_string(preflight, 'stage', ''),
            'fields': get_array(preflight, 'fields', []),
            'choices': get_array(preflight, 'choices', []),
            'choice_states': get_array(preflight, 'choice_states', []),
            'upload_states': get_array(preflight, 'upload_states', []),
            'pending_required': get_array(preflight, 'pending_required', []),
            'security_controls': get_array(preflight, 'security_controls', []),
            'attestation_handoffs': get_array(preflight, 'attestation_handoffs', []),
            'primary_action': preflight.get('primary_action', {}),
            'blockers': get_array(preflight, 'blockers', []),
            'errors': get_array(preflight, 'errors', []),
            'warnings': warnings,
            'partial': get_bool(preflight, 'partial', False),
            'form_fingerprint': get_string(preflight, 'form_fingerprint', ''),
            'document_generation': get_int(preflight, 'document_generation', 0),
            'mutation_epoch': get_int(preflight, 'mutation_epoch', 0),
            'snapshot_id': get_string(preflight, 'snapshot_id', ''),
            'preset': get_string(preflight, 'preset', 'generic_form'),
            'employer_domain': get_string(preflight, 'employer_domain', ''),
            'ready_for_submission': get_bool(preflight, 'ready_for_submission', False),
            'performance': preflight.get('performance', {}),
            'screenshot': screenshot,
        }
    )
    if get_bool(review, 'ready_for_submission', False):
        record = issue_review_token(
            client_id,
            tab_id,
            get_int(review, 'document_generation', 0),
            get_string(review, 'form_fingerprint', ''),
            review,
            mutation_epoch=get_int(review, 'mutation_epoch', 0),
            snapshot_id=get_string(review, 'snapshot_id', ''),
        )
        review.update(token_summary(record))
    return review


async def form_prepare(
    client_id: str,
    tab_id: str,
    fields: list[dict[str, object]] | None = None,
    choices: list[dict[str, object]] | None = None,
    comboboxes: list[dict[str, object]] | None = None,
    uploads: list[dict[str, object]] | None = None,
    steps: list[dict[str, object]] | None = None,
    do_not_touch: list[str] | None = None,
    scope: str = 'auto',
    advance_steps: bool = False,
    employer_domain: str = '',
    capture_evidence: bool = True,
    timeout: float | None = None,
    preset: str = 'generic_form',
) -> JsonObject:
    del timeout
    field_plans = _json_object_list(fields or [])
    choice_plans = _json_object_list(choices or [])
    combo_plans = _json_object_list(comboboxes or [])
    upload_plans = _json_object_list(uploads or [])
    step_plans = _json_object_list(steps or [])
    initial = await form_preflight(
        client_id,
        tab_id,
        scope=scope,
        planned_fields=fields,
        planned_choices=choices,
        planned_comboboxes=comboboxes,
        planned_uploads=uploads,
        do_not_touch=do_not_touch,
        employer_domain=employer_domain,
        preset=preset,
    )
    if not initial.get('success'):
        return initial
    execution = FormExecutionContext(client_id=client_id, tab_id=tab_id, scope=scope, preset=preset)
    execution.document_generation = get_int(initial, 'document_generation', 0)
    execution.mutation_epoch = get_int(initial, 'mutation_epoch', 0)
    execution.set_snapshot(initial, get_string(initial, 'form_fingerprint', ''))
    _absorb_performance(execution, get_object(initial, 'performance', {}))
    execution.trace_event('discovery', 'form_preflight', get_string(initial, 'status', 'inconclusive'))
    hard_blockers = hard_prepare_blockers(initial, [*field_plans, *combo_plans, *upload_plans])
    if hard_blockers:
        execution.trace_event('policy', 'form_prepare', 'blocked')
        result = _merge_envelope(initial, 'form_prepare', 'blocked', True)
        result.update({'blockers': hard_blockers, 'handoff': True})
        return result

    actions: JsonArray = []
    step_results: JsonArray = []
    observed_fields = get_array(initial, 'fields', [])
    if field_plans or choice_plans or combo_plans or upload_plans:
        actions.extend(
            await prepare_actions(
                client_id,
                tab_id,
                field_plans,
                choice_plans,
                combo_plans,
                upload_plans,
                observed_fields,
                do_not_touch or [],
                preset,
            )
        )
        _count_action_round_trips(execution, actions)
        execution.trace_event('mutation', 'form_actions', 'completed')
    for step in step_plans:
        step_fields = _json_object_list(step.get('fields', []))
        step_choices = _json_object_list(step.get('choices', []))
        step_combos = _json_object_list(step.get('comboboxes', []))
        step_uploads = _json_object_list(step.get('uploads', []))
        step_result: JsonObject = {'step_key': str(step.get('step_key', '')), 'actions': [], 'transition': {}}
        step_actions = await prepare_actions(
            client_id,
            tab_id,
            step_fields,
            step_choices,
            step_combos,
            step_uploads,
            observed_fields,
            do_not_touch or [],
            preset,
        )
        step_result['actions'] = step_actions
        actions.extend(step_actions)
        _count_action_round_trips(execution, step_actions)
        if advance_steps:
            action_text = _json_string_list(step.get('advance_action_text_any', []))
            if action_text and any(is_final_submit_text(item) for item in action_text):
                step_result['transition'] = {
                    'status': 'blocked',
                    'reason': 'The requested step action resembles a final submit.',
                }
            elif action_text:
                from pydoll_mcp_server.tools.primary_action import page_click_primary_action

                transition = await page_click_primary_action(
                    client_id,
                    tab_id,
                    scope=scope,
                    button_text_any=action_text,
                    timeout=5.0,
                )
                step_result['transition'] = transition
                actions.append({'kind': 'step_transition', 'step_key': step_result['step_key'], 'result': transition})
                execution.performance.browser_call()
        step_results.append(step_result)
        transition = get_object(step_result, 'transition', {})
        if get_bool(transition, 'success', False):
            refreshed = await form_preflight(client_id, tab_id, scope=scope, preset=preset)
            _absorb_performance(execution, get_object(refreshed, 'performance', {}))
            observed_fields = get_array(refreshed, 'fields', observed_fields)
            execution.trace_event('discovery', 'step_transition', get_string(refreshed, 'status', 'inconclusive'))

    final_preflight = await form_preflight(
        client_id,
        tab_id,
        scope=scope,
        do_not_touch=do_not_touch,
        employer_domain=employer_domain,
        preset=preset,
    )
    if not final_preflight.get('success'):
        return final_preflight
    _absorb_performance(execution, get_object(final_preflight, 'performance', {}))
    execution.trace_event('verification', 'form_preflight', get_string(final_preflight, 'status', 'inconclusive'))
    execution.document_generation = get_int(final_preflight, 'document_generation', execution.document_generation)
    execution.mutation_epoch = get_int(final_preflight, 'mutation_epoch', execution.mutation_epoch)
    execution.set_snapshot(final_preflight, get_string(final_preflight, 'form_fingerprint', ''))
    review = await _review_from_preflight(
        client_id,
        tab_id,
        final_preflight,
        employer_domain=employer_domain,
        capture_evidence=capture_evidence,
    )
    result = _merge_envelope(review, 'form_prepare', get_string(review, 'status', 'inconclusive'), True)
    result.update(
        {
            'actions': actions,
            'steps': step_results,
            'review': review,
            'trace': list(execution.trace),
            'performance': execution.performance_json(),
            'snapshot_id': execution.snapshot_id,
            'document_generation': execution.document_generation,
            'mutation_epoch': execution.mutation_epoch,
            'preset': preset,
        }
    )
    if get_string(review, 'review_token', ''):
        result['review_token'] = get_string(review, 'review_token', '')
    return result


def _error(operation: str, code: ErrorCode, message: str, details: JsonObject | None = None) -> JsonObject:
    return _merge_envelope(StructuredError(code, message, details=details or {}).to_dict(), operation, 'blocked', False)


def _merge_envelope(value: JsonObject, operation: str, status: str, success: bool) -> JsonObject:
    result = dict(value)
    result.update(v2_envelope(operation, status, success))
    return result


def _json_object_list(value: object) -> list[JsonObject]:
    normalized_value = normalize_json_value(value, 'form plan list')
    if not isinstance(normalized_value, list):
        return []
    return [item for item in normalized_value if isinstance(item, dict)]


def _json_string_list(value: object) -> list[str]:
    normalized_value = normalize_json_value(value, 'form string list')
    if not isinstance(normalized_value, list):
        return []
    return [item for item in normalized_value if isinstance(item, str)]


def _absorb_performance(execution: FormExecutionContext, value: JsonObject) -> None:
    execution.performance.absorb(value)


def _count_action_round_trips(execution: FormExecutionContext, actions: JsonArray) -> None:
    saved = 0
    for action in actions:
        if not isinstance(action, dict):
            continue
        kind = get_string(action, 'kind', '')
        result = get_object(action, 'result', {})
        action_performance = get_object(result, 'performance', {})
        if action_performance:
            execution.performance.absorb(action_performance)
        else:
            execution.performance.browser_call()
        if kind == 'fields_batch':
            saved += max(0, len(get_array(result, 'filled', [])) - 1)
        elif kind == 'choices_batch':
            saved += max(0, len(get_array(result, 'choices', [])) - 1)
    execution.performance.round_trips_saved += saved


__all__ = [
    'application_domain_status',
    'form_preflight',
    'form_prepare',
    'form_review',
    'form_submit_after_review',
    'normalize_employer_domain',
    'record_domain_restriction',
]
