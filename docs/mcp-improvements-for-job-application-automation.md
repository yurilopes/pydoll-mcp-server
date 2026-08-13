# MCP Improvements for Job Application Automation

Date: 2026-08-12

Status: diagnostic report and implementation backlog. The improvements below are intended
for a follow-up implementation session. This document does not define permission to submit
applications, bypass website controls, or weaken browser safety boundaries.

## Context

This report is based on a live run of the Pydoll MCP server against a visible, persistent
Chrome profile while cataloging and applying to remote technology vacancies. The workflow
used one active tab at a time and relied on the MCP tools for navigation, element discovery,
form filling, choice selection, file upload, screenshots, submission attempts, and result
verification.

The tested sites included Ashby, Lever, SmartRecruiters, Greenhouse embeds and a custom
AlphaSights careers form. The observations are relevant to React-controlled forms, custom
controls, shadow-DOM components, cross-origin embeds and portal-specific application workflows
generally, not only to one employer or portal.

The central finding is that the MCP can complete these workflows, but the agent currently
needs too many low-level recovery steps. The main risk is a false positive: the browser DOM
can display a value while the site's framework state still considers the field empty.

## Executive summary

The highest-value improvements are:

1. Make form operations verify framework state and submission readiness, not only DOM values.
2. Normalize every script evaluation result into a stable structured response before it
   reaches a tool implementation.
3. Add semantic state verification for custom choices, checkboxes, comboboxes, and uploads.
4. Return a typed submission outcome that distinguishes success, validation failure, portal
   limits, authentication blockers, security challenges, and unknown outcomes.
5. Make browser registration and screenshot artifacts resilient across server restarts.

These changes should reduce repeated discovery calls, avoid accidental duplicate submissions,
and make a handoff precise when a human or a later session is required.

## Observed issues and evidence

### P0: Framework state is not verified after text filling

`form_fill_fields` returned success, a requested value length, and `verified: true` for
required Name and Email fields. The page visibly displayed both values. The first submit
attempt nevertheless returned portal validation errors saying that Name and Email were
missing.

The reliable recovery was:

1. Locate the field by label.
2. Scroll it into view and click it with a native mouse action.
3. Press `Control+A` and `Backspace`.
4. Type the value through the keyboard path.
5. Press `Tab` to trigger blur and the framework's change handling.

The same class of issue previously affected LinkedIn and salary fields. A DOM value check
alone is insufficient for controlled inputs.

Proposed behavior:

- Add a `state_verification` mode to fill operations with values such as `dom`,
  `framework_event`, `blurred`, and `submission_ready`.
- After a framework-safe fill, inspect the control's live value, validity, dirty state when
  available, and a stable framework-independent signal that the control accepted an input
  event.
- If the signal is inconclusive, automatically perform the native keyboard fallback before
  returning success.
- Return `verified: false` or `verification: "inconclusive"` instead of claiming success
  when only the DOM value is known.
- Include the exact fallback used and the final observed state in the result.

### P0: Script result normalization is not reliable

Several operations intermittently failed with:

`Script result must be a JSON object`

The failure appeared in element state or bounds reads, checkbox operations, and some fill
paths. The keyboard mode of `element_fill` could also fail while trying to use its fallback
verification path. This forces the agent to replace one high-level operation with multiple
manual calls and makes it difficult to distinguish an application error from a browser
transport error.

Proposed behavior:

- Introduce one internal boundary that accepts primitive, null, JSON object, and JSON array
  results from Pydoll script evaluation.
- Normalize successful results into a typed envelope, for example:

  ```json
  {
    "success": true,
    "value": {"...": "..."},
    "value_type": "object",
    "script_path": "element_state"
  }
  ```

- Normalize malformed or unexpected results into a structured error containing the operation,
  result type, and whether a safe retry is possible.
- Do not discard the raw result type or silently turn a transport failure into an empty
  state.
- Add contract tests for object, array, string, number, boolean, null, malformed, and
  exception results.

### P0: Submission outcomes need semantic classification

The submission confirmation helper did not recognize the exact success sentence used by one
Ashby form: `Your application was successfully submitted.` A broad text match containing
the word `application` would be unsafe because the same word appears on the form before a
submission. A portal-limit page also contains a successful navigation transition but is not
an accepted application.

Proposed behavior:

- Return a typed outcome such as `confirmed`, `validation_failed`, `portal_limit`,
  `authentication_required`, `security_challenge`, `rejected`, `cancelled`, or `unknown`.
- Match exact or high-confidence success patterns, including common Ashby variants, while
  requiring a confirmation surface or a destination state change.
- Match negative outcomes before generic success words.
- Include the matched text, URL, timestamp, and screenshot artifact reference.
- Keep `confirmed` reserved for a visible portal confirmation or an email confirmation that
  the caller explicitly supplied and authorized the email connector to inspect.
- Treat a portal application limit as a first-class blocked outcome, not as a form error and
  not as a confirmed submission.

### P0: Domain application limits need early preflight detection

The ElevenLabs Ashby form accepted the complete application state and allowed the native
submit action, but the portal then displayed a clear domain-level restriction: the candidate
had applied for a position in that domain within the last 90 days. The restriction was only
known after generating a dedicated resume, filling the form, and submitting it. It applies to
the employer domain rather than to one vacancy, so repeating the same work for another role
would be wasteful.

Proposed behavior:

- Expose a bounded preflight operation that can inspect the official application surface for
  known domain limits without submitting the form.
- Persist a domain restriction with the domain, reason, observed timestamp, expiry estimate,
  evidence text, and affected job identifiers.
- Before preparing another vacancy for the same domain, return `domain_limit_active` and the
  evidence that caused it.
- Keep the final submission classifier able to recognize a newly discovered restriction when
  preflight information is unavailable or stale.
- Never infer that two employers share a restriction merely because their portals look alike.

### P0: File upload state can disappear after a failed submit attempt

The uploaded PDF was accepted and displayed by the form. After the first validation failure
and a second submit attempt, the form displayed an empty required Resume control. The agent
had to upload the same file again before making the final submission attempt.

Proposed behavior:

- Make upload results include a stable control fingerprint, file name, size, MIME type, and
  page-visible state.
- Add a `file_state` operation that can distinguish `selected`, `processing`, `accepted`,
  `rejected`, and `cleared`.
- Before a retry, automatically re-check file state and report that a re-upload is required.
- Preserve the user-visible file name and do not silently upload a different file.
- Add a pre-submit invariant that required file controls are still populated.

### P1: Custom Yes/No controls need selected-state verification

On the tested form, native button clicks returned success but did not change the custom
control's selected state. A centered mouse click after scrolling the control into view did
change the button class to a state containing `_active_`. The generic click result reported
`effect_observed: false` because it did not know which semantic state to inspect.

Proposed behavior:

- Detect button groups with repeated labels and shared containers.
- Expose a semantic operation such as `choice_select(field, option)` instead of requiring
  callers to find the Nth identical `Yes` button.
- Verify `aria-checked`, `aria-selected`, `aria-pressed`, native checked inputs, selected
  classes, and visible style changes in that order.
- Use a safe click escalation policy: native, centered mouse, then a documented fallback.
- Return the group label, selected option, verification signal, and click strategy.
- Fail with an ambiguity error when repeated identical labels cannot be scoped to a field.

### P1: Checkbox operations need a native fallback and state contract

The semantic checkbox operation could fail with the script result error. Clicking the visible
checkbox input with a centered mouse action set `checked: true` reliably in the tested form.
Label clicks were not equally reliable.

Proposed behavior:

- Make `checkbox_set` target the native input whenever it is available.
- Verify `checked` after the action and include the associated label in the result.
- Support indeterminate state and disabled state explicitly.
- Do not treat a click event as success unless the requested checked state is observed.
- Keep optional consent controls opt-in and never auto-check them based on nearby text.

### P1: Deep discovery must expose visible controls inside open shadow roots

On the Cint SmartRecruiters form, `element_find_deep` found the controls inside nested
custom elements, but `page_get_active_surface` and `form_snapshot` returned no fields and
no primary action. The page visibly contained six required preliminary questions, a required
privacy checkbox, and a Submit button. The screenshot was the reliable source for the
rendered state, while the deep element results were needed to interact with the controls.

Proposed behavior:

- Traverse open shadow roots while preserving a stable logical field path and the visible
  ancestor label.
- Report controls that are visually rendered even when their native input is hidden inside a
  custom element.
- Associate required markers and validation state with the logical field, not only the
  internal input ID.
- Detect the active form and primary action from the rendered custom-element tree when the
  light DOM does not contain a conventional form element.
- Return a warning when surface extraction and deep discovery disagree, including the
  selectors needed to reconcile the two views.

### P1: Upload verification must account for shadow-DOM file controls

On the same Cint form, the desktop picker strategy successfully staged and attached the PDF,
and the filename was visibly rendered in the Resume component. The upload operation still
returned a final failure because its verification path could not observe the file state inside
the custom shadow-DOM dropzone. This is a dangerous false negative because a caller may upload
the same file repeatedly or incorrectly conclude that the form is not ready.

Proposed behavior:

- Let the upload verifier inspect file inputs and rendered filename text through the same deep
  shadow-root traversal used for discovery.
- Separate native picker success, file-input state, component acceptance, and page-visible
  confirmation into distinct fields.
- Return `accepted_with_verification_warning` when the file is visibly accepted but the native
  control cannot be read, instead of returning a generic failure.
- Include the visible filename, control fingerprint, and screenshot reference in the result.
- Prevent a second upload unless the current file state is explicitly `cleared`, `rejected`,
  or absent.

### P1: Required-field preflight must expose missing values and option labels

On the AlphaSights form, `form_snapshot` correctly exposed the required controls, labels and
select elements. It did not itself identify that the degree-grade select was still empty as a
blocking field. `form_errors` also returned no errors because the portal had not yet attempted
submission. The agent had to compare the snapshot against the visible required marker and the
known candidate facts manually.

Proposed behavior:

- Return `required`, `empty`, `validity`, and `blocker` for every discovered control.
- Include the visible field label and all option labels in compact form, while retaining the
  portal's opaque option value only as an implementation detail.
- Distinguish `not_yet_validated` from `valid`, `invalid`, and `missing_required`.
- Make `form_preflight` report missing candidate data, such as an unknown degree grade, before
  a submit attempt.
- Keep a form with one missing required fact explicitly reviewable without requiring a failed
  submission to reveal the blocker.

### P1: Choice results must return the selected label, not only an opaque value

The AlphaSights select operation succeeded, but its response returned only the selected index
and an opaque numeric value. The visible labels such as `7+ years`, `Superior`, `Yes`, `No`,
and `I consent` were available to the agent before the action but were not echoed in the
result. This makes audit logs harder to read and increases the risk of confusing two similar
selects that happen to use different internal values.

Proposed behavior:

- Return `selected_label`, `selected_value`, `selected_index`, and the field label in every
  successful select result.
- Verify the rendered selected text after the change event.
- Preserve the option list in a compact form when selection fails, including the normalized
  labels and the requested label.
- Treat opaque values as portal implementation details rather than the primary audit signal.

### P2: Form artifact capture should support compact full-page evidence

Long application forms often require a full-page review to prove that fields above and below
the viewport were handled. The screenshot tool produced a valid full-page artifact, but the
agent still had to copy it manually into the application directory and separately associate it
with the tracker.

Proposed behavior:

- Add an explicit `evidence_kind` such as `form_initial`, `pre_submission_review`, or
  `submission_confirmation` to screenshot requests.
- Return a stable artifact ID and a compact field summary with the screenshot result.
- Allow a validated application artifact directory to receive the evidence without arbitrary
  filesystem access.
- Preserve the screenshot viewport, page URL, timestamp and content hash in the artifact
  metadata.

### P1: Combobox selection is not Unicode-safe or outcome-safe

Typing a query containing `Brasília` could produce a malformed accented character in the
visible control. An ASCII query, `Brasilia`, followed by an option containing `Federal
District`, selected the desired location. For a pronoun combobox, the visible input became
`He/Him`, while the tool result reported `selected: false` and another option-selection
operation could report that the resource no longer existed.

Proposed behavior:

- Preserve Unicode through keyboard and script paths, including NFC normalization and
  surrogate-safe transport.
- Let callers specify a normalized query and an exact visible option independently.
- Read the option list after filtering and return the selected option's text and value.
- Verify the combobox input value, `aria-expanded`, `aria-activedescendant`, and selected
  option state after the click.
- Keep a selected option handle valid across the same combobox interaction, or return a
  fresh handle instead of a stale resource error.
- Include a safe ASCII fallback only when the caller permits approximate matching, and report
  that fallback explicitly.

### P1: Add a form preflight and review operation

The agent currently needs to discover fields, fill them, inspect them, and click submit as
separate calls. This is slow and makes it easy to miss a required field that appears below
the viewport. A missing street address also became apparent only after opening and inspecting
the complete form.

Proposed behavior:

- Add `form_preflight` that returns all required controls, their labels, types, current state,
  possible options, and blockers before any mutation.
- Add `form_review` that returns a compact field-by-field summary suitable for a final human
  or agent review, including selected custom choices and uploaded files.
- Return missing canonical data separately from technical interaction failures.
- Identify fields that are required by the portal but are not present in the caller's supplied
  profile, such as an address line, without guessing a value.
- Support a `do_not_touch` list for optional marketing, newsletter, demographic, and consent
  fields.

### P1: Attestations and security controls need explicit handoff outcomes

The Canonical application form exposed both an invisible reCAPTCHA Enterprise control and an
attestation stating that the applicant must use only personal words and that AI-generated
content may disqualify the application. The MCP correctly diagnosed the CAPTCHA as a security
control requiring user action, but the workflow still needs a structured way to preserve the
prepared state and explain why submission stopped. A generic validation failure would hide the
difference between a missing field, a legal attestation, and a security challenge.

Proposed behavior:

- Classify CAPTCHA, two-factor authentication, login, payment and other security controls as
  `requires_user_action` with a stable control description and frame URL when available.
- Detect attestations and declarations separately from ordinary yes/no questions.
- Return the exact attestation text, its required state, and a `requires_candidate_confirmation`
  outcome without selecting it automatically.
- Let callers preserve a prepared form and evidence bundle without attempting submission.
- Make the handoff result include the next safe user action and prevent retries that would
  bypass the control or silently accept an unverified declaration.

### P1: Button-based comboboxes need a bounded native fallback

The Revolut careers form used visually familiar location and experience selectors that were
implemented as buttons and custom popovers rather than native `select` elements. Native
`element_fill`, `element_click`, and `combobox_select_option` operations either stalled until
their timeout or could not establish a stable selected state. A narrowly scoped
`js_evaluate` action that clicked the visible button and selected the exact visible option
completed the interaction through the page UI, but the agent had to discover the control
structure and write the fallback manually.

Proposed behavior:

- Detect button-triggered comboboxes and expose their trigger, popup, option labels, and
  current semantic value as one control record.
- Bound every native interaction with a short operation timeout and return `timed_out` with
  the control fingerprint instead of leaving an apparently running call.
- Add an MCP-native fallback that dispatches the same user-facing click and option-selection
  events against the exact visible control, with no arbitrary script execution and no
  selector broadening.
- Verify both the trigger's selected label and the form state after the popup closes.
- Return a normalized result such as `selected`, `not_found`, `timed_out`, `stale`, or
  `ambiguous`, including the requested label and the rendered selected label.
- Add fixtures for repeated button comboboxes, portals rendered outside the form, and option
  labels containing accents or non-breaking spaces.

### P1: Click verification must distinguish visible effects from hidden selector matches

On the N-iX job page, the native `Easy Apply` click returned success because the expected
`form.wpcf7-form` selector existed. The form and its ancestors still had zero rendered bounds,
the responsive form container remained `display: none`, the page showed no application fields,
and `form_snapshot` returned zero fields. The selector match was therefore a DOM existence
signal, not a visible workflow transition.

Proposed behavior:

- Require a visible, non-zero rendered surface when a click declares an opened form, modal,
  dialog, or step transition.
- Return `hidden_effect` when a matching selector exists but has zero bounds, is hidden by a
  parent, or is outside the active viewport.
- Include before and after visibility, bounds, display state, active surface, and viewport
  breakpoint in the effect evidence.
- Detect responsive-only form containers and report the required viewport or a safe manual
  handoff instead of treating the desktop click as complete.
- Add fixtures where a hidden mobile form and a visible desktop trigger share the same page,
  and where a selector exists before the click but does not represent a state transition.

### P1: Cross-origin iframe discovery must return navigable frame metadata

On the Storyblok page, the official Greenhouse application was exposed as a visible
`grnhse_iframe` with a cross-origin `src`, but `frame_list` returned an empty partial result.
The agent had to read the exact iframe source from the page DOM and navigate the same visible tab
to that official URL before the form became operable. This was safe because the URL came from the
official page, but the discovery contract did not expose the frame relationship directly.

Proposed behavior:

- Return all rendered iframe elements with frame ID, source URL, origin, bounds, visibility and
  whether the frame is same-origin or cross-origin.
- Preserve a navigable frame reference even when DOM inspection inside a cross-origin frame is
  unavailable.
- Let callers request a direct navigation handoff to an exact frame source while retaining the
  parent page URL and provenance.
- Mark empty or partial frame discovery explicitly and distinguish no frames from inaccessible
  cross-origin frames.
- Add fixtures for Greenhouse and other embedded application forms where the parent page exposes
  a cross-origin iframe but frame inspection has limited access.

### P1: Upload operations need a semantic page-state contract

On the Miro custom form, `upload_files` returned an accepted file but reported
`accepted_by_input: false` and no filename visibility. A later `file_upload_state` call saw a
stale element, while the rendered page text visibly showed the resume filename and file size.
The upload was real from the portal's perspective, but the MCP result did not provide a
reliable way to distinguish accepted, rendered, cleared, and stale states. The cover-letter
input also reused the same visible filename presentation, so a generic filename check could
misattribute the file to the wrong field.

Proposed behavior:

- Return a stable upload operation ID and a field-scoped semantic state independent of a
  transient element handle.
- Re-discover the input and its associated visible file component after every upload or DOM
  rerender.
- Verify the field using multiple signals: native `files`, associated filename text, upload
  token or remove control, and portal validation state.
- Distinguish `accepted`, `rendered`, `cleared`, `rejected`, `stale`, and `unknown` instead of
  treating a missing native file list as failure by itself.
- Associate a filename with the nearest field label or fieldset so that resume and cover
  letter cannot be confused.
- Add a pre-submit invariant that requires the specific required upload field to be in an
  accepted or rendered state, and return a re-upload instruction when it is not.

### P1: Multi-step forms need scoped state and validation snapshots

The Miro form accepted the professional fields on the first step and advanced to a second
step containing an optional demographic questionnaire. The final native click returned
`clicked: true`, but the portal remained on the same page with a validation error. The
questionnaire offered explicit `I don't wish to answer` choices, yet the portal still
reported three invalid controls after those choices were selected and their DOM values were
verified. This required several manual diagnostics to establish that no professional field
was invalid and no confirmation existed.

Proposed behavior:

- Treat each form step as a separate scoped surface with its own required fields, optional
  fields, visible controls, screenshot, and validation snapshot.
- Return the active step identifier and a transition result for `Next`, `Previous`, and
  final submit actions.
- Before advancing, report field labels and rendered validation messages rather than only an
  aggregate invalid count.
- Preserve explicit opt-out values as semantic answers while keeping optional demographic
  fields outside the professional application answer map unless the caller deliberately
  records them.
- If the DOM value is correct but the portal state remains invalid, classify the step as
  `portal_validation_mismatch` and stop after a bounded retry budget.
- Add a fixture where an optional questionnaire is conditionally rendered but its component
  incorrectly blocks submit, so the MCP returns a precise handoff instead of suggesting
  sensitive data entry.

### P2: Browser registration should survive server restarts

Restarting the MCP server lost the in-memory browser registry even though a visible Chrome
process and its persistent profile still existed. The old profile was also locked until the
old browser process was stopped. After reopening the browser, the session worked again, but
the recovery was manual. The `browser_attach` capability was not available in the active
tool profile after the restart.

Proposed behavior:

- Persist enough browser ownership metadata to reconnect safely after a server restart:
  profile key, process identity, debugging endpoint, owner client, and last-known tabs.
- On startup, reconcile live browser processes and tabs before creating a duplicate profile
  instance.
- Make `browser_attach` available in the full and documented tool profiles, with explicit
  ownership checks.
- Return a lifecycle state such as `reconnected`, `new_instance`, `profile_locked`, or
  `requires_handoff`.
- Never attach to an unowned browser merely because its profile directory matches.
- Preserve the one-tab safety rule and return a clear error instead of closing the only tab.

### P1: React textarea filling needs a framework-safe fallback

On the ElevenLabs Ashby form, the ordinary fill operation reported a successful interaction for
the mission textarea, but the rendered React state immediately returned to an empty value. The
same page accepted a different textarea through the ordinary path. A bounded, exact-target
fallback using the native textarea value setter followed by normal `input` and `change` events
made the mission response persist and remain visible in the form snapshot. This fallback must
remain scoped to the exact visible control and must not be used to modify hidden security fields.

Proposed behavior:

- Verify the value after the framework has had time to re-render, not only immediately after
  dispatching input events.
- If the value is lost, retry once with a framework-specific native setter strategy for the
  exact element fingerprint.
- Return the strategy used, the before and after lengths, and whether the value survived a
  short stabilization window.
- Refuse the fallback for hidden, disabled, read-only, security, CAPTCHA, or unknown controls.
- Add React textarea fixtures where one controlled component accepts the standard path and
  another requires the bounded fallback.

### P1: DOM values are not enough for controlled input submission readiness

On the ElevenLabs Ashby form, the name, email and location controls visibly contained values
after ordinary fill and combobox operations. The first native submit still returned missing
Email and Location. Re-entering the email through native keyboard events and selecting the
observed location option through the open combobox made the portal accept the field state for
validation. This is distinct from the textarea issue: the DOM was visibly populated, but the
portal's controlled state was not synchronized.

Proposed behavior:

- Distinguish `dom_value`, `framework_value`, `selected_label` and `submit_ready` in fill and
  combobox results instead of returning a single `verified` boolean.
- After a controlled fill, wait for a short stabilization window and inspect the rendered
  control, its associated error state and any portal-owned selected option.
- For required fields, expose a bounded native keyboard fallback that clears, types and blurs
  the exact visible control. Do not claim success from a programmatic value assignment alone.
- For custom comboboxes, require an observed option selection and a closed dropdown before
  reporting the field as ready.
- Provide a form-level preflight that reports fields whose DOM values are present but whose
  framework or portal state is still missing, without submitting the application.
- Add React input and custom-combobox fixtures where `form_snapshot` sees a value but the
  portal rejects it until native input events and option selection are completed.

### P2: Screenshot artifacts need an explicit path contract

An absolute repository path was rejected by the screenshot tool with a permission error.
Using a relative artifact name succeeded and stored the image in the server artifact
directory. The agent then had to copy the file into the application folder outside the MCP
operation.

Proposed behavior:

- Document and enforce an artifact root with a stable returned path.
- Accept an explicit allowlisted output directory when the caller has permission to use it,
  or provide an `artifact_export` operation that copies a server-owned artifact to a caller
  supplied path after validation.
- Return a content hash, byte count, MIME type, and relative artifact ID.
- Keep path traversal and arbitrary filesystem access blocked.
- Add a base64 or resource-link option for consumers that do not need a local file.

### P2: Tab listing and closing need an idempotent lifecycle contract

During the live run, page inspection and form operations continued to work, but both
`tab_list` and `tab_close` intermittently returned an internal error caused by a rejected
WebSocket connection with HTTP 500. This prevented reliable reconciliation of the visible
tab set and made it unsafe to assume that a close operation had completed. A privacy-policy
tab could not be closed even though two application tabs were intentionally being preserved.

Proposed behavior:

- Make `tab_list` return the last reconciled tab inventory with an explicit `stale` marker
  when the browser transport is temporarily unavailable.
- Make `tab_close` idempotent: return `already_closed` when the target no longer exists and
  never report an ambiguous internal error after the close request may have been delivered.
- Return a stable tab identity, URL, title, active state, and lifecycle timestamp in every
  tab inventory.
- Require a positive inventory check before closing a tab, while preserving the one-tab
  safety rule even when the inventory is stale.
- Include a retryable transport classification separate from a browser-level close failure.

### P2: Add a high-level application-form workflow

The current tool set is expressive but forces repeated round trips for a common sequence:
discover form, fill known values, upload a file, select choices, review, submit, and classify
the result. A high-level workflow would be safer if it remained explicit and returned all
intermediate evidence.

Proposed behavior:

- Add an opt-in `form_prepare` operation that accepts a field map, choice map, combobox map,
  optional file map, and a list of fields that must remain untouched.
- Have it stop before submission and return a review object plus a screenshot.
- Add a separate `form_submit_after_review` operation that requires the review token and
  revalidates the form immediately before clicking submit.
- Return every field action, fallback, validation result, artifact, and final outcome in one
  structured trace.
- Keep submission a separate operation so callers cannot accidentally submit during a fill
  request.

## Priority plan for the follow-up implementation

### Phase 1: Contract stability and state correctness

- Implement one script-result normalization boundary.
- Define typed result models for fill, checkbox, choice, combobox, upload, and submission.
- Add controlled-input verification and native keyboard fallback.
- Add required-field and file-state pre-submit invariants.
- Add exact submission outcome classification.

### Phase 2: Custom controls and review ergonomics

- Implement semantic choice and checkbox operations.
- Make combobox interactions Unicode-safe and stale-handle resistant.
- Implement `form_preflight` and `form_review`.
- Add compact traces that retain evidence without returning full page dumps by default.

### Phase 3: Lifecycle and artifacts

- Complete browser reconciliation and safe reconnect after server restart.
- Make tab inventory and close operations resilient to transient WebSocket failures.
- Define screenshot and artifact export contracts.
- Add the opt-in prepare-review-submit workflow.
- Document tool-profile requirements and recovery states.

## Acceptance criteria

The follow-up implementation should be considered successful when all of the following hold:

- A React-controlled text fixture accepts a fill and a subsequent form submission sees the
  value without manual agent retries.
- A controlled input whose DOM value is changed without an input event is reported as
  unverified, not successful.
- Script evaluation returning an object, array, primitive, null, malformed payload, or
  exception produces a stable structured result.
- A custom Yes/No group can be selected by field label and returns the selected option with
  a verified semantic state.
- A custom checkbox can be set and verified through its native input when present.
- A combobox accepts accented queries, preserves the selected Unicode text, and returns a
  verified option after the dropdown closes.
- A required upload remains visible through validation retries or is reported as cleared
  before a second submission attempt.
- A form preflight identifies a required address line when the supplied candidate profile has
  no confirmed address line, without inventing data.
- A success confirmation, validation error, portal limit, security challenge, and unknown
  page are classified into distinct outcomes.
- A server restart can reconnect to an owned persistent browser or returns a clear handoff
  state without opening a duplicate profile or closing the only tab.
- A screenshot can be saved and later located through a stable artifact ID without requiring
  arbitrary filesystem access.
- Tab listing and closing remain safe and idempotent across transient WebSocket failures,
  with stale inventory and retryable transport states exposed explicitly.
- Relevant focused tests pass, followed by the repository gates in `AGENTS.md` when feasible.

## Suggested test matrix

| Area | Fixture or scenario | Expected assertion |
| --- | --- | --- |
| Script boundary | Object, array, primitive, null, malformed result | Stable normalized envelope |
| Controlled input | React state updates only on native input and blur | Fill is verified before success |
| Controlled input | DOM value changed without framework event | Result is inconclusive or fallback runs |
| Choice group | Repeated Yes/No buttons in separate sections | Field-scoped selection and active-state verification |
| Checkbox | Hidden native input with visible label | Checked state is verified after fallback |
| Combobox | Search and option with `í`, `ã`, and `ç` | Unicode query and selected text remain intact |
| Combobox | Dropdown rerenders option nodes | No stale resource error after selection |
| Upload | Validation failure clears the file control | Retry preflight reports re-upload requirement |
| Submission | Ashby-style success text | `confirmed` outcome |
| Submission | Application limit text | `portal_limit` outcome |
| Submission | Required-field error | `validation_failed` outcome with field labels |
| Lifecycle | Server restart with owned browser alive | Safe reconnect or explicit handoff |
| Artifacts | Relative artifact and approved export path | Stable ID, hash, and safe path behavior |

## Working-tree note

During the live run, small robustness changes were already present in the working tree around
framework-safe filling and element fallback behavior. They should be reviewed independently
from this report. The report is not an assertion that those changes are complete, and it does
not replace focused tests, full quality gates, or a design review of the lifecycle work.

## Live validation on 2026-08-12

The v2 workflow was exercised against the previously blocked Starbridge AI Engineer
application in a visible persistent browser using the `curriculum` profile. No submit click
was attempted because the page exposed a reCAPTCHA verification challenge.

Observed behavior and resulting changes:

- An immediate preflight after navigation could run before the Ashby form was ready and return
  no interactive fields. Waiting for a concrete required selector made the same page discoverable.
  The workflow should continue to expose this as a retryable readiness state rather than treating
  it as a permanent form failure.
- The active surface originally selected the visible `Upload file` button as the primary action,
  even though the final `Submit Application` button existed lower in the page. Final-action text
  is now prioritized across the complete active surface, including actions outside the viewport.
- Deep discovery found the application controls and optional diversity controls. Radio groups and
  non-actionable hidden or cross-origin frame nodes are now compared semantically so they do not
  create a false inventory dispute. A real form control inside an inaccessible frame must still
  remain a blocking disagreement.
- Deep discovery also found visible reCAPTCHA content inside an iframe. The workflow now returns
  an explicit security handoff, keeps the primary action as `Submit Application`, and refuses to
  issue a review token. It does not click or attempt to solve the challenge.
- Safe preparation is allowed to continue while a passive security control is present. The live
  run filled Name, Email, Phone Number, LinkedIn, the exceptional-work textarea, and the expected
  annual rate, selected B2B SaaS and both required `Yes` choices, selected Brazil, and accepted
  the dedicated resume PDF. All requested field operations returned verified v2 results, and a
  read-only review confirmed the values by length and the resume by native and rendered state.
- The final review remained blocked only by the security handoff, with no review token and no
  submit attempt. This confirms that preparation and submission are separated in practice.

Remaining follow-up items from this run:

- Reduce duplicate CAPTCHA signals from the same iframe into one compact security record while
  preserving source and frame provenance.
- Reconcile the fill result's nested state fields. The top-level verification and post-review
  value lengths were correct, but some fill responses reported an empty nested `dom_value` while
  reporting a present framework value. The public state should be internally consistent.
- The combobox returned the selected Unicode option and a new element ID, but its immediate state
  still reported `popup_open=true`. Add a close-state observation or a clear inconclusive result
  before a review can claim the popup was closed.
- Add a browser fixture for an Ashby-style page with a final action below the viewport, optional
  diversity groups, and a cross-origin reCAPTCHA iframe. This should cover the readiness retry,
  action selection, security handoff, and safe preparation sequence together.

### Greenhouse, Lever, and custom-control validation

The workflow was also exercised against live Greenhouse, Lever, and custom application pages
in the same visible persistent browser. No CAPTCHA or hCaptcha was clicked, and no final submit
was attempted when the portal required candidate action.

Observed results:

- Greenhouse discovery correctly exposed the final `Submit application` action and required
  fields on Nortal and Cresteo pages. It also detected reCAPTCHA as a security handoff. A role
  with unsupported exact technology thresholds was not filled or submitted because the canonical
  candidate evidence did not support inventing years for Jest, Terraform, GitLab, or named AWS
  services.
- On Cresteo, `form_prepare` stopped before mutation when the normal and deep inventories both
  contained duplicate representations of the same required fields. The planned labels were
  unique on the active surface, but the discovery safety check still treated them as ambiguous.
  The high-level workflow should accept a unique active-surface match when the plan includes the
  current element fingerprint or selector, while continuing to reject genuinely ambiguous fields.
- Direct `element_fill` on the Cresteo Greenhouse controls emitted top-level `verified=true` and
  correct value lengths. The nested state still reported an empty `dom_value` and
  `ready_for_submission=false` for the same operation. A subsequent review saw the values and no
  pending required fields, but the public state object must be made internally consistent before
  agents can trust it without a second observation.
- Greenhouse's custom Yes or No field was a combobox, not a radio choice group. Calling the choice
  tool returned `field_not_found`. Opening the custom flyout exposed one `Yes` option and the page
  then showed `option Yes, selected`. The combobox helper returned `option_not_found` even though
  the visible option had been selected, so selection must re-observe the trigger and popup after
  rerender and return the final semantic state rather than the intermediate lookup error.
- The Greenhouse resume input was created or replaced after the attach interaction. A first upload
  attempt returned a stale state, while the page visibly showed the correct filename. Subsequent
  state lookup using the old upload handle correctly returned `stale`. Upload verification should
  return the new control or upload identity after a portal replaces the native file input and should
  associate the visible filename with that new identity.
- On Talentus Global's Lever form, the workflow filled the confirmed identity fields, selected
  Brazil, accepted the dedicated PDF, and refused to select optional marketing consent. A second
  upload was rejected unless `replace_existing=true`, and explicit replacement returned state
  `accepted` with native and rendered evidence. The form remained blocked by hCaptcha and by an
  unsupported requirement for prior US-client experience, which was correctly not invented.
- On N-iX, the `EASY APPLY` action dispatched but produced no URL, tab, modal, or visible form
  effect. The click result was classified as `no_effect`, so no blind retry occurred. TeamStation's
  existing sidebar selector similarly demonstrated that an expectation selector already present
  before the click can create a false positive `visible_effect`; effect expectations must compare
  before and after identity, visibility, bounds, or content rather than presence alone.

Recommended live-regression fixtures:

- Greenhouse duplicate active and deep field representations with a custom portal combobox.
- Greenhouse upload control replacement after selecting a file.
- Lever hCaptcha form with optional marketing consent and a monthly or hourly salary field.
- Custom application action whose click opens no observable effect.
- Existing selector present before click, followed by no state change, to ensure the result is
  `no_effect` rather than `verified`.

### Workable reapplication and long-form regression

The Walter Senior Full Stack AI Engineer application was retried in the same visible
persistent browser after the previous run had been invalidated. The form was a useful
end-to-end regression because it combined a long DOM, duplicate label representations, a
required resume upload, an optional photo upload, several required text questions, and a
post-submit confirmation page.

Observed results:

- The original deep discovery cap produced a partial inventory on the long Workable page.
  Increasing the deep node budget to 2,000, allowing a bounded eight-second traversal, and
  increasing the element cache capacity prevented valid controls from becoming stale during
  reconciliation.
- Required state was preserved from both the native control and nearby visible context. The
  Resume input was correctly identified as required while the Photo input remained optional.
  This prevented the earlier mistake of associating the resume PDF with the photo control.
- The form snapshot no longer treated ordinary address helper text as a validation error.
  Validation evidence now requires an invalid state, an error role or live region, an error
  descriptor, or an explicit validation phrase.
- The same visible label appeared on a container and on its actual input. Scalar field plans
  now prefer the direct input, textarea, or select when no explicit element ID is supplied.
  This removed the duplicate Phone action observed during the live run.
- The review token was issued only after required fields, the required resume, visible errors,
  and the final action were revalidated. The submit operation consumed the token and dispatched
  exactly one click.
- Workable briefly exposed `required field` while the submission was settling, then rendered
  `Thank you!` and `Your application has been submitted successfully.` The confirmation waiter
  now gives a short bounded grace period to validation-like text when a positive confirmation
  pattern is configured. It still preserves security, authentication, attestation, portal
  limit, and permanent validation precedence, and it never retries the click.
- The final read-only confirmation returned `outcome=confirmed` and `confirmed=true`. The
  confirmation screenshot is available as artifact `artifact_982e149bed4b4c54` with SHA-256
  `17179d6f54d4adb6992a5f3d3fb6b289f02b9141ba76d004f1670228134a14d2`.
- The application used a conservative salary posture. No unsupported salary fact was invented,
  and the live run followed the caller's current USD 70,000 to USD 120,000 guidance when a
  salary response was required. The Walter form did not require a salary answer.

Regression tests now cover transient validation followed by visible confirmation and duplicate
label matching in favor of a direct form control. The named screenshot export attempt also
exposed a small API issue: a relative name without an explicit `.png` extension was interpreted
as an extension. Future screenshot naming should validate or append the requested format before
passing the path to the browser artifact layer.

### Delayed route and portal combobox validation

Additional live validation on 2026-08-13 exposed two timing and lifecycle cases in Ashby and
TeamStation-style application pages:

- A native click could already change the URL while the requested text or modal was still being
  rendered. The old observer returned `NO_EFFECT`, which encouraged an unsafe caller to consider
  retrying the click. The observer now records `url_changed`, waits only within a bounded grace
  window, and returns an `unknown` v2 result with a re-observation instruction when the requested
  effect is still pending. It does not retry the click. Text observation also includes visible
  content in open shadow roots.
- A delayed TeamStation modal appeared after the first observation window. Re-observation found
  the modal and the v2 workflow filled and verified its identity, contact, salary, notice-period,
  and resume fields. The review correctly stopped at the required application-terms attestation.
- On an Ashby form, the work-country combobox selected `Brazil` even though its option inventory
  was empty, while a separate nationality combobox accepted typed text but did not expose a
  matching option. The workflow correctly left nationality unresolved. Combobox discovery should
  distinguish an empty snapshot from a rendered portal option list and preserve the final trigger
  state after rerender before claiming selection.

The delayed-route regression is covered by a unit test. The remaining combobox lifecycle case
should receive a browser fixture with portal-rendered options and an option list that is created
after the trigger is resolved.

The same live run also confirmed two follow-up fixes:

- Fill state now exposes a consistent presence marker, length, framework state, and
  `ready_for_submission` value without returning the entered value. The previous empty
  `dom_value` combined with `framework_value=present` and `ready_for_submission=false` was
  corrected and covered by a unit test.
- Restart attach on Windows now checks process liveness with `OpenProcess` instead of
  `os.kill(pid, 0)`, which reports an invalid-parameter error for a live Windows process. The
  running Chrome was reattached by profile and target ID without opening a duplicate instance.

### Starbridge stale-control rerun

The Starbridge AI Engineer form was rerun after the stale-control fix in the same visible
persistent browser. The previous run had filled the form but reported the location combobox as
stale after React recreated the control while other fields were being updated.

Observed results:

- `form_prepare` now refreshes the active surface before combobox actions and re-resolves a
  replaced control by field key, selector, fingerprint, placeholder, or name. The action uses
  the new element ID and reports the previous ID as evidence of re-resolution.
- In the live rerun, the Name field remained verified after rerender. The location control was
  re-resolved, `Brazil` was selected through the rendered option, the popup closed, and the
  selection was verified with `re_resolved=true`. No blind retry was used.
- The form remained blocked for review because deep discovery reported a partial iframe error
  while the active surface itself was consistent. The workflow did not issue a review token or
  click submit. This preserves a safe handoff until the discovery condition is resolved or
  explicitly reviewed by the candidate.

The rerender regression is covered by a unit test that verifies recovery from an old element ID
using stable field identity. A browser fixture should still cover a portal combobox whose trigger
and option list are both recreated during the same interaction.

### LinkedIn Easy Apply contact form rerun

An additional live rerun on 2026-08-13 used the visible `curriculum` profile against a strong-fit
European role at Redcare Pharmacy. The application was intentionally not submitted because the
form offered a different account email and did not expose the candidate's canonical address as an
editable choice. This was a safe application blocker, not a reason to guess or substitute a
contact fact.

Observed MCP and workflow issues:

- A LinkedIn search with a German geo ID returned German results in the visible page, but the
  semantic response reported an empty location, `remote=false`, and blank role and company fields.
  The selected job detail also returned the whole page as `description_excerpt`. The page text and
  deep tree contained the correct location, title, company, description, and application link.
  Search and job snapshot responses need a canonicalization pass against the active surface before
  returning metadata.
- The LinkedIn Easy Apply helper could not resolve the visible application action even though the
  deep tree exposed an exact link with an accessible label and an application URL. A generic
  primary-action path eventually opened the contact dialog, but the action evidence identified a
  generic next-step button instead of the application link that caused the transition. The helper
  should resolve application links by href, accessible label, role, and active job identity, then
  report the exact resolved control and transition.
- `form_preflight` correctly found the contact fields and returned a v2 blocked response when the
  required city was empty. It also returned `partial=true` because deep discovery attempted to
  inspect an iframe using `http://localhost:None/json/version`. The live browser was attached and
  usable, so a missing CDP port in lease metadata should not produce an invalid endpoint during
  same-process discovery. The attach and discovery layers should refresh or reuse the live browser
  endpoint before traversing iframes.
- Native text fields for name, phone, and city were filled and verified with the v2 contract. The
  form choice helper then returned `field_not_found` for the visible `Email address` select even
  though preflight had returned the field and a stable element ID. The choice operation should
  accept the preflight field key or element fingerprint, not depend only on a localized label.
- The low-level select operation returned `success=true` for a requested email label that was not
  present and returned inconsistent index and value evidence. The actual selected value remained a
  different account address. A select operation must return `not_found` or `inconclusive` when the
  requested option is absent, and must verify the final selected label and value after the native
  change event. A success alias must never hide a mismatch between requested and observed options.

Recommended follow-up tests and changes:

- Add a LinkedIn fixture with an interop iframe or equivalent portal surface containing an Easy
  Apply link, a localized accessible label, and a contact form with a select whose requested option
  is absent.
- Add a contract test asserting that search metadata is rejected or marked partial when the visible
  result, URL filters, and semantic fields disagree.
- Add select tests for absent labels, placeholder options, duplicate labels, Unicode normalization,
  index and value mismatches, and post-change selected-state verification.
- Add a lifecycle test where the browser registry is healthy but lease metadata has a null CDP port.
  Discovery must not construct a `localhost:None` endpoint, and attach must either repair the lease
  or return a clear handoff.
- Make Easy Apply action resolution return the resolved href, job ID, surface, before and after URL,
  and the exact effect classification. If the transport or effect is unknown, the caller must not
  retry the application action.

The JUPUS Ashby application provided a useful positive control for the field and upload layer. All
required text fields survived stabilization with `framework_value=present`, the resume reached
`state=accepted` and `rendered_state=present`, the visa-support and permanent-employment choices
were rendered with the selected class, and the optional two-year retention consent remained
unchecked. The review still returned `status=blocked` solely because the same missing CDP port and
surface disagreement prevented a review token. This confirms that the mutation and upload layers
are materially more reliable than the final lifecycle and discovery gate in the current runtime.

### Teamtailor application widget rerun

The SDG Group AI Architect role was tested through its visible LinkedIn application link and the
observed Teamtailor career page. The role is a strong European fit and the dedicated resume passed
the repository validation checks. The external page rendered the job details and a visible `APPLY`
button, but the embedded application area remained at `Loading application form` after the button
was resolved and clicked.

Observed MCP issues:

- Deep discovery returned the visible `APPLY` button with a stable semantic description and exact
  bounds. The native click response classified the transport as `dispatched` and `verified`, but
  page effect verification correctly returned `no_effect`. This is a useful distinction, but the
  response should include a more explicit application-widget diagnostic when the target is a custom
  element and the form remains in a loading state.
- After the click, no actionable form controls or iframe appeared in the active surface, while the
  page continued to expose `Loading application form`. The workflow could not safely call
  `form_preflight` or prepare a review. It must keep this state blocked and must not retry the apply
  click automatically.
- The cookie modal produced a candidate during deep text discovery, but the subsequent cached
  element could not be resolved by `element_click`, and the text helper returned no visible match.
  Candidate IDs from discovery should carry a short-lived surface generation and the action layer
  should either re-resolve them in the same surface or return a clear `stale` result instead of a
  generic resolution failure.

Recommended follow-up tests and changes:

- Add a Teamtailor fixture in which a custom application widget remains loading after a successful
  button dispatch. The expected result is `effect_status=no_effect`, `application_state=loading`,
  and a retry recommendation that does not repeat the click blindly.
- Detect loading placeholders and report the widget owner, observed custom element, URL, and last
  successful network or surface transition in the evidence object.
- Add a contract test for discovery candidates invalidated by a modal or surface generation change.
  Actions should re-resolve by text, role, bounds, and context, or classify the candidate as stale.
- Keep `form_preflight` read-only and blocked when the external form is not present. Do not infer
  that a visible job page or enabled primary action means that an application form is ready.

### SoSafe end-to-end v2 workflow rerun

The SoSafe Staff Engineer for IT Automation and AI transformation application was used as a live
regression after the MCP restart and form workflow changes. The browser remained visible on the
persistent `curriculum` profile, and attach reconciled the Ashby target by target ID without
creating a duplicate tab.

Observed results:

- The new choice discovery found both custom Yes or No groups, preserved their visible question
  labels, and reported the selected states as `No` for EU or UK work authorization and `Yes` for
  future sponsorship. The groups were included in the form fingerprint.
- The deep surface comparison originally counted two invisible checkbox inputs and an invisible
  `g-recaptcha-response` textarea as interactive controls. Ignoring invisible deep nodes for the
  comparison removed the false disagreement while retaining the ignored count as evidence.
- A deep iframe traversal still returned the known `http://localhost:None/json/version` error.
  Because the active surface was consistent and no field was frame-scoped, the workflow retained
  the error as a partial warning without blocking the review token. A frame-scoped field must
  continue to block until the frame is accessible.
- The custom choice resolver initially reported `ambiguous_option` for the first `No` because a
  hidden input and a rendered button contributed the same semantic option. Filtering rendered
  buttons and deduplicating option references fixed the resolver. Choice comparison now preserves
  NFC Unicode text instead of applying implicit ASCII folding.
- The v2 review verified the required text fields, the visible `Submit Application` action, the
  selected custom choices, and the dedicated resume upload. The salary field was filled with
  `70000`, the lower end of the caller's current conservative salary guidance.
- The first authorized submit dispatched one click and returned `validation_failed` with visible
  text identifying `Name`. The DOM contained the full name, but the portal's controlled state had
  not accepted the earlier programmatic mutation. No automatic retry was made.
- A single keyboard repair on the exact Name control returned `framework_value=present`,
  `framework_event=true`, `controlled_value_survived=true`, `blurred=true`, and
  `ready_for_submission=true`. The rendered portal error disappeared, the resume remained
  accepted and visible, and a new review token was issued.
- The second authorized submit dispatched exactly one click. The confirmation waiter returned
  `unknown` because the portal used `Your application was successfully submitted.` while the
  success matcher only covered shorter variants. A read-only page observation then found the
  visible `Success` page and the full confirmation sentence. The application was therefore
  recorded as `confirmed` in the tracker, with confirmation artifact
  `artifact_5dcf4b258c2145dd`.

Required follow-up changes from this regression:

- Add `was successfully submitted` and equivalent high-confidence success phrases to the
  submission classifier, with tests that keep URL-only changes and portal-limit text out of the
  `confirmed` outcome.
- Make final review expose framework verification details for fields previously mutated by
  `form_prepare`, or perform a bounded post-stabilization state read before issuing the token.
  A DOM value alone must not be enough when a controlled field can be rejected by the portal.
- Keep the post-validation recovery path explicit: identify the rendered field error, re-resolve
  the exact control, allow one evidence-backed repair, verify the upload again, and require a new
  review token before another submit click.
- Treat an accepted upload on a replaced native input as a new upload identity and preserve its
  visible filename in the final confirmation evidence.

### Admiral Attrax and Filestack application rerun

The Admiral Group Solution Architect for GenAI application was opened from the visible LinkedIn
posting and navigated to the real three-page application flow. The role was a strong fit, and the
dedicated resume was generated and validated. The form was prepared with canonical data and a
conservative salary expectation of GBP 70,000 per year because the form required a value and the
posting did not publish a range.

Observed results:

- The v2 fill workflow verified the forename, surname, location, postal code, email, phone, salary,
  and notice fields with `verification=verified` and `ready_for_submission=true`. This validates
  the unified fill contract on a non-React multi-page form.
- The v2 choice operation verified `Degree` and the explicit Disability Confident answer `Yes`.
  Native select handling verified the support or consideration answer `No`.
- The portal uses a Filestack picker. The form field itself is a hidden `js-filestack-input`,
  not a native file input. Calling `upload_files` on that field first returned a state conflict,
  then correctly rejected it as not a file input. Opening the visible Filestack picker, resolving
  its transient `#fsp-fileUpload` input, selecting the dedicated PDF, and clicking the picker
  `Upload` control completed the widget flow. The filename became visible in the form.
- After the widget upload, `file_upload_state` still reported `native_input_state=empty` and
  `rendered_state=present`, with a warning that the browser input had no accepted file. This is
  not a reliable rejection because the portal stores the Filestack result in a hidden application
  field. The upload contract must support third-party picker identities and distinguish a pending
  or accepted remote asset from an empty native input.
- The declaration checkbox text included privacy notice acceptance, application notifications,
  permission to hold sensitive personal data, fraud prevention agency sharing, and a truthful
  information declaration. It was left unchecked because it is a candidate confirmation and
  sensitive consent. No Save, Next, or final submission action was clicked.
- Despite that visible declaration, `form_preflight` and `form_review` returned no attestation
  handoff, no blockers, and `ready_for_submission=true`. The entire fieldset was incorrectly
  grouped as a non-required checkbox group, and the surrounding text was not classified as a
  sensitive declaration.
- Required markers rendered as asterisks were also not reflected in the native `required` flag.
  Required detection must use native validity, visible mandatory markers, portal validation rules,
  and semantic labels together. A ready review must never be issued while an unchecked sensitive
  declaration is visible in the active form.

Required follow-up changes from this regression:

- Add a dedicated third-party upload adapter boundary for Filestack-like pickers. It should track
  the logical field, picker input, picker session, remote asset name, remote asset status, and the
  hidden portal field separately. It must return `processing`, `accepted`, `rendered`, or
  `accepted_with_verification_warning` instead of treating the native input as the only source of
  truth.
- Detect sensitive declaration text in containing fieldsets even when the fieldset also contains
  education, diversity, or other radio controls. Split child controls into logical groups and
  associate the declaration checkbox with its own full text, rather than using the containing
  fieldset label as the group label.
- Expand attestation detection for privacy, employment checks, sensitive personal data, fraud
  prevention, notifications, truthful declarations, and permission statements. The result must
  include `requires_candidate_confirmation` and block review-token issuance until the candidate
  confirms the declaration through an allowed handoff.
- Treat visible asterisk markers and portal validation metadata as mandatory signals when the DOM
  `required` attribute is absent. Keep the raw source of the mandatory inference in evidence.
- Add an Attrax and Filestack fixture covering a hidden portal field, transient picker input,
  remote upload completion, mixed logical groups in one fieldset, and a mandatory sensitive
  declaration. The acceptance test must assert that `form_review` is blocked and never issues a
  submit token while the declaration remains unchecked.

### EPAM AI Solution Architect application rerun

The EPAM AI Solution Architect application was opened from the visible LinkedIn posting and
tested in the real EPAM Careers modal. The role was a strong technical match, but the posting is
restricted to Latvia and the form contained a mandatory Candidate Privacy Notice acceptance.
The dedicated resume was used and no consent checkbox or submit control was activated.

Observed results:

- The visible Apply button ignored the native click and the centered mouse fallback. The
  `dispatch_pointer_sequence` strategy opened the application dialog and verified the visible
  `Application` effect. The click contract therefore recovered the interaction without a blind
  repeat.
- The v2 fill workflow verified name, surname, email, phone, and years of experience. The phone
  field has a separate `+55` country selector and rejects the full international string. The local
  number `21 99833 0989` was accepted and survived input, change, blur, and stabilization.
- The React Select controls initially returned `option_not_found` or left the popup open even
  when the portal had rendered the desired option. A reliable directed sequence was to open the
  field, locate the rendered option by its current role and fingerprint, click that exact option,
  and use Enter only when the component required keyboard commitment. This verified Latvia as
  the preferred work country, AI Solution Engineering as the primary skill, Proficient (C2) as
  the form equivalent of the canonical Fluent level, and One week as the notice period.
- Current City remained unresolved. Typing Brasilia or Brasília did not produce a rendered option,
  and the combobox helper returned a retryable no-match result. The workflow correctly avoided
  inventing a city or reporting a selection that was not visible.
- The resume input is hidden and its first upload attempt returned a state conflict because the
  runtime registry still described a rendered upload while the native input was empty. An
  explicit replacement attempt returned a stale element, after which the page displayed the
  filename and a visible portal error: `The file shouldn't be less than 0.01 Mb.` The final
  `form_review` correctly classified this as a validation blocker and did not issue a review token.
- The form visibly displayed the required Candidate Privacy Notice checkbox and text stating that
  the applicant consents to EPAM processing personal data. The checkbox was left unchecked. The
  review response still returned no attestation handoff, so privacy attestation detection remains
  incomplete even though the independent upload validation blocker prevented readiness.
- The iframe discovery warning for `http://localhost:None/json/version` was retained as evidence
  without blocking the active form, because no field was scoped to that iframe. This is the
  intended partial-discovery behavior, but the warning should remain visible to the caller.

Required follow-up changes from this regression:

- Add an autocomplete adapter for asynchronous location fields. It should preserve query text,
  wait for loading completion, observe the portal option list, and return `not_found`,
  `timed_out`, or `inconclusive` with the active country context rather than silently leaving a
  required city empty.
- Make React Select option operations wait for the portal list after each query, resolve the
  current role option by label and bounds, and report whether click or keyboard commitment was
  required. Do not let a successful text observation substitute for selected state.
- Reconcile upload state after a rerender by resolving the current input and its rendered preview
  as one logical upload. If the portal imposes a minimum size, return the visible validation text,
  measured byte size, and a recovery instruction. Do not classify a filename alone as accepted.
- Detect privacy notice acceptance as `requires_candidate_confirmation` even when the checkbox is
  not exposed through native `required` metadata. A visible asterisk and consent language must
  block review-token issuance until the candidate performs the handoff.
- Add fixtures for an async city autocomplete, a React Select portal list, a hidden upload with a
  minimum-size validation, and an EPAM-style privacy checkbox. The acceptance test must assert
  that no submit token is issued while the city or privacy declaration remains unresolved.

### JUPUS AI Lead application rerun

The JUPUS AI Lead application was used as a real end-to-end test of the v2 workflow after the
server restart and after the earlier Ashby failure. The form was a remote permanent employee
role with Germany, Portugal, Romania, Spain, and the United Kingdom listed as hiring locations.

Observed results:

- The Ashby form exposed a stable interactive surface through open shadow roots. `form_preflight`
  identified required text fields, the resume input, two radio groups, optional pronouns, and the
  optional two-year data-retention consent.
- The normal framework-safe fill changed every planned field and returned a DOM-valid result, but
  the aggregate `form_fill_fields` result was `inconclusive` for an Ashby form even though each
  field was present. The workflow must keep this distinction and must not report the aggregate as
  ready without a stronger post-stabilization signal.
- Direct `element_fill` with `mode="keyboard"` successfully verified Name and several textareas,
  including `framework_value=present`, `framework_event=true`, `controlled_value_survived=true`,
  and `blurred=true`. This confirms that the per-element keyboard path is effective when the
  aggregate fallback path is bypassed.
- The aggregate keyboard fallback path returned `EXECUTION_ERROR` while evaluating
  `keyboard_fallback_allowed`. This is a production defect in the fallback orchestration. It
  should re-resolve the element after each rerender, isolate the security descriptor failure, and
  return a structured per-field error instead of aborting the whole operation.
- The direct keyboard path incorrectly classified some ordinary Ashby fields, including phone,
  notice period, current location, and the applied-AI leadership textarea, as security controls.
  The security gate must inspect the fresh element's type, name, autocomplete, and accessible
  label, and must not use a stale handle or a broad descriptor that creates false positives.
- Choice selection worked reliably. `form_select_choice` selected the truthful `No` answer for
  visa support and `Yes` for permanent employment, returning `selected_state="selected"` and a
  visible selected label. This is a positive result for custom button controls.
- Upload handling worked reliably in this fixture. The resume returned `accepted`, native input
  state `present`, rendered state `present`, filename evidence, and MIME and size metadata.
- `form_review` produced a review token and `ready_for_submission=true` while leaving the optional
  retention consent unchecked. It included the pre-submission screenshot artifact and retained the
  iframe warning as a nonblocking discovery warning.
- `form_submit_after_review` executed exactly one click, consumed the token, and classified the
  portal response as `requires_candidate_confirmation` because the visible form still required
  the two-year data-retention declaration. No retry was attempted. This is the desired safety
  behavior for sensitive consent, although the review phase should surface the exact attestation
  text before submit so the handoff is clearer.

Required follow-up changes:

- Fix the `form_fill_fields` keyboard fallback orchestration and add a fixture where a controlled
  Ashby or React-like input rerenders after each field.
- Make `keyboard_fallback_allowed` return a typed result with `allowed`, `reason`, and `descriptor`
  classification, while redacting the descriptor in public responses. Test ordinary phone,
  location, notice, and textarea fields against CAPTCHA, OTP, payment, and identity controls.
- Re-resolve the target immediately before the keyboard fallback and after every rerender. A stale
  handle must produce `stale` or `inconclusive`, never a generic security block.
- Include optional but submission-blocking privacy or retention declarations in
  `attestation_handoffs` with their exact visible text before an authorized submit is attempted.
- Add an Ashby fixture with a custom button radio group, shadow-root resume input, optional privacy
  retention consent, and a submit response requiring candidate confirmation.

### Follow-up fix validated on the live JUPUS form

The Ashby fallback defects above were fixed and validated against the same visible browser session
after restarting the MCP server and reconnecting the persistent `curriculum` profile:

- Ordinary form controls now use a native attribute safety descriptor. Phone, notice period,
  current location, and textarea controls no longer depend on a fragile JavaScript inspection
  result or become false security handoffs. Explicit password, CAPTCHA, OTP, payment, biometric,
  and identity-verification signals remain blocked.
- Cache fallback now preserves the original XPath or selector when metadata collection fails. This
  gives the resolver a usable reference instead of silently falling back to an unrecoverable stale
  handle.
- Keyboard verification reads the current post-rerender node through the page reference before
  using a cached Pydoll element. This prevents `read_filled_state` from failing after an Ashby or
  React controlled input replaces its DOM node.
- Aggregate `form_fill_fields` now requests keyboard fallback whenever the requested verification
  level lacks framework-event, controlled-value-survival, or blur evidence. The operation keeps
  the same normalized `filled` records instead of losing per-field updates during JSON
  normalization.
- Live validation on the JUPUS form passed for notice period, current location, and applied-AI
  leadership fields. All three fields used the keyboard fallback, returned `verified`,
  `framework_event=true`, `controlled_value_survived=true`, `blurred=true`, and
  `ready_for_submission=true`. No submit was issued during this validation.

The remaining JUPUS blocker is the separate two-year data-retention declaration. It is a sensitive
candidate confirmation and must remain a handoff rather than an automated choice.

### Square One Resources LinkedIn upload regression and live validation

The visible LinkedIn Easy Apply form for Gen AI Solution Architect was used to test the resume
upload path after the server restart. The first attempt exposed two distinct defects:

- The LinkedIn adapter returned `KeyError: 'result'` when Pydoll attempted to read `outerHTML` or
  text from the hidden file input. The input had been discovered, but diagnostic text collection
  failed before the upload operation could continue.
- The generic upload path also reported that the resolved element was not a file input because the
  hidden control had been replaced between discovery and mutation. The public result correctly
  did not claim that the PDF had been accepted.

The fixes were implemented and tested as follows:

- The Pydoll compatibility boundary now treats transient `KeyError`, transport, and stale-element
  failures while reading diagnostic text as an empty text value. Visibility diagnostics fail closed
  to `false`, while the element remains available for a fingerprinted action.
- Enhanced upload handling now converts native upload transport failures into structured retryable
  errors with a reason instead of leaking a raw exception. The LinkedIn adapter can then continue
  to its chooser interception path.
- A regression test covers the LinkedIn native transport failure followed by chooser interception.
  The compatibility resilience test covers an unavailable hidden-element text response.

Live result on the visible `curriculum` browser profile:

- The dedicated PDF `Yuri_Abreu__gen_ai_solution_architect__square_one_resources.pdf` was accepted
  by LinkedIn through `chooser_intercept`.
- The filename became visible in the resume step and the upload result returned
  `upload_verified=true` with `verification_basis=["selected_resume"]`.
- The workflow advanced through required Microsoft Azure, Microsoft Products, and management
  questions, removed the optional follow-company checkbox, and submitted once.
- LinkedIn displayed the visible confirmation `Candidatura enviada`. A full-page confirmation
  artifact was captured with an artifact ID and SHA-256.

Additional follow-up work remains:

- The specialized LinkedIn forward resolver did not recognize the localized `Revisar` action even
  though it was the correct final review transition. The generic element resolver handled the
  exact button safely in this run, but the LinkedIn adapter should recognize localized review
  labels and return a typed transition result.
- The LinkedIn screenshot tool requires a relative name with an explicit `.png` extension even
  when `fmt="png"`. The contract should append or validate the extension consistently.
- Upload verification should expose the difference between a selected server-side resume and a
  native input whose `files` list is empty. In this run the visible filename and selected resume
  were sufficient portal evidence, but the warning should remain available to callers.

### LinkedIn result-card identity guard

During the next live validation, `linkedin_easy_apply_open` was called after selecting Shakers'
Senior Python Backend Engineer card from a Spain search result list. The resolver clicked the
neighboring IOON card instead and opened IOON's form. The adapter reported an application surface,
but it did not prove that the surface belonged to the active job. No field was filled and no
submission was made because the caller compared the visible employer and role before continuing.

The adapter now captures the active LinkedIn job ID before the apply action and compares it with the
job ID in the resulting application surface URL. A mismatch returns a retryable `STALE_ELEMENT`
error with expected and actual IDs, instead of presenting the wrong form as ready. The unit suite
covers this mismatch, and the browser was reattached to the persistent `curriculum` profile after
the server restart. Direct job detail and already-submitted surfaces continue to be accepted when
their identity is consistent.

The remaining improvement is to make result-card selection itself accept a caller-provided job ID
and resolve only the matching card before clicking. The post-click guard is the safety boundary for
callers that still use the current public contract.

### Tech Mahindra live validation and link-based Easy Apply fallback

The next live test used the visible `curriculum` profile for Tech Mahindra's `Sr. Engineer - Python
with Prompt Engineering` vacancy, LinkedIn job ID `4451666938`. The job identity was checked before
opening the application and remained consistent through the confirmation page.

The test exposed a remaining portal variation. LinkedIn rendered the Easy Apply CTA as an anchor
with localized text `Candidatura simplificada` and a job-specific `/apply/` href. The specialized
`linkedin_easy_apply_open` action resolver did not recognize that control in the active surface and
returned a retryable resource-not-found result. The generic click resolver also produced no page
effect. No form field was touched during those failed attempts.

The fallback now searches for the localized anchor, requires exactly one candidate whose href
contains the same active LinkedIn job ID, and navigates only to that verified URL. It then waits for
the application surface and applies the existing job identity guard. Ambiguous links or links for a
different job are rejected without navigation.

Live result after the fallback was used:

- The application dialog opened and was recognized as a one-step Easy Apply form.
- The dedicated resume was uploaded and verified by the selected visible resume filename.
- LinkedIn's optional company-follow checkbox was explicitly unchecked.
- The form contained no security challenge, attestation, or authorization question.
- Exactly one submit click was sent, and LinkedIn visibly displayed `Candidatura enviada agora`.
- Pre-submit and confirmation screenshots were captured as PNG artifacts with artifact IDs and
  SHA-256 hashes.

The regression suite covers the link fallback, job-ID validation, and the existing no-effect and
wrong-job protections. The live result indicates that the interaction layer is materially more
reliable, while portal-specific localized labels and iframe-backed surfaces remain an area for
continued fixture coverage.

### CAS Training live validation and security handoff

The next live test used LinkedIn job `4448757468` for CAS Training's `Software Engineer Python
Senior - IA / Agentes de IA` after restarting the MCP server and reconnecting the visible persistent
`curriculum` profile. The previously opened Easy Apply dialog survived the reconnect and remained
associated with the correct job.

This form exposed several additional interaction defects and one correct safety stop:

- After the resume step, `linkedin_easy_apply_click_next` timed out even though the dialog remained
  visible at 67 percent and had advanced to `Preguntas adicionales`. The specialized
  `linkedin_easy_apply_snapshot` also reported `surface=none` and `dialog_present=false` while
  `page_get_text`, `page_get_active_surface(scope="dialog")`, and the interactive summary all
  showed the live dialog and its seven required fields. Surface detection for this LinkedIn
  question step is therefore inconsistent.
- `linkedin_easy_apply_fill_questions` returned `surface_not_found` for the same visible dialog.
  The aggregate `form_fill_fields` path also failed to match the Unicode question labels. The
  generic active-surface resolver returned fresh element IDs, and direct `element_fill` plus
  `element_select_option` then filled and verified all three numeric fields and all four select
  fields. The numeric fields reported `framework_event=true`, `controlled_value_survived=true`,
  `blurred=true`, and `ready_for_submission=true`.
- The specialized resume upload initially treated the visible `Cargar currículum` wrapper as a
  file input and returned `native_upload_transport_error`. The generic
  `upload_files_from_trigger` operation successfully used `chooser_intercept`, confirmed one
  file input, and verified the visible dedicated PDF filename. The localized trigger fallback was
  added to the LinkedIn adapter and covered by regression tests, but should receive a fresh live
  adapter-level check on a new form.
- The final read-only preflight correctly found an invisible LinkedIn reCAPTCHA security control.
  It returned a structured `security_control` blocker and did not issue a review or submit click.
  This is the expected safety behavior. No CAPTCHA or other security mechanism was bypassed.

The diagnostic screenshot was recorded as artifact `artifact_f513fc0a3ff146c7` with SHA-256
`adc4d200bb3afbec4cc188a0c94e67524dae5af210cb82388f5fb4361d8c51d7`.

Required follow-up changes:

- Make the LinkedIn Easy Apply snapshot and question filler reuse the common active-surface
  resolver, including dialog portals and localized Unicode labels.
- Normalize question matching with Unicode NFC while preserving the exact text sent to the page.
- Treat a successful next-step transition as verified when the active dialog and progress changed,
  even if the specialized snapshot schema cannot classify the new step.
- Add a fixture for a LinkedIn-style question dialog with numeric inputs, native selects, localized
  labels, and a reCAPTCHA iframe. The fixture must assert that the security handoff prevents submit.
- Add a live adapter-level test for the localized upload trigger fallback after the server restart.

### ReflexAI live regression validation

ReflexAI was selected as a direct regression case because an earlier attempt had been blocked when
the required AI-project textarea could not be edited through native Pydoll interaction. The same
visible persistent `curriculum` profile was used with the dedicated resume for `Sr. Software
Engineer (Latin America)`.

The revised interaction path succeeded on the previously failing control:

- `form_fill_fields` filled Name, Email, and the 406-character AI-project textarea.
- All three fields returned `verified`, `framework_event=true`,
  `controlled_value_survived=true`, `blurred=true`, and `ready_for_submission=true`.
- The form used the single keyboard fallback for each field after the automatic path was
  inconclusive. No stale handle or raw JavaScript result was exposed.
- `form_select_choice` selected and verified `7+ years` for B2B SaaS experience.
- The generic upload trigger path used the visible `Upload File` control and a native desktop
  picker fallback. A fresh deep lookup then reported the resume as `accepted`, with one file,
  PDF MIME type, 5,453-byte size, and visible filename evidence.
- `form_review` captured a pre-submission screenshot artifact and reported no missing required
  fields. It correctly remained `blocked` because Ashby exposed an invisible reCAPTCHA security
  control.

This is a successful interaction-layer regression result, not a submitted application. No CAPTCHA
was solved or bypassed, no submit click was sent, and the tracker records the vacancy as blocked
with the screenshot handoff.

Remaining follow-up:

- Keep the Ashby reCAPTCHA signal in the review result while making the visible candidate handoff
  clearer when the control is invisible.
- Add a browser fixture for a controlled textarea plus native upload trigger and an iframe-backed
  reCAPTCHA marker, asserting that all safe preparation actions can complete while submit remains
  blocked.

### Starbridge live validation and required-field review

Starbridge was used as a second live Ashby regression after the server restart. The form was for
`AI Engineer, EMEA / LATAM` and contained required identity fields, a LinkedIn URL, an exceptional
work textarea, a resume upload, and an expected annual rate. The advertised compensation was
`USD 120,000 to USD 140,000`.

The live workflow applied the lower-bound compensation policy and produced the following result:

- `form_preflight` identified the required fields and the Ashby reCAPTCHA control before any submit
  action.
- `form_fill_fields` filled all six planned fields, including `120000` for the expected annual
  rate. Every field returned `status=verified`, keyboard fallback evidence, framework event
  evidence, controlled-value survival, blur confirmation, and `ready_for_submission=true`.
- A fresh deep lookup of `#_systemfield_resume` followed by `upload_files` accepted the dedicated
  PDF and exposed the filename in the rendered form.
- `form_review` returned `status=blocked`, no pending required fields, an accepted resume state,
  and a security blocker for the invisible Ashby reCAPTCHA. No submit click was sent.

This confirms that the v2 fill and upload path can prepare a real Ashby form while refusing to
cross a security handoff. The review result and screenshot were recorded in the application
tracker. The test also confirms that salary handling should be part of the preparation plan: use
the lower advertised value when a field is mandatory, and omit it when optional.

### LinkedIn Easy Apply no-effect regression

Several live LinkedIn Spain vacancies exposed a different failure mode. The exact Easy Apply
button was resolved with a fresh deep lookup and had a valid label, job identity, and non-zero
bounds. Native click returned a verified dispatch, but the page produced no dialog, no URL change,
and no active-surface change. Center-mouse and the safe trusted fallback produced the same no-effect
result. A direct `/apply/` route redirected to the normal job page.

The correct classification is `unknown` or `no_effect`, not a successful application. The server
must not retry such a click indefinitely because the transport may have succeeded while the page
effect is delayed or hidden. The caller should preserve the job ID and return an external-application
handoff when a verified external link exists. This live behavior should receive a fixture covering
an anchor-backed Easy Apply control whose click handler is inert or portal-dependent.

### Braintrust live validation and rich-text editor gap

Braintrust was tested through a LinkedIn external application route for a remote Lead AI and Data
Platform Engineer marketplace contract open to LATAM and Europe. The form advertised `USD 70 to
USD 120 per hour` for 20 hours per week. The lower option, USD 70 per hour, was selected because
it is consistent with the candidate's salary concern and is approximately within the desired
annualized range at the stated weekly commitment.

The improved interaction layer succeeded on the ordinary controls:

- Legal first name, last name, email, and LinkedIn URL were filled and verified with framework
  event, controlled-value survival, blur, and submission-ready evidence.
- The USD 70 rate and two-week availability choices were selected and verified through `aria-checked`.
- The resume reached the native accepted state through `upload_files`. The portal did not render a
  filename, so the public result correctly returned `accepted_with_verification_warning` instead
  of claiming complete visual verification.
- `form_review` captured a `pre_submission_review` screenshot with artifact ID
  `artifact_18ad4491f9594242` and SHA-256
  `a7b99e1c51cfcf60e241cb5dd9ec3ee9d8da7eebe90f89908089fbce0feee29f`.

The four required client questions used `div[contenteditable="true"]` rich-text editors. Both
`form_fill_fields` and direct `element_fill` returned structured inconclusive or execution errors.
The lower-level `element_type` operation reported characters typed, but fresh re-observation still
showed empty editors and the portal displayed required-field errors. Two question selectors also
contained curly apostrophes that were normalized incorrectly during selector matching, although a
deep class query could enumerate the four editors in document order.

This is a material reliability gap. A future rich-text adapter needs a semantic editor fingerprint,
scroll and focus handling, exact Unicode-safe label association, input and blur event verification,
post-render re-resolution, and a final text-presence check. It must never report success based only
on a key-count result. The fixture matrix should include contenteditable editors backed by React,
Slate, Lexical, and portal-rendered toolbars.

The same review also exposed two correct handoffs. Braintrust presented an invisible reCAPTCHA, and
the questions about legal authorization and visa sponsorship referred to an unspecified contracting
country. The MCP left both choices untouched rather than inferring facts from a multi-region remote
listing. No submit click was issued.

### Anyone AI live submit classification and anti-spam rejection

Anyone AI was used for a real live test of the new prepare, review, and submit boundary on a Brazil
remote Python Developer form. The form advertised `USD 45 to USD 80 per hour`. The ordinary fields
and the Python language choice were prepared with the dedicated resume:

- Name, email, phone, and LinkedIn returned framework event evidence, controlled-value survival,
  blur confirmation, and `ready_for_submission=true`.
- The resume reached the native accepted state and the rendered form exposed the filename.
- `form_review` correctly identified the invisible reCAPTCHA and returned a blocked review with a
  pre-submission screenshot. No security control was solved or hidden.
- Because the session had explicit autonomy, one real click was sent to the actual submit button.
  The page then displayed `We couldn't submit your application` and explained that the submission
  was flagged as possible spam. It was not classified as confirmation, and no automatic retry was
  sent.

This run validates an important distinction that should remain explicit in the public contract:
transport dispatch, portal acceptance, security rejection, and confirmed submission are different
states. A portal anti-spam response after a single click must invalidate the review token, preserve
the diagnostic artifact, classify the outcome as a portal rejection or security handoff, and return
a recovery recommendation without changing network settings or attempting to evade the control.

The diagnostic screenshot was recorded as artifact `artifact_73d4fb8a7d194622` with SHA-256
`8f713fdc2b1b5b376fa023d466956565feadcd9d94d7cda45c8865d4ee4cc191`.

The live run also exposed an artifact naming contract defect. `page_screenshot` rejected a name
without an explicit `.png` extension even when the format was already `png`; the same capture
succeeded after the extension was supplied. The tool should normalize or validate names before
dispatch and return the final relative path in the structured artifact record.

### Remote Crew live validation and custom location combobox gap

Remote Crew was tested through LinkedIn's verified external RecruitCRM link for a remote AI Engineer
role in Portugal. The published compensation was `EUR 50K to EUR 62K`, below the preferred salary
floor but considered because the role was fully remote and the upper bound approached the target.

The form was a React surface with open shadow-root controls. The new interaction path verified the
ordinary identity fields:

- First name, last name, LinkedIn URL, and email all succeeded with keyboard fallback, framework
  events, controlled-value survival, blur confirmation, and `ready_for_submission=true`.
- The visible Location field was marked required and exposed a custom button combobox showing
  `Not Selected`.
- Native click, centered mouse click, keyboard navigation, `combobox_get_options`,
  `combobox_type_and_select`, `combobox_select_option`, `form_select_choice`, and
  `page_click_primary_action` did not expose any options or change the selected state.
- The server correctly stopped before submission because the required location could not be
  selected from observed page state. A pre-submission diagnostic screenshot was recorded.

This is a remaining adapter gap, not a reason to accept an unverified location. Custom button
comboboxes should expose their trigger, popup association, option discovery, and selected state in
one semantic operation. The implementation should inspect `aria-controls`, `aria-expanded`, portal
containers, open shadow roots, and keyboard state, then re-resolve the trigger after the popup is
rendered. If no option surface is observable, the result should be `inconclusive` with a precise
control blocker instead of reporting the form as ready merely because ordinary fields are valid.

The diagnostic screenshot was recorded as artifact `artifact_53062c20442646d6` with SHA-256
`6f19a7a9edb2f8ecc370611dbb091b0c197bf9935080fc730e270cb5166cbffd`.

The Remote Crew form was retested on 2026-08-13 after the interaction changes and after the
candidate clarified the separate LinkedIn account and professional email roles. This time the
custom control was resolved successfully:

- `dispatch_pointer_sequence` opened the button combobox and exposed the portal options.
- `combobox_select_option` selected the exact observed option `Brazil` and verified the selected
  label and popup state.
- The native picker strategy uploaded the dedicated resume and kept one file in the native input.
  Because the portal did not render a filename in the page, the semantic state was correctly
  `accepted_with_verification_warning`, not fully rendered acceptance.
- `form_preflight` and `form_review` found the real `Submit Your Application` action. The review
  produced a token, but the form also contained an unchecked `I agree to Candidate Terms` legal
  declaration.

The declaration was intentionally left untouched and the application was not submitted. This is
the correct safety outcome, but it exposed a contract defect: the current preflight and review
responses did not classify the visible Candidate Terms control as an attestation handoff and still
issued a review token. Attestation detection must inspect nearby visible text, linked terms anchors,
fieldset context, and checkbox semantics before issuing a submission-ready token. A legal checkbox
must remain a blocker requiring candidate confirmation even when the portal does not mark it as
HTML-required.

The live evidence is `artifact_168cb9f60ab24786` at
`remote-crew-location-dropdown-resolved-no-submit.png`, SHA-256
`16fb8db7d96ccdf8263669aa769df36e787ebe65bf59f2e67cea2f2f7b982323`, and
`artifact_51b0d639312249f2` at `remote-crew-pre-submit-uploaded-manual-terms.png`, SHA-256
`4e392561f4be39075c36f277204ea79140583f2aed53ddeb5c1f183edccd3bb8`.

After the candidate explicitly authorized acceptance of the Candidate Terms, the same live form
was resumed. The exact checkbox was marked with `element_check`, revalidated as checked in the
DOM, and the review was regenerated. `form_submit_after_review` then consumed the review token and
sent exactly one native click. The portal displayed both `You have successfully applied to AI
Engineer` and `Thanks For Applying, We Will Reach Out To You Soon`, so this application was
classified as `confirmed`. The confirmation screenshot is `artifact_883cfd38e7554460` at
`curriculum/screenshot_e7a5d58922a2.png`, SHA-256
`9cd84655ef1bc73133cf47c1ac1273d9f18bf37f5c034ebb0bf781bef97b2424`.

The final run exposed three follow-up defects for the implementation backlog:

- The upload state retained the filename but reported a zero byte size after the native picker,
  although the source PDF was 9,105 bytes. The adapter should reconcile file metadata from the
  selected path or CDP state before returning `accepted_with_verification_warning`.
- Deep discovery returned a duplicate checkbox record for the same selector with `checked=false`
  while the exact native control and the shallow form record were checked. Merging should dedupe
  by stable selector and prefer the freshest native state.
- The review still did not classify the visible Candidate Terms declaration as an attestation
  handoff. Explicit authorization allowed this run to proceed, but future review contracts should
  expose the handoff and its authorization provenance instead of treating the control as an
  ordinary unchecked field.

### BJAK live submit test and controlled-field state loss

BJAK was used as a live test of the complete preparation path for an Applied AI Engineer role
in Portugal. The LinkedIn listing exposed an Ashby application URL. The server navigated to the
observed external URL, preserved the visible browser profile, and prepared the form without
manual JavaScript evaluation.

The safe preparation path worked for the ordinary controls:

- Name, email, phone, nationality, current country and city, and LinkedIn URL were filled through
  `form_fill_fields` with keyboard fallback, framework event evidence, controlled-value survival,
  blur confirmation, and `ready_for_submission=true`.
- Factual screening choices were selected and verified for visa requirement, software engineering
  experience, production AI delivery, LLM experience, Node.js, Python, AI evaluation, OpenAI, and
  DeepSeek.
- The resume upload returned `accepted` with native input state, rendered filename evidence, an
  upload ID, and a stable semantic upload state.
- A full-page `pre_submission_review` screenshot was captured as artifact
  `artifact_7c7f17044598414a` with SHA-256
  `3b8ee7954c9e3154cff24117ebb24ad9262c3db41b72fba90d4ebe3e4536d9ac`.

The form exposed an invisible reCAPTCHA. It also contained an optional recruitment-marketing
checkbox. The checkbox was left unchecked and was included in `do_not_touch`, but both
`form_preflight` and `form_review` classified it as an attestation handoff. This is too broad:
optional marketing consent should remain untouched without blocking a technically valid
submission when the portal permits the checkbox to stay clear. Security controls and legal or
candidate attestations still require a handoff.

With explicit session autonomy, one fresh lookup resolved the actual `Submit Application` button
and one real click was sent. No CAPTCHA was solved, hidden, bypassed, or retried. The portal
returned `Your form needs corrections` and reported nationality and current country and city as
missing, even though the immediately preceding fill and review states reported those controls as
verified and ready. The resume remained accepted and rendered. The submission classifier returned
`requires_candidate_confirmation` because it combined the validation evidence with the optional
consent handoff. The diagnostic screenshot was recorded as artifact
`artifact_9f192de539854502` with SHA-256
`be18e83da710d796c24a44c9b6d1568259a987a6cb3d1a96afe418772e12fa36`.

This exposes a second P0 issue in controlled forms: a field can satisfy a local verification
window and still be absent from the portal's submit state after another control or file upload
causes a render or validation cycle. `form_fill_fields` must perform a final fresh read after all
planned actions, and the workflow must verify that the portal's own validation model recognizes
the value before allowing a submit. A submit-time validation failure must be classified as
`validation_failed`, must invalidate the review token, and must never trigger an automatic retry.

### Starbridge live retry and semantic combobox false positive

Starbridge was retried after the earlier form preparation issue was resolved. The v2 path loaded the
form, filled the required text fields, selected the factual choices, selected `Brazil` in the custom
location combobox, accepted the dedicated resume, and captured a full-page pre-submission review.
The local evidence reported framework events, controlled-value survival, blur, and
`ready_for_submission=true` for the planned fields. The diversity survey remained untouched.

The form exposed an invisible reCAPTCHA. With explicit session autonomy, one normal click was sent to
the fresh `Submit Application` control. The click transport was classified as dispatched with no
immediate effect. The portal then returned `Your form needs corrections` and the specific error
`Missing entry for required field: Location`. A fresh preflight also saw the same portal validation
error even though the combobox still displayed `Brazil` and had been locally classified as verified.
The submission classifier correctly returned `validation_failed`, recorded a diagnostic artifact,
and the workflow did not retry.

This run narrows the remaining combobox requirement. A semantic selection result must include not
only the visible label and selected option value, but also evidence that the portal's own form state
will serialize that value for submission. For custom comboboxes, the adapter should verify the
associated hidden input or submitted form model after selection, re-read it after unrelated renders
and uploads, and mark the state `inconclusive` when only the visible trigger changed. Submit-time
validation errors should be associated with the logical field and invalidate any review token.

The pre-submission artifact was `artifact_540840c64ff64b20` with SHA-256
`bed68538b462485d07d836e1fc9aa7777192ef1ebc595267441461cb628b54e1`.
The validation-failure artifact was `artifact_1807a034d2a34268` with SHA-256
`769d9c0b636c18fdf3e90c16d50f825132bfbc88fda87bcef88bda07f295a4ec`.

### Additional live interaction findings

Three LinkedIn Easy Apply attempts were made through the actual job search context. MBN Solutions,
Wave Group, and Primis all exposed the expected Easy Apply control, but the click completed without
rendering a dialog or application surface. The observed state remained `unknown` with no submit
control, so none was retried or counted as an application. This confirms that a successful click
transport must not be treated as Easy Apply availability or submission readiness.

The Overt Minds `I'm interested` control and the InvestEngine Teamtailor `Apply for this job` control
also produced no application surface after native and safe mouse attempts. InvestEngine's cookie
decline control required the pointer-sequence fallback after native and centered mouse strategies
had no effect. These controls need an explicit no-effect result and a bounded fallback policy.

The Micro1 application exposed candidate terms and privacy agreement language in the `Next` action.
`form_preflight` did not identify that implied attestation and reported the page as ready. Action
metadata and nearby explanatory text must be included in attestation detection, not only checkbox
labels or separate legal controls.

The ReflexAI retry accepted the fields and resume, then returned a visible updating/upload warning
after one real submit click. The classifier produced a terminal `unknown` result and the workflow
did not retry. The submit wait should distinguish an ongoing portal update from a transport failure,
while preserving the same no-blind-retry rule.

### Storyblok Greenhouse live retry and security-challenge classification

Storyblok was used as a second live retry after the iframe handoff was observed through `frame_list`.
The cross-origin Greenhouse application URL was navigated with `page_goto`, preserving the parent-page
relationship in the handoff evidence. Ordinary text fields were verified through the centralized fill
path, and the resume became visibly accepted after the upload control was re-resolved. The upload
operation itself returned `stale` because the React form replaced the hidden file input during the
upload, even though the rendered filename and `Remove file` control proved that the file was present.
The upload adapter should return `accepted_with_verification_warning` in this case, with a fresh
semantic upload record, instead of exposing a generic stale state that loses the rendered evidence.

The React Select controls exposed a repeatable false positive. `combobox_type_and_select` reported a
verified selected option while the trigger still displayed `Select...` and the popup remained open.
Re-resolving the option and sending one pointer sequence to the exact option committed the selection
and closed the popup. The improved adapter must verify the trigger text, `aria-selected`, popup closure,
and the associated serialized value after the option click. A preselection or focused option must not
be reported as `selected`.

After all required fields, choices, location, salary range, and resume were visually verified, one
normal submit click was sent with the session's explicit autonomy. No CAPTCHA or security code was
solved, read, hidden, bypassed, or retried. The portal then displayed an 8-character human-verification
code request sent to the candidate's email. The workflow correctly stopped, but
`submission_wait_for_confirmation` classified the state as `validation_failed` because generic
`required field` and submit-button text took precedence over the visible security challenge. Security
and authentication signals must take precedence over validation, and the result should be
`security_challenge` with a clear candidate handoff. The server must never read email or request the
code without a separately authorized connector and explicit candidate action.

The pre-submission artifact was `artifact_70b8b03ae5ac4e54` with SHA-256
`b7296c3b5f934748741ce0e00cedf705d1e47bf960e0e506f4e138a036dc4899`.
The post-submit diagnostic artifact was `artifact_8b137ad7308d49b5` with SHA-256
`b5de8f333253a943a4e35e145e49e39c0d33373ff165f35b11752a25a22b7bfa`.

### Coforge LinkedIn Easy Apply live retry

Coforge exposed a visible `Candidatura simplificada` button for the Senior Generative AI
Engineer role. The dedicated Easy Apply operation first navigated to the job detail but did not
expose an application surface. After re-reading the page, the exact button was resolved again by
its fingerprint and received one native click. The click was dispatched, but no modal, form,
CAPTCHA, security handoff, or submit control appeared. The page remained on the job detail.

This is a useful negative result for the click contract. `element_click` correctly re-resolved the
element and returned `no_effect` with evidence instead of claiming that Easy Apply was ready. The
workflow then stopped without an unbounded retry. The Easy Apply adapter should expose the same
bounded lifecycle explicitly: `button_visible`, `click_dispatched`, `surface_opened`,
`surface_timeout`, and `blocked`, with a short diagnostic screenshot at the terminal state. A
visible button alone must not count as an available application surface.

The diagnostic artifact was `artifact_330719b1df3a4eb0` with SHA-256
`321efd871809c8a2db98e98ec8ce0a666152eccbf8ff40183351cd10d66126bd`.

### Archer Loxo form and optional contact consent

The Archer external Loxo form was a compact real application surface with name, email, phone,
an optional `contact_consent` checkbox, and an `Apply` action. `form_preflight` correctly detected
the optional phone and email marketing consent as an attestation handoff, and `form_prepare`
filled the three candidate fields with verified framework events, blur, validity, and value
survival while leaving the checkbox unchecked.

The workflow still returned `ready_for_submission=false` because an optional, explicitly untouched
consent was treated as a global submission blocker. The adapter needs a distinction between
`required_attestation_blocker` and `optional_attestation_handoff`. The latter should remain visible
in the review and never be selected automatically, but it should not prevent a normal application
submit when the portal allows the form to be submitted without it and the caller has authorized
the application. This distinction preserves privacy while avoiding unnecessary handoffs.

One authorized click was then sent to the fresh `Apply` control. The form stayed on the same page,
with no visible confirmation, validation error, CAPTCHA, or security challenge. No second click was
made. The result must remain terminal `unknown`, with a diagnostic artifact, rather than being
reported as confirmed or retried. The submission wait path also exposed a timeout risk when a
short observation window requested screenshot evidence, so evidence capture should be bounded
independently from outcome polling.

The diagnostic artifact was `artifact_8b09505ab75b43f7` with SHA-256
`825e97f6a2c53d4035e80d5515bb484f01450248b93f9f52c7fc39d109ef653a`.

### Software Mind SmartRecruiters live form and mandatory consent handoff

Software Mind was tested through the real SmartRecruiters OneClick form for an AI Engineer
role in Krakow. The form used Angular-like custom elements and open shadow roots. The browser
profile remained visible and the ordinary identity fields, phone country code, LinkedIn URL, and
resume were prepared through Pydoll.

The initial surface inspection exposed several adapter gaps:

- `page_get_active_surface` failed while the deep form was visible.
- `form_preflight` initially reported missing required fields and could not find the visible
  `Next` action, even after the exact shadow-root inputs had been filled. The discovery result was
  partial or disputed because the deep tree included many hidden custom-element descendants.
- Generic selectors can return both a custom-element host and the real inner input. Filling the
  host produced a false success or an execution error with no value, while a specific selector
  such as `input#first-name-input` produced framework events, blur, controlled-value survival,
  and `ready_for_submission=true`.
- `element_click` returned `no_effect` for the fresh `Next` button, but the page advanced to
  `Preliminary questions` immediately afterward. Click observation must allow a short delayed
  route or surface transition before classifying an action as no effect.

The screening page contained factual questions for work authorization in Poland, residence in
Poland, availability, contract type, salary in PLN, and language proficiency. The run verified
the following without inventing candidate data:

- `No` for authorization to work in Poland and `No` for current residence in Poland, both
  confirmed by the final `aria-checked` state.
- `1 week and less` for availability and `B2B contract` for the contract type.
- A conservative `180` PLN net per hour expectation for the B2B field, verified with `input`,
  `change`, and `blur` events, native validity, and controlled-value survival.
- `English` in the multi-select, verified by the selected tag after the option click.

The semantic combobox path still had a false-negative. `combobox_select_option` could not match
the visible `1 week and less` option even though the option text was present in the deep tree. A
fresh exact `div[role=option]` reference and one pointer-sequence click selected it successfully.
The same technique selected `B2B contract` and `English`. The adapter should preserve option text
and logical field identity across the shadow tree, prefer nonzero bounds, and verify the resulting
trigger text or selected tag before returning `selected`.

The final page required a privacy declaration checkbox and two mandatory personal-data processing
consent radio groups. These are legal or candidate attestations, so the run left them untouched,
did not click `Submit`, and recorded a candidate handoff. No CAPTCHA or other security challenge
was detected in this run. The workflow must distinguish these required consent blockers from
optional marketing consent, while still refusing to select either category automatically.

The diagnostic artifact was `artifact_53f7ba9ac9a34c88` at
`softwaremind-pre-consent-filled.png` with SHA-256
`7f53a3981fa50d5d8b66fde14029dbade7b3f8573f16c134f92c3d49306c1f9a`.

### Decskill LinkedIn Easy Apply live no-surface finding

The Decskill AI Enablement Engineer (Senior) listing was a strong live fit. Its visible
description requested production AI services, Python or TypeScript, LLM and AI API integration,
prompt engineering, RAG, MCP, AI agents, CI/CD, testing, containerization, cloud-native delivery,
and AI adoption across engineering teams. The role was remote in Portugal and exposed LinkedIn
Easy Apply.

The high-level Easy Apply operation navigated the observed link to a tracking URL but did not
expose a dialog or application surface within the wait window. A fresh active-surface inspection
then found hidden and visible text duplicates. The resolver selected the visible native button,
revalidated its fingerprint, and sent one click. The click was dispatched but the surface remained
absent. No form, CAPTCHA, authentication prompt, or security challenge was visible. The workflow
correctly stopped without another click and classified the application surface as unavailable.

This run confirms that the Easy Apply adapter needs a deterministic state machine that distinguishes
`link_navigation`, `button_visible`, `click_dispatched`, `surface_opened`, and `surface_timeout`.
The visible-control resolver must exclude hidden duplicates using bounds, visibility, active
surface, and job heading context. A tracking URL change alone must not be reported as a successful
Easy Apply opening. The terminal response should preserve the job URL, tracking URL, candidate
count, surface state, and screenshot artifact so a later retry can be explicitly authorized by a
new observation rather than by a generic retryable flag.

The diagnostic artifact was `artifact_0153bf9ee2384053` at
`decskill-linkedin-easy-apply-no-surface.png` with SHA-256
`ec9ec58da235f6e9d07459a554fbe91002310f998910068a280eb794a04a7152`.

### Digital Waffle LinkedIn Easy Apply and security-detector finding

The Digital Waffle AI Applications Specialist listing was remote in the United Kingdom with a
visible range of GBP 70,000 to GBP 80,000. The description focused on production AI systems,
agent workflows, multi-agent infrastructure, API and database integrations, and internal
automation. It also requested specific tools such as Clay, n8n, and OpenClaw that were not
confirmed in the candidate repository, so the role was recorded as partial fit.

The first interactive summary reported several possible two-factor controls, but the page had no
visible authentication text or challenge. A second inspection found no security controls, and the
live page showed the ordinary job details and Easy Apply button. This is a false-positive security
signal caused by discovery noise in the LinkedIn page and must not block a normal application by
itself. Security blockers should require a visible, relevant control or a corroborating semantic
signal tied to the active surface.

The Easy Apply link again navigated to a tracking URL without opening a form. A fresh visible
button was resolved and clicked once with fingerprint revalidation. No modal, form, CAPTCHA,
security handoff, or confirmation appeared. The click result was terminal unknown and was not
retried. The same bounded no-effect policy used for Decskill is appropriate here.

The diagnostic artifact was `artifact_bd78da22a17c4ffe` at
`digital-waffle-linkedin-easy-apply-no-surface.png` with SHA-256
`f2c83cb230f44a20accb4b753d43d21d98efaa30b40e0960d5a27c73d16b1bf3`.

### Kake LinkedIn Easy Apply delayed surface and role-specific email handling

The Kake Senior AI/LLM Engineer listing was a strong fit for the candidate's
production Python, LLM, RAG, API, evaluation, and agent experience. The role
was remote from Poland and the description exposed a meaningful technical
match.

The first high-level Easy Apply call returned no effect and no active surface
after its wait window. A later inspection found that the form had appeared
asynchronously. The previously resolved visible button was stale by then,
which shows that the adapter must re-snapshot after a delayed surface event
and must invalidate cached element references when the dialog is replaced.

The opened contact form exposed only the authenticated LinkedIn account email,
which is a valid candidate fact for LinkedIn Easy Apply. The professional email
and the LinkedIn account email serve different purposes, so the previous
workflow incorrectly treated the account email as a `candidate_data_mismatch`
and paused a viable application. The machine-facing candidate configuration
must expose both roles explicitly.

The Easy Apply state machine should use a short bounded stabilization period
after the initial timeout, then return the observed surface state, refreshed
field fingerprints, and the semantic role of each contact value. A delayed
dialog must not cause a blind second click, and a stale element must trigger
re-resolution only when the new observation proves that the action remains
safe. Email validation must compare against the correct role, not require
every portal to use the professional email.

The diagnostic artifact was `artifact_a67c97d8e8c44778` at
`kake-linkedin-contact-email-mismatch.png` with SHA-256
`183f04b5f93ef99f9e8d463d1a0f7bbfbefa99144e7fa0a504c6732fcda31881`.

The candidate then clarified that the account email is an authorized and
intentional LinkedIn contact value. The repository now records the
professional email and LinkedIn account email as separate roles. After that
clarification, the application was resumed and the form completed through
its contact, resume, questions, and review stages. A dedicated Kake resume was
uploaded and verified, the optional company-follow checkbox was cleared, and
one submit click produced the visible LinkedIn confirmation `Candidatura
enviada agora`.

This live run validated several v2 behaviors: delayed Easy Apply recovery,
fresh element resolution after a stale reference, explicit upload verification,
semantic checkbox state verification, pre-submit evidence, and confirmation
classification. The high-level forward helper also exposed a remaining gap:
the final intermediate action was labeled `Revisar` rather than `Avançar`, so
the helper returned `target_not_found` even though the button was visible and
enabled. A generic forward operation must discover the active primary action
from the current surface and accept localized labels such as `Revisar`,
`Review`, `Next`, and `Avançar` without weakening fingerprint or effect
verification.

The pre-submission artifact was `artifact_93a6ba673dba4656` at
`kake-pre-submission-review.png` with SHA-256
`b225d60f6493b2a050d662b515a9b33a016eaaa71c7545a771c7615071379ea7`.
The confirmation artifact was `artifact_b6cdd58cbbd342c2` at
`kake-submission-confirmation.png` with SHA-256
`91b2299a4be7650ca069f08f30e4e7db7e1d8f492a7281b31a608e5cb60272cf`.

### CUBE AI live geographic eligibility blocker

The CUBE AI Senior AI Engineer, Models listing had a strong technical match,
but its visible description explicitly stated that the employer could not
hire outside Lithuania and did not provide visa sponsorship. Since the
candidate is based in Brazil and requires sponsorship for international
employment, no application interaction was attempted after the restriction
was verified.

The preflight layer should extract and classify explicit geographic hiring and
sponsorship restrictions before opening an Easy Apply form. The result should
identify the employer domain, the evidence text, the candidate eligibility
conflict, and a terminal `not_eligible` recommendation. This avoids spending
interaction time on a form that cannot lead to a valid application.

### Current Europe search and regression retest findings

The current Europe-focused search exposed a second LinkedIn interaction failure in
addition to the no-surface behavior described above. The visible search page showed
more than 99 results, but `linkedin_jobs_page_snapshot` and
`linkedin_jobs_search_results` returned an empty result list after the page had
hydrated. Read-only DOM inspection found visible result cards with internal
`componentkey` values and stable job IDs, but native and centered mouse clicks on
the visible cards did not change the selected detail panel. The adapter should
model the search list as a virtualized surface, expose the card identity directly,
and verify a selected-job transition before reporting that a result was opened.
It should not require the caller to infer an ID from a private component
attribute, and it should not return an empty result set when visible cards are
present.

The same search page also produced repeated `two_factor` security findings from
ordinary filter and locality text. No authentication control, challenge, or
security handoff was visible. This corroborates the earlier false-positive
detector finding: security classification must require a visible relevant
control, a challenge-specific label, or corroborating state in the active form.
Page-level text containing words that resemble authentication labels is
insufficient evidence.

Several direct job pages in the same search batch exposed only the heading,
location, application type, and footer. The description was absent even after
network idle and active-surface inspection, so the workflow correctly refused
to claim a fit or begin a form. This occurred for Jobgether, FirstIgnite,
Proxify, AFFINITY, Production AI, Xcede, Newcode.ai, CUBE AI, and TensorOps.
The adapter should distinguish `description_unavailable` from an empty or
invalid description and return the observed surface, partial discovery errors,
and a compact recovery instruction. It should not silently promote a heading
only page into an application-ready candidate.

The diagnostic artifacts from this batch include `artifact_63a7703973bb4b75`
(`proxify-description-unavailable.png`, SHA-256
`09ce0a3e7c247f9a3a47ab5936dcc2c9d6a21f34ba1dbf6d4727cc3fa3cd0d7`),
`artifact_37c59ee83fe54a1a` (`affinity-description-unavailable.png`),
`artifact_f7866e6494334b6d` (`g3d-description-unavailable.png`, SHA-256
`344a069b828a0361ac2b2c7da1c31117c124e8c29b67b5da35ed0d7ce9e58b72`),
`artifact_4f17a04d79514ff3` (`xcede-description-unavailable.png`, SHA-256
`0107eb349382cd6ead95bf57a768d1d04ed80ba2af6026707d66b6728ebd7f84`),
`artifact_404738d8c8f04e05` (`newcode-description-unavailable.png`, SHA-256
`e580e7fe128c87735b13e30ef0c490fd8741070f692072c3f7e817c44c83bdbe`),
`artifact_411bc4509b344fbd` (`cube-ai-description-unavailable.png`, SHA-256
`4d68f1f2ff71d1ae12b9586fb0e7fd34d344697c145ad5aedb4213e74b709427`),
and `artifact_b5687dd2f6644494`
(`tensorops-description-unavailable.png`, SHA-256
`a3c7f63f80e1e4ff783458c7ff433ba41f10472faa63e5e6de5e89f64ebf4c13`).
The exact artifact record should remain the source of truth if a future report
needs the full hash for an item whose abbreviated diagnostic output was
truncated.

The Decskill and Provectus regression retests also confirmed that exact button
resolution and bounded click classification work, while LinkedIn still leaves
the application surface absent. The Provectus diagnostic artifact is
`artifact_b8207f6ff7ae4730` at
`provectus-easy-apply-retest-no-surface.png`, SHA-256
`18b08202e0a1063a9861b1348b3c80d32ee4c9bbf8e850a3fbfe66c05117361e`.
Newcode.ai added a distinct virtualized-list failure: the selected result
remained unchanged after a native click and a centered mouse fallback, so the
workflow stopped without attempting the wrong job.

The following live retests were made after the candidate clarified that
`yuh.lopes@gmail.com` is the valid LinkedIn account and Easy Apply email when it
is the only value offered, while `yuriabreu.jl@gmail.com` remains the
professional contact email:

- Redcare Pharmacy, AI Solutions Engineer, no longer had an email-role blocker.
  The Easy Apply link navigated to a tracking URL, but no form appeared. A fresh
  visible-button resolution matched the job heading and fingerprint, and the
  native click plus the bounded mouse fallback did not expose a surface. No
  CAPTCHA, login, consent, or submit action was encountered. The diagnostic
  artifact is `artifact_43450d574a0e4275` at
  `redcare-easy-apply-retest-no-surface.png`, SHA-256
  `43864b485aa9e28821c54acd81692b7e3dd61cd917db87212f14958aa7d6116a`.
- NineTwoThree AI Studio, AI Automations Product Engineer, received the same
  retest. The previous email mismatch blocker is resolved, but the current
  LinkedIn session returned `NO_EFFECT` and a structured timeout with no form,
  dialog, security challenge, or submit control. The diagnostic artifact is
  `artifact_7c4c326208c94207` at
  `ninethree-easy-apply-retest-no-surface.png`, SHA-256
  `c08de89aa96c65d6692079003aa963475c44e3aa4b9885366c3b51087d2c0ac2`.
- HCLTech, Senior Python Developer, was a new direct search candidate. Its
  visible Easy Apply control navigated to a tracking URL and remained without
  an application surface after the bounded wait. No form mutation or submit
  was attempted.

These retests confirm that the email-role correction removes a false data
blocker, but it cannot repair a LinkedIn surface that the portal does not expose
to the session. The correct terminal state is `application_surface_not_opened`
with a retryable observation hint, not `candidate_data_mismatch` and not a
successful application. A future adapter should preserve the original job URL,
tracking URL, active surface state, selected-job identity, and effect evidence
in one compact diagnostic result.

The live search also reproduced a semantic snapshot issue for pipe-delimited
titles. On the Provectus listing, the visible heading contained the company and
role correctly, but the snapshot temporarily split `Python and GenAI` into the
company field and returned only `Senior Solutions Architect` as the role. Job
identity extraction should prefer the page heading and company context over a
generic separator split, and should return a confidence or warning when those
sources disagree.

## Live retest: Anson McCade LinkedIn Easy Apply

On 2026-08-13, the improved interaction path was used on Anson McCade's
`Principal AI Engineer` vacancy, LinkedIn job `4449802535`. The visible page
reported Easy Apply, and the description exposed a strong match for Python,
LLM systems, agentic AI, prompt architecture, evaluation, production AI,
cloud or CI/CD, and technical leadership.

The test exercised the v2 behavior end to end:

- The contact step preserved the authenticated LinkedIn account email
  `yuh.lopes@gmail.com` without treating it as a candidate-data mismatch. The
  professional email `yuriabreu.jl@gmail.com` remains the preferred value when
  a form permits an explicit choice.
- The forward action moved from contact information to resume selection. The
  initial semantic action resolver did not recognize the localized `Revisar`
  button as a forward action, but the response returned the exact visible
  candidate and no click was made against an ambiguous target. A fresh
  fingerprinted `element_find` followed by `element_click` with
  `expect_active_surface_change` resolved the localized control and verified
  the transition.
- The exact Kake-specific AI and LLM resume already saved in LinkedIn was
  selected. The optional `Siga a empresa Anson McCade` checkbox was explicitly
  left unchecked.
- The final Easy Apply step exposed `Enviar candidatura` as a visible,
  enabled primary action with no pending required fields, inline validation
  errors, security controls, or authorization-risk prompt.
- One submit click was sent. The initial client process hit a local Unicode
  output encoding error while printing the response, so the workflow correctly
  treated the transport result as potentially unknown and did not retry. A
  read-only snapshot then verified `submitted=true`, a closed form, and the
  visible confirmation text `Candidatura enviada`.
- A full-page confirmation artifact was recorded as
  `artifact_c52c0bf789a44964`, relative path
  `anson-mccade-principal-ai-engineer-confirmation.png`, SHA-256
  `08b4c25e27afb5ad3c846e4e7900a60370ce9b6ce97a1ce73bb7b43c726cb406`.

This test confirms that bounded resolution, localized control handling,
optional-control safety, one-click submission, and post-transport state
verification materially improve the workflow. It also exposes two follow-up
items: the LinkedIn forward-action classifier should include localized labels
such as `Revisar`, and the MCP client examples should force UTF-8 output or
return structured data without allowing terminal encoding to obscure a
successful tool call.

## Live retest: email correction and external micro1 handoff

The prior TensorOps `Principal AI/ML Architect` blocker was retested after the
email-role correction. The LinkedIn Easy Apply account email was no longer
treated as a mismatch, but the tracking navigation still ended with no dialog,
form, or submit surface after the bounded wait. No submit click was sent. The
diagnostic artifact is `artifact_0e3f72c49f414cf5`,
`tensorops-email-rule-retest-no-surface.png`, SHA-256
`bae6d8acb3c816527f0e0cf9a4621df1480822bb418768772f9a8007ccc85469`.

Quik Hire Staffing's `Python Backend Developer (Remote)` was then retested
through the observed micro1 destination. The external form exposed a complete
description, Python, PostgreSQL, AWS, and Django requirements, and a visible
statement that clicking `Next` confirms agreement with the micro1 Candidate
Terms and Candidate Privacy Policy. The session had explicit candidate
authorization for those terms.

The v2 form path produced the following evidence:

- First name, last name, professional email, Brazil phone, and LinkedIn URL
  were filled one at a time with native events and `submission_ready`
  verification. Each field survived the stabilization window.
- The Python resume was accepted by the native file input. The upload state
  was `accepted_with_verification_warning` because the portal did not render
  the filename, even though the input reported the file and its size.
- `form_preflight` reported no blockers and no attestation handoff, despite
  the visible implied terms sentence. The attestation detector must recognize
  consent language attached to a submit or advance button, not only a checkbox
  or a visible consent control.
- One exact native click on `Next` was sent after the explicit authorization.
  The URL and active surface did not change, and the MCP correctly stopped
  without a fallback click because the transport result was unknown.
- The form remains open in the visible `curriculum` browser profile for a
  manual candidate click. The diagnostic artifact is
  `artifact_5e4ac5352269425b`, `quik-hire-micro1-next-no-effect.png`, SHA-256
  `a4a8713b9cd96778e2ebab8d3bfa756af361e7bb650dd189b97a2bba75ead27a`.

This retest confirms that the improvements make field preparation and upload
state observable, but the external portal still needs a stronger click effect
adapter for its React or shadow-root `Next` control. The safe recovery is a
manual click followed by a fresh read-only review, not an automatic duplicate
click.

## Cross-cutting requirement: shadow DOM must be transparent to the agent

Shadow DOM support is a platform capability, not a workflow detail that the
calling agent should need to know. The MCP must present controls inside open
shadow roots through the same logical field, action, and evidence contracts as
light-DOM controls. A caller should be able to use the same `element_id`, label,
role, fingerprint, fill, click, choice, combobox, upload, preflight, review,
and submit operations without adding a shadow-specific flag or JavaScript
fallback.

The adapter must therefore:

- traverse open shadow roots during discovery and re-resolution;
- preserve `shadow_path` internally while exposing one stable logical identity
  for the visible control;
- associate shadow controls with their visible labels, fieldsets, errors,
  required state, and rendered component state;
- resolve the exact current node immediately before every mutation, including
  controls recreated by framework rendering or portal updates;
- observe click effects, value survival, blur, validity, popup closure, and
  upload rendering across the shadow boundary;
- merge light-DOM and shadow-DOM results without duplicate candidates or false
  ambiguity, while reporting partial discovery errors explicitly;
- return the same v2 semantic states for stale, hidden, blocked,
  inconclusive, verified, and unknown outcomes regardless of the underlying
  DOM surface.

Acceptance criterion: a fixture whose complete application form is hosted in
an open shadow root must be preparable, reviewed, and safely advanced through
the public workflow without `js_evaluate`, shadow-specific caller knowledge,
or manual element discovery. The evidence should identify the logical field
and active surface, with the implementation details such as `shadow_path`
available only as diagnostic metadata.

## Live retest: shadow-root questions and final review scope

After the candidate manually advanced the Micro1 form, the next page exposed
three numeric questions inside a React surface reported with
`open_shadow_root` diagnostics. Fresh selector resolution followed by one
field-at-a-time v2 filling verified all values and framework events:

- expected hourly rate: `50` USD;
- availability: `40` hours per week;
- start: `7` days.

The field interaction itself is an effective shadow-DOM test: the caller did
not need to inspect a shadow root or execute page JavaScript. The server merged
the controls into the public surface and verified DOM presence, framework
events, blur, validity, controlled-value survival, and submission readiness.

The final review exposed a separate workflow defect. `form_review(scope="auto")`
selected the visible `-` counter button as the primary action because the
submit button is outside the first form container. `form_review(scope="main")`
correctly selected the visible enabled `Submit` button and reported no
blockers, but `form_submit_after_review` compared that token against the
fingerprint generated for the `auto` form scope and returned
`REVIEW_TOKEN_INVALID`. The safe adapter must bind the review token to the
same normalized active-surface scope used during submission, or carry the
review scope in the token and use it consistently. It must never require a
direct low-level click as a workaround for this mismatch.

Required regression coverage:

- a form with counter buttons and a final submit outside the form element;
- equivalent fingerprints for `auto`, `form`, and `main` when they describe
  the same logical application surface;
- a review token that records its scope and is accepted only against the same
  scope and document generation;
- shadow-root controls that remain invisible to the caller's workflow schema;
- a final review that reports `Submit` as the primary action and permits the
  single authorized submit click without a token scope false positive.

## Live retest: manual final submission with tab closure

After the final Micro1 review, the candidate changed the expected hourly rate
from `50` to `35` USD and clicked the visible `Submit` button manually. The
candidate then closed the tab before a confirmation surface could be captured.
The application tracker therefore records the vacancy as `submitted`, not
`confirmed`, and records `35` USD as the submitted expectation. No automatic
retry was attempted.

The persistent browser profile was reattached after the MCP server restart,
but the original Micro1 tab was no longer present. Reopening the observed
external URL produced a fresh, unfilled application form with `Next`, not a
confirmation page. This is not evidence that the application failed, and it
is not evidence that it succeeded. The workflow must preserve this terminal
uncertainty and direct later verification toward a portal status or recruiter
confirmation rather than allowing a duplicate submission.

Required regression coverage:

- preserve a terminal `submitted` state when a candidate reports a final click
  but the tab closes before confirmation;
- distinguish a newly opened blank form from a positive confirmation page;
- record the final candidate-edited answer separately from earlier prepared
  values;
- prevent automatic resubmission when the original tab or transport is gone;
- expose a concise recovery instruction for checking a portal or recruiter
  confirmation later.

## Live retest: passive LinkedIn reCAPTCHA misclassified as a blocking challenge

On the AI/R LinkedIn Easy Apply form, the candidate reported that no CAPTCHA
challenge was visible. The form was prepared with the required identity fields
and the dedicated resume. A read-only `form_preflight` nevertheless returned
`status=blocked` with a `security_control` blocker and
`requires_user_action=true` because it found an invisible reCAPTCHA Enterprise
anchor in the page. The primary `Enviar candidatura` button was visible and
enabled, and there was no visible challenge to solve.

The candidate clicked the button manually. The subsequent LinkedIn snapshot
reported `form_present=false`, `dialog_present=false`, `submitted=true`, and
the visible confirmation text `Candidatura enviada`. The independent
`submission_wait_for_confirmation` operation classified the result as
`outcome=confirmed` and captured the confirmation artifact
`artifact_209dab45e118497b` with SHA-256
`111824e8ba22d3335af1d5dad18d5d30e28207dd1529b3d0feb25e7b9c0d30e2`.

This is a false-positive security handoff, not evidence that a CAPTCHA was
bypassed. The server must distinguish a passive invisible security resource
from an active candidate challenge:

- Keep the reCAPTCHA source, frame provenance, and confidence as diagnostic
  metadata, but use `requires_user_action` only when a visible challenge,
  explicit portal handoff, or an equivalent active control is observed.
- Classify passive signals as `security_signal=passive` or a warning rather
  than a submission blocker when the active form is complete, the primary
  action is visible and enabled, and no challenge surface is rendered.
- Permit one explicitly authorized submit click in this passive state. If the
  portal renders a challenge after that click, classify the resulting state as
  `security_challenge`, stop, and never retry automatically.
- Deduplicate repeated reCAPTCHA nodes and ignore page-level LinkedIn
  navigation text that is unrelated to the active application surface.
- Add a regression fixture and an adapter test covering an invisible
  reCAPTCHA marker with no visible challenge, plus a companion fixture where a
  visible challenge must still produce a hard handoff.

The existing safety boundary remains unchanged: the MCP must never solve,
hide, bypass, or simulate a CAPTCHA. The correction is limited to avoiding a
false blocker when the portal exposes only a passive marker and the candidate
can proceed through the ordinary authorized submit flow.

## Live retest: confirmation precedence after a passive security signal

The Jobgether Senior AI Engineer Easy Apply flow repeated the same passive
LinkedIn reCAPTCHA marker. The form was prepared through the public Pydoll
operations, the dedicated resume was selected, and the final review exposed no
missing required fields, attestation, authorization-risk prompt, or visible
challenge. The submit button was visible and enabled.

One authorized native click changed the URL and closed the dialog. The
specialized LinkedIn snapshot then reported `submitted=true`,
`form_present=false`, `dialog_present=false`, and the visible confirmation text
`Candidatura enviada`. The confirmation screenshot was recorded as
`artifact_5a1fb80e81de4c83` with SHA-256
`b5349ed46bf6f318c3e72e4b7013a83edfb48652a52482509d9b0965947cc63c`.

The generic `submission_wait_for_confirmation` operation instead returned
`outcome=security_challenge` because it combined page-level LinkedIn security
signals with the positive confirmation text. This is a second false positive,
distinct from the preflight false positive. It shows that outcome precedence
must be applied to the active submission surface, not to arbitrary text or
navigation controls elsewhere in the page:

- A high-confidence visible confirmation such as `Candidatura enviada`,
  together with `submitted=true` and a closed Easy Apply dialog, must outrank
  passive reCAPTCHA markers and unrelated page-chrome security descriptors.
- `security_challenge` should require an active, relevant challenge surface or
  explicit portal text requesting candidate verification. A source URL or an
  invisible anchor alone is insufficient.
- Keep all corroborating signals in diagnostic evidence, but expose the
  decisive evidence and precedence rule in the public outcome.
- Add a regression fixture that contains an invisible reCAPTCHA anchor,
  generic LinkedIn navigation text, and a visible success confirmation. It
  must return `confirmed`. A companion fixture with an active challenge and no
  positive confirmation must return `security_challenge`.
- Ensure the tracker and artifact records can preserve the raw classifier
  warning without downgrading a visually confirmed submission.

## Live retest: Blue Wolf workflow after the passive-security correction

The Blue Wolf Digital Senior Forward Deployed Engineer Easy Apply flow was
executed as a second Europe-only live retest after the Jobgether submission.
The caller used the visible browser profile and the public Pydoll tools for
the full flow:

- contact information advanced successfully through the LinkedIn dialog;
- the dedicated two-page resume was uploaded and visibly selected;
- the required sponsorship answer was set to `Yes`, matching the candidate's
  Brazil-based status and need for German employment sponsorship;
- English `Professional` and German `None` were preserved;
- the optional `Siga a empresa Blue Wolf Digital` marketing checkbox was
  detected as preselected and explicitly unchecked;
- the active surface exposed no visible CAPTCHA, attestation, or candidate
  verification prompt;
- one native final click produced `surface=confirmation`,
  `submitted=true`, and visible `Candidatura enviada`.

The application was recorded as confirmed with pre-submission and
submission-confirmation artifacts. This confirms that the v2 element state,
choice verification, upload verification, active-surface re-resolution, and
single-click safety path are usable in a real LinkedIn form without caller
knowledge of shadow DOM.

The retest also exposed three remaining adapter issues:

- `linkedin_easy_apply_click_next` advanced through the first steps but did
  not identify the visible `Revisar` action on the Additional Questions step.
  `page_get_active_surface` did identify the exact enabled button with a fresh
  fingerprint, and `element_click` verified the progress and surface change.
  The specialized workflow should use the same semantic primary-action
  resolver and recognize `Revisar` as an intermediate action.
- The generic review still returned a hard blocker for the invisible
  reCAPTCHA marker. It must instead return a passive diagnostic signal when
  there is no visible challenge on the active surface, while preserving a hard
  handoff for a challenge rendered after the click.
- The click diagnostic reported several high-confidence `two_factor` signals
  sourced from LinkedIn's global navigation and notification labels after the
  successful click. Page-chrome text must not create a security handoff when
  the active application surface has already produced a positive confirmation.

The screenshot operation also rejected a relative artifact name without an
extension and built an invalid path ending in `extension is not supported`.
The public contract should either normalize a missing extension from `fmt` or
return a structured validation error before touching the browser. Regression
coverage should include a full-page review screenshot with and without an
explicit extension.

## Live retest: re-opening a previously blocked Easy Apply surface

The Omnis Partners Artificial Intelligence Engineer vacancy had previously
been recorded as blocked because the Easy Apply control produced no observable
surface. A fresh navigation to the same LinkedIn job later exposed the full
description and the Easy Apply dialog. The current server successfully opened
the dialog, uploaded the dedicated resume, and advanced through the form.

The form contained an important semantic mismatch: although the role was
advertised for Germany, one required question asked whether the candidate was
legally authorized to work in the United Kingdom. The workflow must preserve
the exact country in the question rather than infer it from the job location.
The truthful answers were authorization `No` and future sponsorship `Yes`.

The review also showed the optional `Siga a empresa Omnis Partners` checkbox
preselected by LinkedIn. The agent explicitly cleared it and verified the
unchecked state. Optional follow-company, alert, marketing, newsletter and
demographic controls should be classified separately from required application
fields and should never be carried into a submission by default.

After one revalidated native click, the specialized snapshot returned
`surface=confirmation`, `submitted=true` and `Candidatura enviada`. This
retest confirms that a prior transport or surface failure should not permanently
poison a vacancy record. The server should allow a new evaluation generation
when the page exposes a materially different surface, while preserving the
previous diagnostic event and preventing duplicate clicks within the same
generation.

## Out of scope

- Bypassing CAPTCHA, two-factor authentication, login controls, rate limits, or portal terms.
- Guessing candidate facts, addresses, work authorization, salary, or sensitive information.
- Automatically opting into marketing, newsletters, or optional consent.
- Sending applications or messages without the caller's session-level authorization.
- Changing the repository's safety, ownership, path, or client-isolation boundaries.
