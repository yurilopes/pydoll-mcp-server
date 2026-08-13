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

## Out of scope

- Bypassing CAPTCHA, two-factor authentication, login controls, rate limits, or portal terms.
- Guessing candidate facts, addresses, work authorization, salary, or sensitive information.
- Automatically opting into marketing, newsletters, or optional consent.
- Sending applications or messages without the caller's session-level authorization.
- Changing the repository's safety, ownership, path, or client-isolation boundaries.
