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

## Out of scope

- Bypassing CAPTCHA, two-factor authentication, login controls, rate limits, or portal terms.
- Guessing candidate facts, addresses, work authorization, salary, or sensitive information.
- Automatically opting into marketing, newsletters, or optional consent.
- Sending applications or messages without the caller's session-level authorization.
- Changing the repository's safety, ownership, path, or client-isolation boundaries.
