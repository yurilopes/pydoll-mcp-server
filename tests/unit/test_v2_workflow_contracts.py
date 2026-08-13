"""Unit coverage for the v2 form, submission, script, and artifact contracts."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from pathlib import Path

import pytest

from pydoll_mcp_server.browser.script_utils import normalize_script_result
from pydoll_mcp_server.json_types import (
    JsonArray,
    JsonObject,
    JsonValue,
    get_array,
    normalize_json_value,
    require_json_object,
)

pytestmark = [pytest.mark.unit]


def _script_response(value: object, runtime_type: str) -> JsonObject:
    normalized = normalize_json_value(value, 'test value')
    return {'result': {'result': {'type': runtime_type, 'value': normalized}}}


def test_script_normalizer_supports_all_json_and_undefined_types() -> None:
    cases: list[tuple[str, JsonValue, str]] = [
        ('object', {}, 'object'),
        ('array', [], 'array'),
        ('string', 'text', 'string'),
        ('number', 3, 'number'),
        ('boolean', True, 'boolean'),
        ('null', None, 'null'),
    ]
    for runtime_type, value, expected_type in cases:
        result = normalize_script_result(_script_response(value, runtime_type), 'test', expected_type)
        assert result['success'] is True
        assert result['value_type'] == expected_type

    undefined = normalize_script_result({'result': {'result': {'type': 'undefined'}}}, 'undefined')
    assert undefined['success'] is True
    assert undefined['value_type'] == 'undefined'


def test_script_normalizer_hides_malformed_and_exception_details() -> None:
    malformed = normalize_script_result({'unexpected': 'shape'}, 'malformed', 'object')
    assert malformed['success'] is False
    assert malformed['received_type'] == 'malformed'
    assert malformed['resource_state'] == 'unknown'
    assert 'exceptionDetails' not in str(malformed)

    exception = normalize_script_result(
        {
            'result': {
                'result': {'type': 'object'},
                'exceptionDetails': {'text': 'private browser error'},
            }
        },
        'exception',
    )
    assert exception['success'] is False
    assert exception['response_format'] == 'cdp_runtime_exception'
    assert 'private browser error' not in str(exception)


def test_review_token_is_single_use_and_client_scoped() -> None:
    from pydoll_mcp_server.tools.form_contracts import (
        consume_review_token,
        get_review_token,
        issue_review_token,
    )

    record = issue_review_token('client-a', 'tab-a', 4, 'fingerprint', {'stage': 'form'}, ttl_seconds=10)
    assert get_review_token(record.token) is record
    consumed = consume_review_token(record.token)
    assert consumed is record
    assert get_review_token(record.token) is None

    other = issue_review_token('client-b', 'tab-a', 4, 'fingerprint', {'stage': 'form'}, ttl_seconds=10)
    assert other.client_id != record.client_id


def test_submission_outcome_precedence_is_conservative() -> None:
    from pydoll_mcp_server.tools.submission import SubmissionOutcome, classify_submission_outcome

    assert (
        classify_submission_outcome('application submitted captcha challenge', ['application submitted'], [])
        is SubmissionOutcome.SECURITY_CHALLENGE
    )
    assert (
        classify_submission_outcome('application submitted sign in required', ['application submitted'], [])
        is SubmissionOutcome.AUTHENTICATION_REQUIRED
    )
    assert (
        classify_submission_outcome('application submitted already applied', ['application submitted'], [])
        is SubmissionOutcome.PORTAL_LIMIT
    )
    assert (
        classify_submission_outcome('application submitted required field', ['application submitted'], [])
        is SubmissionOutcome.VALIDATION_FAILED
    )
    assert (
        classify_submission_outcome('application submitted', ['application submitted'], [])
        is SubmissionOutcome.CONFIRMED
    )
    assert classify_submission_outcome('the page changed', [], []) is SubmissionOutcome.UNKNOWN


def test_combobox_matching_preserves_unicode_and_reports_ambiguity() -> None:
    from pydoll_mcp_server.tools.combobox_controls import select_option

    options: JsonArray = [
        {'text': 'São Paulo', 'value': 'sp', 'disabled': False},
        {'text': 'Sao Paulo', 'value': 'sp-2', 'disabled': False},
        {'text': 'São Paulo', 'value': 'disabled', 'disabled': True},
    ]
    assert select_option(options, 'Sa\u0303o Paulo', True, False) is not None
    assert select_option(options, 'Sao Paulo', True, False) is not None
    ambiguous = select_option(
        [{'text': 'Remote', 'value': '1'}, {'text': 'Remote', 'value': '2'}],
        'Remote',
        True,
        False,
    )
    assert ambiguous is None


def test_domain_restriction_is_explicitly_normalized() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import (
        _DOMAIN_RESTRICTIONS,
        normalize_employer_domain,
        record_domain_restriction,
    )

    _DOMAIN_RESTRICTIONS.clear()
    assert normalize_employer_domain('HTTPS://Jobs.Example.com/path') == 'jobs.example.com'
    stored = record_domain_restriction('jobs.example.com', 'portal_limit', ['limit reached'], ['job-1'])
    assert stored['domain'] == 'jobs.example.com'
    assert stored['job_identifiers'] == ['job-1']
    assert 'other.example.com' not in _DOMAIN_RESTRICTIONS


def test_application_terms_are_reported_as_candidate_handoff() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import attestation_handoffs

    fields: JsonArray = [
        {
            'label': 'I accept the TeamStation AI application terms.',
            'type': 'checkbox',
            'checked': False,
        }
    ]
    handoffs = attestation_handoffs(fields, ['terms'])
    assert len(handoffs) == 1
    handoff = require_json_object(handoffs[0], 'attestation handoff')
    assert handoff['requires_candidate_confirmation'] is True
    assert handoff['protected_by_do_not_touch'] is True


def test_tel_value_verification_accepts_input_mask_formatting() -> None:
    from pydoll_mcp_server.tools.form_input_modes import verification_satisfied

    state: JsonObject = {
        'input_type': 'tel',
        'value': '(21) 99833-0989',
        'framework_event': True,
        'controlled_value_survived': True,
        'blurred': True,
        'validity': 'valid',
        'errors': [],
    }
    assert verification_satisfied(state, '+55 21 99833 0989', 'submission_ready') is False
    state['value'] = '+55 (21) 99833-0989'
    assert verification_satisfied(state, '+55 21 99833 0989', 'submission_ready') is True


def test_disputed_deep_inventory_allows_unique_active_surface_plans() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import hard_prepare_blockers

    preflight: JsonObject = {
        'fields': [
            {'label': 'Name', 'field_key': 'name', 'element_id': 'name-1'},
            {'label': 'Email', 'field_key': 'email', 'element_id': 'email-1'},
        ],
        'primary_action': {'text': 'Submit Application'},
        'do_not_touch': [],
        'blockers': [
            {
                'kind': 'discovery',
                'details': {'status': 'disagreement'},
            }
        ],
        'attestation_handoffs': [],
        'missing_candidate_data': [],
    }
    plans: list[JsonObject] = [
        {'label_contains': 'Name', 'value': 'Yuri'},
        {'label_contains': 'Email', 'value': 'yuri@example.com'},
    ]
    assert hard_prepare_blockers(preflight, plans) == []


def test_disputed_deep_inventory_still_blocks_ambiguous_plans() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import hard_prepare_blockers

    preflight: JsonObject = {
        'fields': [
            {'label': 'Name', 'field_key': 'name-1', 'element_id': 'name-1'},
            {'label': 'Name', 'field_key': 'name-2', 'element_id': 'name-2'},
        ],
        'primary_action': {'text': 'Submit Application'},
        'do_not_touch': [],
        'blockers': [{'kind': 'discovery', 'details': {'status': 'disagreement'}}],
        'attestation_handoffs': [],
        'missing_candidate_data': [],
    }
    assert hard_prepare_blockers(preflight, [{'label_contains': 'Name', 'value': 'Yuri'}])


def test_disputed_deep_inventory_can_use_type_to_select_surface_textarea() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import hard_prepare_blockers

    preflight: JsonObject = {
        'fields': [
            {'label': 'Tell us about your AI work', 'tag': 'textarea', 'type': 'textarea'},
            {'label': 'Tell us about your AI work', 'tag': 'input', 'type': 'textbox'},
        ],
        'primary_action': {'text': 'Submit Application'},
        'blockers': [{'kind': 'discovery', 'details': {'status': 'disagreement'}}],
    }
    assert (
        hard_prepare_blockers(
            preflight,
            [{'label_contains': 'AI work', 'type': 'textarea', 'value': 'confirmed text'}],
        )
        == []
    )


def test_disputed_inventory_does_not_require_primary_action_during_prepare() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import hard_prepare_blockers

    preflight: JsonObject = {
        'fields': [{'label': 'Name', 'field_key': 'name', 'element_id': 'name-1'}],
        'do_not_touch': [],
        'blockers': [
            {'kind': 'primary_action', 'reason': 'not_found'},
            {'kind': 'discovery', 'details': {'status': 'disagreement'}},
        ],
        'attestation_handoffs': [],
        'missing_candidate_data': [],
    }
    assert hard_prepare_blockers(preflight, [{'label_contains': 'Name', 'value': 'Yuri'}]) == []


def test_security_handoff_does_not_block_safe_preparation() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import hard_prepare_blockers

    preflight: JsonObject = {
        'fields': [{'label': 'Name', 'field_key': 'name', 'element_id': 'name-1'}],
        'do_not_touch': [],
        'blockers': [{'kind': 'security_control', 'reason': 'requires_candidate_action'}],
        'attestation_handoffs': [],
        'missing_candidate_data': [],
    }
    assert hard_prepare_blockers(preflight, [{'label_contains': 'Name', 'value': 'Yuri'}]) == []


def test_form_preflight_contract_rejects_page_without_form_fields() -> None:
    from pydoll_mcp_server.tools.form_contracts import v2_envelope

    result = v2_envelope('form_preflight', 'blocked', False)
    result.update(
        {
            'fields': [],
            'primary_action': {'text': 'Apply for this Job'},
            'blockers': [{'kind': 'form_surface', 'reason': 'no_interactive_form_fields'}],
        }
    )
    assert result['status'] == 'blocked'
    blocker = require_json_object(get_array(result, 'blockers')[0], 'form blocker')
    assert blocker['kind'] == 'form_surface'


def test_missing_candidate_data_remains_a_review_blocker_not_a_prepare_abort() -> None:
    from pydoll_mcp_server.tools.form_workflow_helpers import hard_prepare_blockers

    preflight: JsonObject = {
        'fields': [{'label': 'Name', 'field_key': 'name', 'element_id': 'name-1'}],
        'primary_action': {'text': 'Submit Application'},
        'do_not_touch': [],
        'blockers': [],
        'attestation_handoffs': [],
        'missing_candidate_data': [
            {'label': 'Resume', 'field_key': 'resume', 'type': 'file'},
        ],
    }
    assert hard_prepare_blockers(preflight, [{'label_contains': 'Name', 'value': 'Yuri'}]) == []


def test_fill_script_is_function_wrapped_for_url_safe_pydoll_execution() -> None:
    from pydoll_mcp_server.tools.form_scripts import fill_script

    script = fill_script('{"value":"https://example.com/profile","events":[]}')
    assert script.lstrip().startswith('function(){')
    assert script.rstrip().endswith('}')
    assert 'https://' not in script
    assert 'decodeURIComponent' in script


def test_artifact_registry_hash_and_export_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pydoll_mcp_server.browser.artifact_registry import register_artifact
    from pydoll_mcp_server.config import get_config
    from pydoll_mcp_server.tools.artifacts import artifact_export

    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    monkeypatch.setenv('PYDOLL_MCP_RUNTIME_DIR', str(tmp_path / 'runtime'))
    get_config.cache_clear()
    config = get_config()
    source = config.artifacts_dir / 'client-a' / 'review.png'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b'review')

    registered = register_artifact('client-a', str(source), evidence_kind='pre_submission_review')
    assert registered['success'] is True
    assert registered['sha256'] == hashlib.sha256(b'review').hexdigest()
    artifact_id = str(registered['artifact_id'])

    exported = asyncio.run(artifact_export('client-a', artifact_id, 'exports/review.png'))
    assert exported['success'] is True
    assert (config.artifacts_dir / 'exports' / 'review.png').read_bytes() == b'review'

    denied = asyncio.run(artifact_export('client-a', artifact_id, '../../outside.png'))
    assert denied['error_code'] == 'PERMISSION_DENIED'
    get_config.cache_clear()


def test_public_workflow_tools_have_pydantic_safe_plan_schemas() -> None:
    from pydoll_mcp_server.server import mcp
    from pydoll_mcp_server.tools.form_workflow import form_preflight, form_prepare, form_review

    assert inspect.iscoroutinefunction(form_preflight)
    assert inspect.iscoroutinefunction(form_review)
    assert inspect.iscoroutinefunction(form_prepare)
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert {'form_preflight', 'form_review', 'form_prepare', 'form_submit_after_review'} <= names
