# Agent Recipes

These recipes show preferred tool sequences for modern frontend pages. They are
designed to reduce custom JavaScript and keep actions inside the MCP safety
model.

## Open and inspect a page

For a persistent session where the user expects continuity:

```json
{
  "client_id": "agent",
  "session_intent": "user_authenticated",
  "site_hint": "linkedin.com"
}
```

This reuses an existing matching profile so login state is preserved across
launches. Use `profile_list` to discover available profiles.

For disposable browsing where state should not persist:

1. `browser_launch(client_id, headless=false, profile_mode="temporary")`
2. `page_goto(client_id, tab_id, url)`
3. `page_get_text(client_id, tab_id)`
4. `page_get_interactive_summary(client_id, tab_id)`

Use `page_get_tree` when you need DOM shape. It hides head metadata and
invisible nodes by default. Use `include_head=true` or `include_invisible=true`
only for diagnostics.

## Click a visible option by text

Use `element_click_by_text` for cards, buttons, tabs, and custom controls:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "text": "Freelance",
  "exact": true
}
```

The response includes the chosen candidate and rejected candidates so the agent
can detect ambiguity before continuing.

## Fill a controlled input

Use `element_fill` or `element_fill_and_verify` with `value`:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_abc",
  "value": "Senior Python developer"
}
```

The fill path uses native property setters and dispatches `input`, `change`, and
`blur` so React-like controlled inputs see the update.

## Select an autocomplete combobox option

1. Find the input with `page_get_interactive_summary`, `element_find_by_label`,
   or `element_find_by_placeholder`.
2. Call `combobox_type_and_select`.

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_skill",
  "query": "Artificial",
  "option_text": "Artificial Intelligence"
}
```

The tool handles `aria-controls`, `role=listbox`, `role=option`, and portaled
option containers.

For native `select` elements with long option lists, keep the active surface
compact and call `select_get_options` only when the options are needed:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_country",
  "max_options": 50
}
```

## Wait for state instead of sleeping

Prefer condition waits over fixed sleeps:

- `page_wait_for_text`
- `page_wait_text_gone`
- `page_wait_for_selector`
- `page_wait_for_url`
- `page_wait_for_network_idle`
- `element_wait_value`

## Upload a file safely

Use `artifact_prepare_upload` to copy a file into the controlled artifacts
directory before uploading:

```json
{
  "client_id": "agent",
  "source_path": "path/to/resume.pdf"
}
```

The response includes the ready-to-use artifact path. Then find the file input
and call `upload_files`:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_file",
  "paths": ["artifacts/agent/resume.pdf"],
  "expect_filename_visible": true
}
```

Check `file_upload_state` or `visible_in_page` after upload if the page moves
file state out of the native input. Use `artifact_import` for lower-level file
copies from allowed directories.

## Complete a multi-step form flow

Use the high-level form flow tools to navigate multi-step applications without
custom JavaScript:

1. Observe the active surface after the form appears:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "scope": "auto"
}
```

Call `page_get_active_surface`. The response includes fields, compact
actionable controls, containers, primary and secondary actions, progress
indicator, visible errors, and pending required fields. Treat `fields` as the
source of truth for inputs and selects; option lists stay behind
`select_get_options` or `combobox_get_options`.

Radio and checkbox questions appear as grouped fields with an `options` list.
Act on the chosen option's `element_id`; required groups remain in
`pending_required` until selected. `primary_action` excludes modal dismissal
actions such as Close and Cancel.

Prefer `form_select_choice(field_label, option_label)` when selecting a radio
or checkbox answer. The tool confines matching to the question group and
verifies the checked state before reporting success.

2. Fill fields by intent with `form_fill_fields`:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "fields": [
    {"label_contains": "Full Name", "value": "John Doe"},
    {"label_contains": "Email", "value": "john@example.com"},
    {"label_contains": "Phone", "value": "+1 555-0000"}
  ],
  "validate": true
}
```

Each field can match by `label_contains`, `question_contains`, `selector`,
`role`, `name`, `placeholder_contains`, or `within_element_id`. The tool
reports filled, unfilled, ambiguous fields, and validation errors.

3. Advance steps with `page_click_primary_action`:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "expected_progress_change": true
}
```

Returns the clicked button, progress before/after, surfaced errors, and
pending required fields.

4. Resolve duplicate action text with `element_find_by_text_candidates`:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "text": "Apply",
  "prefer_modal": true
}
```

Returns ranked candidates with scores, element IDs, and an `ambiguous`
flag. Use filters (`role`, `tag`, `nearest_heading`) to narrow matches.

5. Wait for submission confirmation with `submission_wait_for_confirmation`:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "success_text_any": ["submitted", "received"],
  "expect_modal_gone": true
}
```

Returns `confirmed`, `submitted_uncertain`, `blocked`, or `failed` with
structured evidence.

6. Recover stale elements after re-render with `element_resolve_again`:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_stale",
  "selector_hint": "#primary-action"
}
```

Returns the new `element_id` when a single safe candidate is found.

## Evaluate JavaScript only when needed

`js_evaluate_readonly` returns real JSON values:

```json
{
  "success": true,
  "value": {"answer": 42},
  "value_type": "object"
}
```

Do not parse `value` as a JSON string. Use manual JavaScript only for diagnostics
that the first-class tools cannot provide.

## Inspect a submitted HTTP request

1. Call `network_enable`, then `network_clear`.
2. Start `network_wait_for_request` with the expected URL and method before triggering
   the form submission.
3. Use the returned request ID with `network_get_request` to inspect the original
   headers and payload.
4. Use the same ID with `network_get_response` after the response arrives.
5. Call `network_clear` when the analysis is complete.

`network_list` is only a compact sanitized index. `network_get_request` is raw and may
contain credentials or personal data, so its response must not be logged automatically.
For multipart requests, Chromium may omit file bytes from `Network.getRequestPostData`;
the tool preserves available data and reports this limitation instead of reconstructing it.

## Call an authenticated HTTP endpoint directly

Use `http_request` when the endpoint should share the browser's cookies but does not need
to run through page JavaScript or CORS. Relative URLs and same-host absolute URLs are
allowed by default. Set `allow_cross_origin=true` only for a deliberate external target.

Use `network_replay_request` to resend a captured request. POST, PUT, PATCH, and DELETE
require `confirm_side_effects=true`. Replay rejects incomplete multipart captures instead
of presenting reconstructed data as the original request.
