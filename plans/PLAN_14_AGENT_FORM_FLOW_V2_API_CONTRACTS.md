# PLAN_14 API Contracts

## Contract Goals

The PLAN_14 tools must expose small, predictable, site-neutral contracts that
help agents complete modern form flows while preserving security and type
quality. Responses must be structured enough for another agent turn to continue
without reading raw DOM text or falling back to JavaScript.

All contracts are alpha-compatible: existing incorrect alpha contracts may be
improved, but useful existing fields should remain when they do not conflict
with clearer behavior.

## Shared Response Rules

Every public tool returns a JSON object. Successful responses include:

- `success`: `true`
- domain-specific outcome fields
- `warnings`: list of short warning strings, present when useful
- `evidence`: present for sensitive, mutating, irreversible, or diagnostic
  actions

Structured failures use the existing error model:

- `error_code`
- `message`
- `retryable`
- `resource_state`
- optional `details`
- optional `recovery_hint`

Add `ErrorCode.AMBIGUOUS_ELEMENT` for cases where multiple candidates are too
close to act safely. Continue using `STALE_ELEMENT`, `PERMISSION_DENIED`,
`TIMEOUT`, `INVALID_INPUT`, and `EXECUTION_ERROR` for existing failure classes.

## Evidence Contract

Sensitive or irreversible actions include `evidence`:

```json
{
  "timestamp": 1781673600.0,
  "target": {
    "element_id": "el_abc",
    "tag": "button",
    "role": "button",
    "name": "Continue",
    "text_preview": "Continue",
    "selector_hint": "#continue",
    "bounds": {"x": 10, "y": 20, "width": 100, "height": 32}
  },
  "strategy": "native",
  "before": {"step": "Contact", "url": "https://example.test/form"},
  "after": {"step": "Questions", "url": "https://example.test/form"},
  "validation_text": ["Step 2 of 4"],
  "warnings": [],
  "redacted": false
}
```

Rules:

- Use Unix seconds from `time.time()`.
- Keep text previews short, normally 200 chars or less.
- Do not include passwords, tokens, cookie values, storage values, full
  JavaScript, bearer tokens, file contents, or large page text.
- For form values, report lengths and redaction status by default.
- If `include_values=true`, include only bounded non-sensitive previews.

## Value Exposure Rules

For snapshots and form tools, `include_values=false` is the default.

When `include_values=false`:

- Return `value_length`, `checked`, `selected`, or safe state metadata.
- Do not return raw text entry values except labels, options, validation text,
  button names, and short non-sensitive UI text.

When `include_values=true`:

- Return `value_preview` only for fields not identified as sensitive by type,
  name, label, autocomplete, placeholder, or ARIA metadata.
- Truncate previews to 200 chars.
- Return `redacted=true` and no preview for sensitive fields.
- Never log returned values.

## Active Surface Contract

Tool:

```text
page_get_active_surface(client_id, tab_id, scope="auto", max_fields=100, max_controls=120, include_values=false)
```

Parameters:

- `scope`: one of `auto`, `modal`, `dialog`, `form`, `main`, `viewport`,
  `active_element_context`.
- `max_fields`: clamp to 1 through 500.
- `max_controls`: clamp to 1 through 500.
- `include_values`: follows the shared value exposure rules.

Success response:

```json
{
  "success": true,
  "surface": {
    "scope": "modal",
    "reason": "topmost aria-modal dialog",
    "element_id": "el_surface",
    "role": "dialog",
    "label": "Application form",
    "bounds": {"x": 100, "y": 40, "width": 800, "height": 700}
  },
  "fields": [],
  "controls": [],
  "primary_action": {},
  "secondary_actions": [],
  "progress": {"text": "Step 2 of 4", "current": 2, "total": 4},
  "errors": [],
  "pending_required": [],
  "review_text": [],
  "active_element": {},
  "count": {"fields": 0, "controls": 0},
  "partial": false,
  "warnings": [],
  "evidence": {}
}
```

Selection rules:

- `auto` prefers visible modal or dialog surfaces over page main content.
- Topmost means visible, largest z-index or latest DOM overlay among visible
  modal-like candidates.
- `main` prefers `main`, `[role=main]`, then visible body content.
- `viewport` includes visible controls intersecting the viewport.
- `active_element_context` includes the active element, its closest form,
  modal, fieldset, section, or labelled group.

## Text Candidate Contract

Tool:

```text
element_find_by_text_candidates(client_id, tab_id, text, exact=true, role="", tag="", within_element_id="", nearest_heading="", section_label="", aria_contains="", prefer_modal=true, prefer_main_content=true, prefer_visible_center=true, prefer_largest=false, max_candidates=20)
```

Success response:

```json
{
  "success": true,
  "candidates": [
    {
      "rank": 1,
      "score": 1280.0,
      "element_id": "el_abc",
      "tag": "button",
      "role": "button",
      "name": "Apply",
      "text": "Apply",
      "actionable": true,
      "enabled": true,
      "visible": true,
      "in_modal": false,
      "in_main": true,
      "nearest_heading": "Role details",
      "section_label": "Main action",
      "selector_hint": "#apply",
      "xpath_hint": "//*[@id=\"apply\"]",
      "bounds": {"x": 10, "y": 20, "width": 120, "height": 40},
      "reasons": ["exact_text", "semantic_button", "main_content"]
    }
  ],
  "ambiguous": false,
  "warnings": []
}
```

Ranking defaults:

- Exact normalized text match: plus 1000.
- Contains normalized text match: plus 600.
- Semantic actionable element: plus 250.
- Enabled and visible: plus 150.
- Preferred active modal match: plus 120.
- Preferred main content match: plus 80.
- Heading, section, ARIA, role, tag, or within filters match: plus 50 each.
- Disabled, hidden, offscreen, duplicate ancestor, or generic container: strong
  penalties.
- `prefer_largest=false` prefers smaller direct controls over large ancestors.
- `prefer_largest=true` reverses only the size component, not the semantic
  penalties.

Ambiguity:

- Default `ambiguity_threshold` for click-by-text is 25 score points.
- If the top two enabled visible actionable candidates differ by less than the
  threshold, return `AMBIGUOUS_ELEMENT`.
- Include the top candidates and recovery guidance suggesting filters such as
  role, tag, `within_element_id`, heading, section, or modal preference.

## Click Effect Contract

Enhanced tool:

```text
element_click(client_id, tab_id, element_id, timeout=null, click_strategy="native", expect_dialog=false, expect_url_change=false, expect_text="", expect_selector="", expect_network_idle=false, effect_timeout=null)
```

Strategies:

- `native`: Pydoll `WebElement.click`.
- `center_mouse`: scroll into view and click the visible center with
  `tab.mouse.click`.
- `dispatch_pointer_sequence`: dispatch DOM pointer and mouse events. Mark as
  untrusted fallback.
- `trusted_fallback_if_safe`: try native first, then center mouse when target
  bounds and topmost state are safe. Use dispatch sequence only when explicitly
  safe and documented in warnings.

Success response:

```json
{
  "success": true,
  "element_id": "el_abc",
  "clicked": true,
  "effect_observed": true,
  "strategy_used": "native",
  "fallbacks_attempted": [],
  "matched_effects": ["expect_dialog"],
  "warnings": [],
  "evidence": {}
}
```

No-effect response:

```json
{
  "success": true,
  "clicked": true,
  "effect_observed": false,
  "strategy_used": "native",
  "fallbacks_attempted": [],
  "warnings": ["Requested effect was not observed before timeout."],
  "evidence": {}
}
```

Effect checks:

- `expect_dialog`: a new visible dialog or modal appears.
- `expect_url_change`: current URL differs from the pre-click URL.
- `expect_text`: page or active surface contains the expected text.
- `expect_selector`: selector appears and, by default, is visible.
- `expect_network_idle`: network event count stabilizes according to existing
  network idle semantics.

## Stale Resolution Contract

Tool:

```text
element_resolve_again(client_id, tab_id, element_id, selector_hint="", xpath_hint="", text="", role="", within_element_id="", max_candidates=5)
```

Success response:

```json
{
  "success": true,
  "resolved": true,
  "old_element_id": "el_old",
  "element_id": "el_new",
  "candidate": {},
  "strategy_used": "selector_hint",
  "warnings": []
}
```

Failure rules:

- If no candidate matches, return `STALE_ELEMENT`.
- If multiple candidates match without a clear winner, return
  `AMBIGUOUS_ELEMENT`.
- Auto re-resolution inside other tools is allowed only when the best candidate
  matches stable selector or XPath hints plus original context and has no close
  competitor.

## Form Fill Contract

Tool:

```text
form_fill_fields(client_id, tab_id, fields, scope="auto", validate=true, include_values=false)
```

Field request shape:

```json
{
  "label_contains": "Email",
  "question_contains": "",
  "selector": "",
  "role": "",
  "name": "",
  "placeholder_contains": "",
  "within_element_id": "",
  "value": "agent@example.test",
  "option_text": "",
  "checked": null,
  "exact": false
}
```

Success response:

```json
{
  "success": true,
  "filled": [],
  "unfilled": [],
  "ambiguous": [],
  "validation_errors": [],
  "pending_required": [],
  "warnings": [],
  "evidence": {}
}
```

Rules:

- The tool executes only caller-provided field mappings.
- It must not generate answers, choose between business options, or infer user
  preferences.
- It may normalize value types for numeric, checkbox, radio, select, textarea,
  contenteditable, and combobox controls.
- It must validate observable state when `validate=true`.
- Ambiguous field matches are reported, not guessed.

## Primary Action Contract

Tool:

```text
page_click_primary_action(client_id, tab_id, scope="auto", button_text_any=[], expected_next_text="", expected_progress_change=false, timeout=null)
```

Success response:

```json
{
  "success": true,
  "clicked": true,
  "effect_observed": true,
  "button": {},
  "previous_step": {},
  "new_step": {},
  "progress_before": {},
  "progress_after": {},
  "errors": [],
  "pending_required": [],
  "warnings": [],
  "evidence": {}
}
```

Primary button selection order:

1. Enabled visible submit or button-like control in active surface.
2. Explicit `button_text_any` match when provided.
3. ARIA role button with primary styling or form submit semantics.
4. Last enabled action in a modal footer when no safer primary exists.

If no clear primary action exists, return `AMBIGUOUS_ELEMENT` or
`RESOURCE_NOT_FOUND` with candidates.

## Submission Confirmation Contract

Tool:

```text
submission_wait_for_confirmation(client_id, tab_id, success_text_any=[], status_text_any=[], button_text_any=[], expect_url_change=false, expect_modal_gone=false, card_selector="", timeout=null)
```

Success response:

```json
{
  "success": true,
  "status": "confirmed",
  "confirmed": true,
  "evidence_text": ["Application submitted"],
  "url_changed": true,
  "modal_gone": true,
  "matched_patterns": ["success_text_any"],
  "warnings": [],
  "evidence": {}
}
```

Status values:

- `confirmed`: requested success evidence was observed.
- `submitted_uncertain`: the page changed or modal closed, but no explicit
  success evidence matched.
- `blocked`: validation errors, required fields, disabled submit, or blocking
  status appeared.
- `failed`: timeout or explicit failure text was observed.

The caller supplies expected success or status patterns. The tool must not embed
platform-specific success words.

## Upload Preparation Contract

Tool:

```text
artifact_prepare_upload(client_id, source_path, filename="", max_size_bytes=52428800)
```

Success response:

```json
{
  "success": true,
  "path": "controlled artifact path",
  "file": {"name": "resume.pdf", "path": "controlled artifact path", "size": 12345},
  "client_artifacts_dir": "controlled directory",
  "warnings": [],
  "evidence": {}
}
```

Denied response:

```json
{
  "error_code": "PERMISSION_DENIED",
  "message": "Source path is not in an allowed import directory.",
  "details": {
    "allowed_directories": [],
    "client_artifacts_dir": "",
    "recommended_mcp_operation": "Use artifact_get_paths, then provide a file already inside an allowed directory or configure an explicit import allowlist."
  },
  "retryable": false,
  "resource_state": "unknown"
}
```

Rules:

- Source must be a file and must exist.
- Source must be in runtime dirs or explicit upload/import allowlists.
- Destination is always the controlled client artifact directory.
- Filename is sanitized with `Path(filename).name` semantics and cannot escape
  the artifact directory.

## Upload Files Enhancement

Enhanced tool:

```text
upload_files(client_id, tab_id, element_id, paths, expect_filename_visible=false, verify_timeout=null)
```

Response additions:

- `accepted_by_input`: true when native input accepted the files.
- `visible_in_page`: true when page text near the input or active surface shows
  the filename.
- `filename_visible`: per-file filename visibility map.
- `nearby_text`: bounded text near the input after upload.
- `diagnostics`: explanation when `state.files` is empty after an apparently
  successful upload.

## Screenshot Contract

Enhanced tools:

```text
page_screenshot(client_id, tab_id, fmt="png", full_page=false, return_base64=false, path="")
element_screenshot(client_id, tab_id, element_id, return_base64=false, path="")
```

Default behavior:

- Save to a controlled artifact file when no path is provided.
- Return path metadata instead of base64.

Success response:

```json
{
  "success": true,
  "path": "controlled artifact path",
  "mime_type": "image/png",
  "width": 1280,
  "height": 720,
  "size": 123456,
  "return_base64": false,
  "data": "",
  "evidence": {}
}
```

Base64 is returned only when `return_base64=true`. It remains size-limited and
should be used for debugging only.

