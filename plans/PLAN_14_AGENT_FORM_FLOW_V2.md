# PLAN_14: Agent Form Flow V2

## Objective

Implement the next generic agent-friendly workflow layer for modern form flows.
This plan builds on PLAN_13, which already delivered interactive summaries,
semantic clicks, framework-safe fills, combobox helpers, condition waits, upload
state, artifact import, and structured JSON returns from JavaScript tools.

PLAN_14 must reduce the remaining need for manual JavaScript, index-based button
selection, coordinate fallbacks, repeated stale element recapture, and ad hoc
text inspection during real multi-step form flows with uploads and review.

The implementation must stay site-neutral. Do not add selectors, text matching,
workflow assumptions, or special behavior for any job board, social network,
ATS, or application platform. Every tool must operate on generic browser,
DOM, accessibility, form, upload, and confirmation concepts.

## Confirmed Baseline

- Existing PLAN_13 work added `page_get_interactive_summary`,
  `element_click_by_text`, `element_click_center`, `mouse_click`,
  `element_fill_and_verify`, `element_wait_value`, `form_snapshot`,
  `form_errors`, combobox helpers, file upload state, artifact paths,
  artifact import, condition waits, and JSON-valued `js_evaluate`.
- `plans/PLAN_13_AGENT_FRONTEND_ROBUSTNESS.md` is currently untracked and must
  not be overwritten, deleted, renamed, or reverted.
- Current large modules remain below the 400 line target, but new behavior must
  be placed in cohesive new modules instead of inflating existing tool modules.
- Pydoll capabilities confirmed for this wave include `WebElement.click`,
  `tab.mouse.click`, `WebElement.set_input_files`, `Tab.expect_file_chooser`,
  `Tab.take_screenshot`, and element screenshot support.

## Non-Negotiable Constraints

- Preserve the security model: no arbitrary filesystem access, no OS commands,
  no free CDP exposure, no credential leakage, no unbounded screenshots, and no
  sensitive values in logs.
- Preserve async behavior and explicit timeouts. Mutating actions must keep tab
  operation locks where they can interfere with each other.
- Do not use `Any`, `cast`, or `type: ignore` to hide typing problems. Normalize
  dynamic browser or script values at small boundaries.
- Do not add production branches only for tests. Fixtures and tests must model
  real contracts the MCP server should support.
- Do not weaken Ruff, mypy, Pyright, LSP, tests, path allowlists, redaction, or
  authentication.
- Keep Python files below the 400 line target when practical. Files between 401
  and 450 lines require explicit justification in progress notes. Files above
  450 lines must be refactored.

## Implementation Phases

1. Test-first fixture and contracts
   - Add the multi-step fixture and failing tests described in
     `plans/PLAN_14_AGENT_FORM_FLOW_V2_TESTS.md` before changing production
     behavior.
   - Cover unit-level ranking, ambiguity, recovery, evidence, upload path
     diagnostics, and screenshot defaults.
   - Cover one real MCP browser smoke flow that completes the fixture without
     manual `js_evaluate`.

2. Shared typed helpers
   - Add small internal modules for active surface detection, ranked text
     candidates, click effect observation, form field intent matching,
     operational evidence, and upload preparation.
   - Use concrete `TypedDict`, dataclass, enum, or narrow JSON helper patterns
     already used in the repo. Avoid broad dictionaries flowing through core
     logic without validation.
   - Keep MCP response shaping at the tool boundary.

3. Active surface observation
   - Add `page_get_active_surface(client_id, tab_id, scope="auto",
     max_fields=100, max_controls=120, include_values=false)`.
   - Supported scopes: `auto`, `modal`, `dialog`, `form`, `main`, `viewport`,
     and `active_element_context`.
   - In `auto`, prefer the topmost visible `dialog`, `[role="dialog"]`,
     `[aria-modal="true"]`, modal overlay, or active form-like surface. Fall
     back to main content, then viewport.
   - Return surface metadata, fields, controls, labels, progress, visible
     validation errors, primary action, secondary action, review text, active
     element context, truncation flags, partial errors, and evidence.
   - `include_values=false` is the default. Value previews are allowed only by
     the response rules in the API contracts plan.

4. Ranked text candidates and ambiguity handling
   - Add `element_find_by_text_candidates(...)` as an observation-only tool that
     never clicks.
   - Enhance `element_click_by_text(...)` with the same filters plus
     `ambiguity_threshold`.
   - Candidate ranking must prefer semantically actionable elements over
     internal text nodes and generic ancestors. Strong candidates include
     `button`, `a[href]`, `a[role=button]`, clickable inputs, labels associated
     to controls, enabled ARIA buttons, tab controls, and elements with clear
     handlers.
   - Filters must include `role`, `tag`, `within_element_id`,
     `nearest_heading`, `section_label`, `aria_contains`, `prefer_modal`,
     `prefer_main_content`, `prefer_visible_center`, and `prefer_largest`.
   - If the top two strong candidates are too close by the configured threshold,
     return `AMBIGUOUS_ELEMENT` with candidates and recovery guidance instead
     of clicking.

5. Click effect validation and stale element recovery
   - Enhance `element_click(...)` with `click_strategy`, `expect_dialog`,
     `expect_url_change`, `expect_text`, `expect_selector`,
     `expect_network_idle`, and `effect_timeout`.
   - Supported `click_strategy` values: `native`, `center_mouse`,
     `dispatch_pointer_sequence`, and `trusted_fallback_if_safe`.
   - Return `clicked`, `effect_observed`, `strategy_used`,
     `fallbacks_attempted`, warnings, target evidence, and the matched effect.
   - A click that emits events but does not satisfy requested effects must return
     `success=true`, `clicked=true`, and `effect_observed=false` unless the
     event itself failed.
   - Add `element_resolve_again(...)` to explicitly re-resolve stale handles.
     Auto re-resolution inside mutating tools is allowed only when the original
     cached hints and context produce exactly one safe candidate.

6. Intent-driven form filling
   - Add `form_fill_fields(client_id, tab_id, fields, scope="auto",
     validate=true, include_values=false)`.
   - Each requested field must provide the intended target and value. The tool
     must not infer or invent answers.
   - Supported matching inputs: `label_contains`, `question_contains`,
     `selector`, `role`, `name`, `placeholder_contains`, `within_element_id`,
     and active surface scope.
   - Supported control actions: text input, textarea, numeric input, select by
     visible text or value, radio by visible text or value, checkbox boolean,
     contenteditable text, and combobox option text using existing combobox
     helpers where applicable.
   - Return filled fields, unfilled fields, ambiguous fields, validation errors,
     changed state, pending required fields, and evidence.

7. Primary action and step progression
   - Add `page_click_primary_action(client_id, tab_id, scope="auto",
     button_text_any=[], expected_next_text="",
     expected_progress_change=false, timeout=null)`.
   - Primary action selection must use active surface context, semantic role,
     button prominence, enabled state, surface order, and optional button text
     filters. It must not depend on platform-specific labels.
   - Return the clicked button, previous step, new step, progress before and
     after, surfaced errors, pending required fields, effect observation, and
     evidence.

8. Upload preparation and diagnostics
   - Add `artifact_prepare_upload(client_id, source_path, filename="",
     max_size_bytes=52428800)`.
   - The tool may copy only from existing runtime directories or explicit
     upload/import allowlists into the controlled client artifacts directory.
   - On denial, return exact allowed directories, target artifact directory, and
     the recommended MCP operation. Do not return shell commands that imply
     arbitrary filesystem access.
   - Enhance `upload_files(...)` with `expect_filename_visible=false` and
     `verify_timeout`.
   - Return `accepted_by_input`, `visible_in_page`, `filename_visible`,
     `nearby_text`, file metadata, and diagnostics explaining native input
     clearing when the site moves upload state into custom UI.

9. Submission confirmation
   - Add `submission_wait_for_confirmation(client_id, tab_id,
     success_text_any=[], status_text_any=[], button_text_any=[],
     expect_url_change=false, expect_modal_gone=false, card_selector="",
     timeout=null)`.
   - Return one of `confirmed`, `submitted_uncertain`, `blocked`, or `failed`.
   - Evidence must include the shortest useful matching text, modal state, URL
     change state, relevant button/status state, and warnings. The caller must
     provide expected text patterns. Do not bake in platform-specific success
     messages.

10. Artifact-first screenshots
   - Change the planned screenshot contract so `page_screenshot` and
     `element_screenshot` save artifact files by default.
   - Add `return_base64=false` and only return base64 when explicitly requested.
   - Return path, mime type, dimensions, byte size, capture scope, and evidence.
   - Support element screenshots through existing `element_id`; region
     screenshot support may be implemented only if it can be validated safely
     against viewport bounds.

11. Tool registration, diagnostics, and docs
   - Register new public tools in `tool_catalog.py`.
   - Update `server_status.capabilities` with active surfaces, form flow,
     upload preparation, effect-aware clicks, and confirmation waits.
   - Update public docs: `README.md`, `docs/agent-recipes.md`,
     `docs/security.md`, `docs/pydoll-capabilities.md`, and `CHANGELOG.md`.
   - Public docs must not include local machine paths. Local paths may appear in
     progress or developer prompt artifacts only.

## Acceptance Criteria

- A real browser smoke test completes the new multi-step fixture with upload,
  review, and confirmation using high-level tools and no manual `js_evaluate`.
- Text candidate tools return ranked candidates with context and refuse low
  confidence ambiguous clicks.
- Click tools report whether the requested effect was observed.
- Stale cached element handles are either safely re-resolved or return a clear
  `STALE_ELEMENT` with recovery guidance.
- Form tools fill only caller-provided answers, validate observable state, and
  report ambiguous or failed fields without guessing.
- Upload tools keep allowlist security intact while making the allowed workflow
  direct and discoverable for agents.
- Screenshots default to artifact files and do not flood MCP text output.
- Evidence is concise, structured, redacted, and available for sensitive actions.

## Required Gates

Run the full gate set from `AGENTS.md` before concluding implementation:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m ruff format --check .
C:\Users\Yuri\anaconda3\python.exe -m mypy --strict src tests
C:\Users\Yuri\anaconda3\python.exe -m pyright --pythonpath C:\Users\Yuri\anaconda3\python.exe
C:\Users\Yuri\anaconda3\python.exe -m pytest -m mcp_e2e -q
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
C:\Users\Yuri\anaconda3\python.exe -m build
```

