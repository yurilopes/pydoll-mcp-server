"""Small semantic policies for common application form surfaces."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormPreset:
    """Policy knobs that do not contain portal-specific selectors or bypasses."""

    name: str
    deep_on_shadow: bool
    reconcile_new_tabs: bool
    stabilization_ms: int
    upload_mode: str


_PRESETS: dict[str, FormPreset] = {
    'generic_form': FormPreset(
        name='generic_form',
        deep_on_shadow=True,
        reconcile_new_tabs=True,
        stabilization_ms=120,
        upload_mode='native_or_trigger',
    ),
    'linkedin_easy_apply': FormPreset(
        name='linkedin_easy_apply',
        deep_on_shadow=True,
        reconcile_new_tabs=True,
        stabilization_ms=100,
        upload_mode='native_or_trigger',
    ),
    'external_ats_multistep': FormPreset(
        name='external_ats_multistep',
        deep_on_shadow=True,
        reconcile_new_tabs=True,
        stabilization_ms=150,
        upload_mode='native_or_trigger',
    ),
}


def get_form_preset(name: str) -> FormPreset | None:
    """Return a known preset without guessing from a URL or portal brand."""

    return _PRESETS.get(name.strip().casefold())


def preset_names() -> tuple[str, ...]:
    return tuple(_PRESETS)


__all__ = ['FormPreset', 'get_form_preset', 'preset_names']
