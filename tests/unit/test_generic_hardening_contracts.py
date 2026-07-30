"""Focused contracts for generic multi-site application hardening."""

from __future__ import annotations

import inspect

import pytest

from pydoll_mcp_server.json_types import fold_visible_text, normalize_json_value, normalize_visible_text

pytestmark = pytest.mark.unit


def test_unicode_normalization_preserves_text_and_supports_folded_matching() -> None:
    decomposed = 'Bras\u0069\u0301lia'
    visible = normalize_visible_text(decomposed)

    assert visible == 'Brasília'
    assert fold_visible_text(visible) == 'brasilia'
    unicode_text = 'João\u00a0D\u2019Ávila 🚀 Ελληνικά'
    assert normalize_visible_text(unicode_text) == unicode_text
    assert normalize_json_value({'label': decomposed}) == {'label': 'Brasília'}


def test_security_diagnostics_are_passive_and_localized_by_kind() -> None:
    from pydoll_mcp_server.security.site_signals import site_diagnostics_script

    script = site_diagnostics_script().lower()
    assert 'security_controls' in script
    for kind in ('captcha', 'two_factor', 'payment', 'biometric', 'identity_verification'):
        assert kind in script
    assert 'document.cookie' not in script
    assert 'localstorage' not in script
    assert 'automation_allowed: false' in script
    assert 'requires_user_action: true' in script


def test_existing_interaction_tools_publish_hardening_parameters() -> None:
    from pydoll_mcp_server.tools.elements import element_click, element_fill
    from pydoll_mcp_server.tools.form_fill import form_fill_fields

    click_params = inspect.signature(element_click).parameters
    fill_params = inspect.signature(element_fill).parameters
    form_params = inspect.signature(form_fill_fields).parameters

    assert {'expect_attribute_selector', 'expect_attribute_name', 'expect_enabled_element_id'} <= click_params.keys()
    assert {'mode', 'validation_timeout', 'expected_enabled_element_id'} <= fill_params.keys()
    assert {'mode', 'validation_timeout', 'expected_enabled_element_id'} <= form_params.keys()
