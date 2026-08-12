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

For a persistent browser session, call `browser_list` before `browser_launch`.
If a browser already exists for the client and profile, `browser_launch` returns
that browser with `reused=true`. Open additional pages with `tab_new`. Do not
start another browser for each search or page. A managed browser is closed when
the MCP server shuts down, while its persistent profile retains authentication.

Before opening another page, call `tab_list` and keep the live count at five or fewer. The
server reconciles tabs opened by pages or manually in Chrome, so the count is not limited to
tabs created through `tab_new`. A tab close is confirmed only when Chrome removes the target;
`DIALOG_PRESENT` means that `dialog_handle` is required before retrying.

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

Use `element_fill` or `element_fill_and_verify` with `value`. The default
`mode="auto"` is appropriate for React, Angular-like, and ordinary controls:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_abc",
  "value": "Senior Python developer",
  "mode": "auto",
  "validation_timeout": 3
}
```

The result reports `mode_used`, `field_valid`, `dependent_control_enabled`,
and `fallback_used`. When a portal replaces the input during validation, the
MCP re-resolves the cached reference before its single keyboard fallback. Use
`mode="keyboard"` only for an ordinary field that rejects framework-safe
events. Never use keyboard mode for CAPTCHA, OTP, payment, biometric, identity,
or password controls.

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

Upload tools accept the generated file path directly. No shell copy or staging
tool call is required:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_file",
  "paths": ["C:/path/to/resume.pdf"],
  "expect_filename_visible": true
}
```

For custom upload buttons or portals using File System Access API, resolve the
trigger and call `upload_files_from_trigger` with the same source path. The MCP
uses the original file for direct inputs and performs temporary native-picker
staging internally only when required.

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "trigger_element_id": "el_upload",
  "paths": ["C:/path/to/resume.pdf"],
  "picker_strategy": "auto",
  "expected_filenames": ["resume.pdf"]
}
```

Check `file_upload_state` or `visible_in_page` after upload if the page moves
file state out of the native input. Use `artifact_prepare_upload` only when a
stable artifact copy is explicitly useful for later operations.

## Prepare and review a job application

Use the v2 workflow for a job application. It separates inspection, planned
mutations, review, and the authorized final click:

1. Call `form_preflight` with the candidate facts and planned uploads. It
   reports required fields, missing candidate data, upload states, visible
   errors, security controls, attestations, and partial discovery errors.
2. Call `form_prepare` with only the approved fields, choices, comboboxes,
   uploads, and explicitly named intermediate steps. It never clicks the final
   submit action.
3. Call `form_review` and inspect `blockers`, `handoff`, `ready_for_submission`,
   selected labels, upload states, and the pre-submission evidence artifact.
4. If the review is ready and the session has explicit authorization, call
   `form_submit_after_review` with the returned `review_token` and either
   `session_autonomous` or `user_approved`.

The review token is bound to the client, tab, document generation, form
fingerprint, and expiration. It is single-use and becomes invalid after a
relevant change or server restart. Never retry a submit when the click
transport is unknown. Re-run preflight and review instead.

Example preflight:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "planned_fields": [
    {"label": "Full Name", "value": "Jane Doe"},
    {"label": "Email", "value": "jane@example.com"}
  ],
  "planned_uploads": [
    {"label": "Resume", "path": "C:/approved/resume.pdf"}
  ],
  "employer_domain": "example.com",
  "include_values": false
}
```

Do not provide guessed address, salary, work authorization, demographic,
attestation, or consent values. A handoff is the expected result when the
candidate must answer or complete a security control.

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

Returns the new `element_id` when a single safe candidate is found. The same
re-resolution happens atomically inside mutating `element_click`,
`element_click_by_text`, `form_fill_fields`, and `page_click_primary_action`.

## Handle security controls

After opening an application page or step, inspect `page_snapshot` or
`page_get_active_surface`. Check `security_controls` before acting. A detected
CAPTCHA, reCAPTCHA, hCaptcha, Turnstile, OTP or 2FA prompt, payment form,
biometric check, or identity verification includes `automation_allowed=false`
and `requires_user_action=true`. Do not click or fill the control. Ask the user
to complete it in the visible browser, then call the observation tool again and
resume the ordinary form flow.

Interaction responses have three independent sections:

- `mcp_action` records resolution, the event strategy, and whether the event was sent.
- `page_effect` records requested and observed URL, text, selector, progress, surface, attribute, or enabled-state effects.
- `site_diagnostics` records declared framework, validation, and security heuristics.

`NO_EFFECT` means the browser event was sent but the requested page transition
was not observed. It is not evidence that the click did not occur.

## Confirm the active profile

The catalog profile is selected at process startup. Use `server_status` with
`include_tool_names=true` and compare `tool_profile`, `exposed_tool_count`, and
`tool_names` with the client's expected surface. `full` intentionally contains
advanced compatibility tools, while `agent` and `linkedin` intentionally omit
them. `keyboard_press` is the canonical keyboard tool; `page_press_key` is not
part of the public catalog.

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
