"""JavaScript fragment for active surface selection."""

SURFACE_SELECTION_SCRIPT = r"""
let surface = null;
let surfaceScope = scope;
let surfaceReason = '';
let surfaceTag = '';
let surfaceRole = '';
let surfaceLabel = '';
let surfaceSelector = '';

function emptySurface(reason, warning) {
    return {
        surface_scope: scope,
        surface_reason: reason,
        fields: [],
        controls: [],
        errors: [],
        warnings: [warning]
    };
}

if (scope === 'auto' || scope === 'modal' || scope === 'dialog') {
    const dialog = findTopmostDialog() || findModalOverlay();
    if (dialog) {
        surface = dialog;
        surfaceScope = dialog.getAttribute('aria-modal') === 'true' ? 'modal' : 'dialog';
        surfaceReason = dialog.getAttribute('aria-modal') === 'true'
            ? 'topmost aria-modal dialog'
            : 'topmost visible dialog';
        surfaceTag = dialog.tagName.toLowerCase();
        surfaceRole = dialog.getAttribute('role') || 'dialog';
        surfaceLabel = dialog.getAttribute('aria-label') || '';
        surfaceSelector = selectorHint(dialog);
    } else if (scope !== 'auto') {
        return emptySurface('no visible ' + scope + ' found', 'No visible ' + scope + ' element found.');
    }
}
if (!surface && (scope === 'auto' || scope === 'form')) {
    const forms = [...document.querySelectorAll('form')].filter(visible);
    if (forms.length) {
        surface = forms[0];
        surfaceScope = 'form';
        surfaceReason = 'first visible form';
        surfaceTag = 'form';
        surfaceRole = 'form';
        surfaceLabel = forms[0].getAttribute('aria-label') || '';
        surfaceSelector = selectorHint(forms[0]);
    } else if (scope !== 'auto') {
        return emptySurface('no visible form found', 'No visible form element found.');
    }
}
if (!surface && (scope === 'auto' || scope === 'main')) {
    const main = document.querySelector('main, [role="main"]');
    if (main && visible(main)) {
        surface = main;
        surfaceScope = 'main';
        surfaceReason = 'main element';
        surfaceTag = main.tagName.toLowerCase();
        surfaceRole = 'main';
        surfaceLabel = '';
        surfaceSelector = selectorHint(main);
    } else if (scope !== 'auto') {
        return emptySurface('no visible main element found', 'No visible main element found.');
    }
}
if (!surface && scope === 'auto') {
    surface = document.body;
    surfaceScope = 'viewport';
    surfaceReason = 'body fallback';
    surfaceTag = 'body';
    surfaceRole = '';
    surfaceLabel = '';
    surfaceSelector = '';
}
if (!surface && scope === 'viewport') {
    surface = document.body;
    surfaceScope = 'viewport';
    surfaceReason = 'viewport scope';
    surfaceTag = 'body';
    surfaceRole = '';
    surfaceLabel = '';
    surfaceSelector = '';
}
if (!surface && scope === 'active_element_context') {
    let active = document.activeElement;
    if (active) {
        surface = active.closest('form, [role="dialog"], fieldset, section, article') || document.body;
        surfaceScope = 'active_element_context';
        surfaceReason = 'active element context';
        surfaceTag = surface.tagName.toLowerCase();
        surfaceRole = surface.getAttribute('role') || '';
        surfaceLabel = surface.getAttribute('aria-label') || '';
        surfaceSelector = selectorHint(surface);
    }
}
if (!surface) {
    return emptySurface(
        'unable to determine surface',
        'Unable to determine active surface for scope: ' + scope
    );
}
"""
