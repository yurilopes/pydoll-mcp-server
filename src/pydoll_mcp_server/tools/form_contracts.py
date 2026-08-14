"""Shared v2 contracts and short-lived state for application form workflows."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Literal, TypedDict

from pydoll_mcp_server.json_types import JsonArray, JsonObject, JsonValue

Verification = Literal['verified', 'inconclusive', 'failed']
FormStatus = Literal['ready', 'blocked', 'inconclusive', 'completed']


class FormFieldPlan(TypedDict, total=False):
    """Caller-provided hints and value for one form field."""

    field_key: str
    label_contains: str
    question_contains: str
    placeholder_contains: str
    selector: str
    element_id: str
    role: str
    name: str
    value: JsonValue
    checked: bool
    option_text: str
    mode: str
    state_verification: str


class ChoicePlan(TypedDict, total=False):
    field_key: str
    field_label: str
    element_id: str
    option_label: str
    option_text: str
    checked: bool
    scope: str


class ComboboxPlan(TypedDict, total=False):
    field_key: str
    element_id: str
    query: str
    option_text: str
    exact: bool
    allow_approximate: bool


class UploadPlan(TypedDict, total=False):
    field_key: str
    element_id: str
    paths: list[str]
    expected_filenames: list[str]
    replace_existing: bool


class FormStepPlan(TypedDict, total=False):
    step_key: str
    fields: list[FormFieldPlan]
    choices: list[ChoicePlan]
    comboboxes: list[ComboboxPlan]
    uploads: list[UploadPlan]
    advance_action_text_any: list[str]


class FieldState(TypedDict, total=False):
    field_key: str
    label: str
    tag: str
    type: str
    role: str
    required: bool
    visible: bool
    enabled: bool
    read_only: bool
    value_present: bool
    value_length: int
    dom_value: str
    framework_value: str
    framework_event: bool
    controlled_value_survived: bool
    blurred: bool
    validity: str
    errors: JsonArray
    selected_label: str
    selected_value: str
    checked: bool
    indeterminate: bool
    ready_for_submission: bool
    verification: str
    blocker: str
    element_id: str
    selector_hint: str
    frame_path: list[str]
    shadow_path: list[str]


@dataclass
class ReviewTokenRecord:
    token: str
    client_id: str
    tab_id: str
    document_generation: int
    form_fingerprint: str
    expires_at: float
    created_at: float
    consumed: bool
    review: JsonObject
    mutation_epoch: int = 0
    snapshot_id: str = ''


_REVIEW_TTL_SECONDS = 600.0
_review_tokens: dict[str, ReviewTokenRecord] = {}


def new_operation_id(prefix: str = 'op') -> str:
    return f'{prefix}_{uuid.uuid4().hex[:16]}'


def v2_envelope(operation: str, status: str, success: bool = True) -> JsonObject:
    return {
        'contract_version': 2,
        'operation_id': new_operation_id(operation),
        'success': success,
        'status': status,
    }


def form_fingerprint(
    fields: JsonArray,
    primary_action: JsonObject | None = None,
    choices: JsonArray | None = None,
) -> str:
    """Create a stable, non-sensitive fingerprint for the currently rendered form."""

    compact_fields: JsonArray = []
    for item in fields:
        if not isinstance(item, dict):
            continue
        raw_length = item.get('value_length', 0)
        value_length = raw_length if isinstance(raw_length, int) else 0
        compact_fields.append(
            {
                'label': str(item.get('label', item.get('name', ''))),
                'tag': str(item.get('tag', '')),
                'type': str(item.get('type', '')),
                'required': bool(item.get('required', False)),
                'value_present': bool(item.get('value_present', False)),
                'value_length': value_length,
                'selected_label': str(item.get('selected_label', '')),
                'selected_value': str(item.get('selected_value', '')),
                'checked': item.get('checked'),
                'indeterminate': bool(item.get('indeterminate', False)),
                'validity': str(item.get('validity', '')),
                'selector_hint': str(item.get('selector_hint', '')),
            }
        )
    compact_choices: JsonArray = []
    for item in choices or []:
        if not isinstance(item, dict):
            continue
        options = item.get('options')
        compact_options: JsonArray = []
        if isinstance(options, list):
            for option in options:
                if not isinstance(option, dict):
                    continue
                compact_options.append(
                    {
                        'label': str(option.get('label', '')),
                        'selected': bool(option.get('selected', False)),
                        'enabled': bool(option.get('enabled', True)),
                    }
                )
        compact_choices.append(
            {
                'field_label': str(item.get('field_label', item.get('label', ''))),
                'type': str(item.get('type', '')),
                'required': bool(item.get('required', False)),
                'selected_label': str(item.get('selected_label', '')),
                'selected_state': str(item.get('selected_state', '')),
                'options': compact_options,
                'selector_hint': str(item.get('selector_hint', '')),
            }
        )
    payload: JsonObject = {
        'fields': compact_fields,
        'choices': compact_choices,
        'primary_action': {
            'name': str((primary_action or {}).get('name', '')),
            'role': str((primary_action or {}).get('role', '')),
            'selector_hint': str((primary_action or {}).get('selector_hint', '')),
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()[:32]


def issue_review_token(
    client_id: str,
    tab_id: str,
    document_generation: int,
    fingerprint: str,
    review: JsonObject,
    ttl_seconds: float = _REVIEW_TTL_SECONDS,
    mutation_epoch: int = 0,
    snapshot_id: str = '',
) -> ReviewTokenRecord:
    now = time.time()
    token = f'review_{uuid.uuid4().hex}'
    record = ReviewTokenRecord(
        token=token,
        client_id=client_id,
        tab_id=tab_id,
        document_generation=document_generation,
        form_fingerprint=fingerprint,
        expires_at=now + max(1.0, min(ttl_seconds, 3600.0)),
        created_at=now,
        consumed=False,
        review=review,
        mutation_epoch=mutation_epoch,
        snapshot_id=snapshot_id,
    )
    _review_tokens[token] = record
    _prune_review_tokens(now)
    return record


def get_review_token(token: str) -> ReviewTokenRecord | None:
    record = _review_tokens.get(token)
    if record is None or record.consumed or record.expires_at <= time.time():
        return None
    return record


def consume_review_token(token: str) -> ReviewTokenRecord | None:
    record = get_review_token(token)
    if record is None:
        return None
    record.consumed = True
    return record


def invalidate_review_tokens(client_id: str, tab_id: str) -> None:
    for record in _review_tokens.values():
        if record.client_id == client_id and record.tab_id == tab_id:
            record.consumed = True


def _prune_review_tokens(now: float) -> None:
    expired = [token for token, record in _review_tokens.items() if record.expires_at <= now or record.consumed]
    for token in expired:
        _review_tokens.pop(token, None)


def token_summary(record: ReviewTokenRecord) -> JsonObject:
    return {
        'review_token': record.token,
        'review_expires_at': record.expires_at,
        'form_fingerprint': record.form_fingerprint,
        'document_generation': record.document_generation,
        'mutation_epoch': record.mutation_epoch,
        'snapshot_id': record.snapshot_id,
    }


__all__ = [
    'ChoicePlan',
    'ComboboxPlan',
    'FieldState',
    'FormFieldPlan',
    'FormStepPlan',
    'ReviewTokenRecord',
    'UploadPlan',
    'consume_review_token',
    'form_fingerprint',
    'get_review_token',
    'invalidate_review_tokens',
    'issue_review_token',
    'new_operation_id',
    'token_summary',
    'v2_envelope',
]
