"""JavaScript payloads for deep DOM traversal."""

DEEP_TREE_JS = """
(() => {
    const maxDepth = __MAX_DEPTH__;
    const maxNodes = __MAX_NODES__;
    const includeShadow = __INCLUDE_SHADOW__;
    const includeIframes = __INCLUDE_IFRAMES__;
    const prefix = 'el_deep_' + Math.random().toString(36).slice(2, 8) + '_';
    __REFERENCE_HELPERS__
    let counter = 0;
    const result = {
        elements: [],
        frames: [],
        shadow_roots: [],
        errors: [],
        partial: false
    };

    function cssEscape(value) {
        if (window.CSS && CSS.escape) return CSS.escape(value);
        return String(value).replace(/([ !"#$%&'()*+,./:;<=>?@[\\\\\\]^`{|}~])/g, '\\\\$1');
    }

    function attrEscape(value) {
        return String(value).replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
    }

    function textOf(el) {
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return '';
        return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    }

    function valueLengthOf(el) {
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return String(el.value || '').length;
        if (el.isContentEditable) return String(el.textContent || '').length;
        return 0;
    }

    function attrsOf(el) {
        const allowed = [
            'id', 'class', 'name', 'type', 'placeholder', 'href', 'src',
            'alt', 'title', 'role', 'aria-label', 'data-testid', 'required',
            'disabled', 'readonly', 'aria-required', 'aria-disabled', 'aria-readonly',
            'aria-checked', 'aria-selected', 'aria-pressed'
        ];
        const attrs = {};
        for (const attr of el.attributes || []) {
            const name = attr.name.toLowerCase();
            if (!allowed.includes(name)) continue;
            let value = attr.value || '';
            if (name === 'value' && el.tagName === 'INPUT' && el.type === 'password') {
                value = '***';
            }
            attrs[name] = value.slice(0, 500);
        }
        const sectionText = (el.closest && el.closest('section,fieldset')?.innerText || '').slice(0, 4000);
        if (el.required || el.getAttribute('aria-required') === 'true'
            || /(^|\\s)\\*\\s*(resume|cv|curriculum vitae)\\b/i.test(sectionText))
            attrs.required = 'true';
        if (el.disabled) attrs.disabled = 'true';
        if (el.readOnly) attrs.readonly = 'true';
        return attrs;
    }

    function selectorHint(el) {
        return structuralSelector(el);
    }

    function xpathHint(el) {
        return structuralXPath(el);
    }

    function boundsOf(el) {
        try {
            const rect = el.getBoundingClientRect();
            return {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            };
        } catch (e) {
            return null;
        }
    }

    function visibleOf(el, bounds) {
        try {
            const style = el.ownerDocument.defaultView.getComputedStyle(el);
            return !!bounds && bounds.width > 0 && bounds.height > 0
                && style.display !== 'none'
                && style.visibility !== 'hidden';
        } catch (e) {
            return false;
        }
    }

    function clickableOf(el) {
        const tag = (el.tagName || '').toLowerCase();
        return ['button', 'a', 'input', 'select', 'textarea', 'option'].includes(tag)
            || !!el.getAttribute('role')
            || typeof el.onclick === 'function';
    }

    function pushElement(el, framePath, shadowPath) {
        if (result.elements.length >= maxNodes) {
            result.partial = true;
            return null;
        }
        const tag = (el.tagName || '').toLowerCase();
        const bounds = boundsOf(el);
        const info = {
            elementId: prefix + counter++,
            tag,
            text: textOf(el).slice(0, 200),
            value_length: valueLengthOf(el),
            attrs: attrsOf(el),
            selector_hint: selectorHint(el),
            xpath_hint: xpathHint(el),
            match_index: referenceMatchIndex(el),
            role: roleForReference(el),
            label: labelForReference(el),
            fingerprint: referenceFingerprint(el),
            bounding_box: bounds,
            visible: visibleOf(el, bounds),
            enabled: !el.disabled,
            clickable: clickableOf(el),
            frame_path: framePath.slice(),
            shadow_path: shadowPath.slice()
        };
        result.elements.push(info);
        return info;
    }

    function walkRoot(root, framePath, shadowPath, depth, pathLabel) {
        if (depth > maxDepth) {
            result.partial = true;
            return;
        }
        let nodes = [];
        try {
            nodes = Array.from(root.querySelectorAll('*'));
        } catch (e) {
            result.errors.push({path: pathLabel, error: String(e && e.message ? e.message : e)});
            result.partial = true;
            return;
        }

        for (const el of nodes) {
            if (result.elements.length >= maxNodes) {
                result.partial = true;
                return;
            }
            const info = pushElement(el, framePath, shadowPath);
            if (!info) return;

            if (includeIframes && ['iframe', 'frame'].includes(info.tag)) {
                const frameRef = info.selector_hint || info.elementId;
                const nextFramePath = framePath.concat([frameRef]);
                result.frames.push({
                    element_id: info.elementId,
                    selector_hint: info.selector_hint,
                    frame_path: framePath.slice(),
                    target_frame_path: nextFramePath.slice(),
                    src: el.getAttribute('src') || ''
                });
                try {
                    if (el.contentDocument) {
                        walkRoot(
                            el.contentDocument,
                            nextFramePath,
                            shadowPath,
                            depth + 1,
                            nextFramePath.join(' > ')
                        );
                    }
                } catch (e) {
                    result.errors.push({
                        path: nextFramePath.join(' > '),
                        error: String(e && e.message ? e.message : e)
                    });
                    result.partial = true;
                }
            }

            if (includeShadow && el.shadowRoot) {
                const shadowRef = info.selector_hint || info.elementId;
                const nextShadowPath = shadowPath.concat([shadowRef]);
                result.shadow_roots.push({
                    host_element_id: info.elementId,
                    mode: el.shadowRoot.mode || 'open',
                    frame_path: framePath.slice(),
                    shadow_path: shadowPath.slice(),
                    target_shadow_path: nextShadowPath.slice()
                });
                walkRoot(
                    el.shadowRoot,
                    framePath,
                    nextShadowPath,
                    depth + 1,
                    nextShadowPath.join(' > ')
                );
            }
        }
    }

    walkRoot(document, [], [], 0, 'root');
    return result;
})()
"""


DEEP_FIND_JS = """
(() => {
    const selector = __SELECTOR__;
    const strategy = __STRATEGY__;
    const maxDepth = __MAX_DEPTH__;
    const maxNodes = __MAX_NODES__;
    const includeShadow = __INCLUDE_SHADOW__;
    const includeIframes = __INCLUDE_IFRAMES__;
    const prefix = 'el_deep_' + Math.random().toString(36).slice(2, 8) + '_';
    __REFERENCE_HELPERS__
    let counter = 0;
    const result = {elements: [], errors: [], partial: false};

    function cssEscape(value) {
        if (window.CSS && CSS.escape) return CSS.escape(value);
        return String(value).replace(/([ !"#$%&'()*+,./:;<=>?@[\\\\\\]^`{|}~])/g, '\\\\$1');
    }

    function attrEscape(value) {
        return String(value).replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
    }

    function selectorHint(el) {
        return structuralSelector(el);
    }

    function attrsOf(el) {
        const attrs = {};
        for (const attr of el.attributes || []) {
            const name = attr.name.toLowerCase();
        if (['id', 'class', 'name', 'type', 'placeholder', 'role', 'aria-label', 'data-testid',
            'required', 'disabled', 'readonly', 'aria-required', 'aria-disabled', 'aria-readonly',
            'aria-checked', 'aria-selected', 'aria-pressed'].includes(name)) {
                attrs[name] = (attr.value || '').slice(0, 500);
            }
        }
        const sectionText = (el.closest && el.closest('section,fieldset')?.innerText || '').slice(0, 4000);
        if (el.required || el.getAttribute('aria-required') === 'true'
            || /(^|\\s)\\*\\s*(resume|cv|curriculum vitae)\\b/i.test(sectionText))
            attrs.required = 'true';
        if (el.disabled) attrs.disabled = 'true';
        if (el.readOnly) attrs.readonly = 'true';
        return attrs;
    }

    function textOf(el) {
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return '';
        return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    }

    function valueLengthOf(el) {
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return String(el.value || '').length;
        if (el.isContentEditable) return String(el.textContent || '').length;
        return 0;
    }

    function pushMatch(el, framePath, shadowPath) {
        if (result.elements.length >= maxNodes) {
            result.partial = true;
            return;
        }
        result.elements.push({
            elementId: prefix + counter++,
            tag: (el.tagName || '').toLowerCase(),
            text: textOf(el).slice(0, 200),
            value_length: valueLengthOf(el),
            attrs: attrsOf(el),
            selector_hint: selectorHint(el),
            xpath_hint: structuralXPath(el),
            match_index: referenceMatchIndex(el),
            role: roleForReference(el),
            label: labelForReference(el),
            fingerprint: referenceFingerprint(el),
            frame_path: framePath.slice(),
            shadow_path: shadowPath.slice()
        });
    }

    function queryMatches(root, framePath, shadowPath, pathLabel) {
        try {
            if (strategy === 'css') {
                for (const el of Array.from(root.querySelectorAll(selector))) {
                    pushMatch(el, framePath, shadowPath);
                }
            } else if (strategy === 'xpath') {
                const doc = root.ownerDocument || root;
                const snapshot = doc.evaluate(
                    selector,
                    root,
                    null,
                    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                    null
                );
                for (let i = 0; i < snapshot.snapshotLength; i++) {
                    pushMatch(snapshot.snapshotItem(i), framePath, shadowPath);
                }
            }
        } catch (e) {
            result.errors.push({path: pathLabel, error: String(e && e.message ? e.message : e)});
            result.partial = true;
        }
    }

    function walkRoot(root, framePath, shadowPath, depth, pathLabel) {
        if (depth > maxDepth || result.elements.length >= maxNodes) {
            result.partial = result.elements.length >= maxNodes;
            return;
        }
        queryMatches(root, framePath, shadowPath, pathLabel);

        let nodes = [];
        try {
            nodes = Array.from(root.querySelectorAll('*'));
        } catch (e) {
            result.errors.push({path: pathLabel, error: String(e && e.message ? e.message : e)});
            result.partial = true;
            return;
        }

        for (const el of nodes) {
            if (includeIframes && ['iframe', 'frame'].includes((el.tagName || '').toLowerCase())) {
                const frameRef = selectorHint(el) || ((el.tagName || 'iframe').toLowerCase());
                const nextFramePath = framePath.concat([frameRef]);
                try {
                    if (el.contentDocument) {
                        walkRoot(el.contentDocument, nextFramePath, shadowPath, depth + 1, nextFramePath.join(' > '));
                    }
                } catch (e) {
                    result.errors.push({
                        path: nextFramePath.join(' > '),
                        error: String(e && e.message ? e.message : e)
                    });
                    result.partial = true;
                }
            }
            if (includeShadow && el.shadowRoot) {
                const shadowRef = selectorHint(el) || ((el.tagName || 'shadow-host').toLowerCase());
                const nextShadowPath = shadowPath.concat([shadowRef]);
                walkRoot(el.shadowRoot, framePath, nextShadowPath, depth + 1, nextShadowPath.join(' > '));
            }
        }
    }

    walkRoot(document, [], [], 0, 'root');
    return result;
})()
"""
