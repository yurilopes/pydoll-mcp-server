# PLAN_14 Tests

## Test-First Rule

The developer must add tests and fixtures that reproduce PLAN_14 problems before
changing production behavior. Tests must validate observable MCP contracts, not
implementation details or source text.

Use small typed fakes for unit tests. Use real browser smoke tests for behavior
that depends on Pydoll, Chromium, file inputs, visible modals, re-rendered
buttons, screenshots, or MCP transport.

## Fixture

Add `tests/fixtures/pages/multi-step-application.html`.

The fixture must be generic and must not imitate any specific job platform. It
should model a modern multi-step form with these features:

- A page list with duplicate visible action text, for example one card action
  and one main action using the same text.
- A visible active modal or dialog opened by the main action.
- Multi-step states: contact, upload, questions, review, confirmation.
- Required fields with visible validation errors.
- Text input, email input, textarea, numeric input, select, radio group,
  checkbox, and file input.
- Dynamic field validation after blur or submit.
- A custom upload display that shows the filename while the native file input
  may clear its `files` state after the site records the upload.
- A primary action button that re-renders between observation and click while
  keeping similar text and semantics.
- A review step showing the submitted values as visible UI text.
- Final confirmation text and changed modal state after submission.
- At least one no-op button that can be clicked successfully but produces no
  requested effect, to test `effect_observed=false`.

Keep the fixture deterministic, local, and served through the existing loopback
fixture mechanism. Do not use network dependencies.

## Unit Tests

Add focused unit tests for pure ranking, validation, path, and response helpers.
Suggested files may include new tests under `tests/unit/`, but exact file names
are less important than cohesion.

Required unit coverage:

- Text candidate ranking prefers semantic controls over text spans and generic
  ancestors.
- Ranking filters work for role, tag, within element, nearest heading, section
  label, ARIA text, modal preference, main content preference, visible center,
  and largest preference.
- Ambiguity detection returns `AMBIGUOUS_ELEMENT` when top candidates are within
  the configured threshold.
- Evidence helper redacts sensitive fields and truncates text previews.
- Active surface selection chooses modal/dialog over main content in `auto`
  scope and respects explicit scopes.
- Form field matching maps labels, question text, placeholders, selectors,
  roles, and names without guessing.
- Form field matching returns ambiguous entries when multiple controls match.
- Stale re-resolution accepts only one safe candidate and refuses ambiguous
  candidates.
- `artifact_prepare_upload` rejects files outside runtime dirs and allowlists.
- `artifact_prepare_upload` copies allowlisted files into the client artifact
  directory and sanitizes filenames.
- Screenshot path generation stays within the artifact directory and chooses
  MIME type from the file extension.

## Integration Tests

Add browser-backed integration coverage for PLAN_14 tools.

Required scenarios:

- `page_get_active_surface` returns the active dialog with fields, controls,
  progress, errors, primary action, secondary actions, review text, and
  evidence.
- `page_get_active_surface` works for `modal`, `form`, `main`, `viewport`, and
  `active_element_context`.
- `element_find_by_text_candidates` returns ranked duplicate text candidates
  with reasons and element IDs.
- Enhanced `element_click_by_text` refuses ambiguous duplicate candidates and
  succeeds when scoped with filters.
- Enhanced `element_click` observes dialog open, expected text, selector
  appearance, URL change where applicable, network idle where enabled, and
  no-effect clicks.
- `element_resolve_again` recovers a re-rendered primary button when safe.
- `form_fill_fields` fills text, email, textarea, numeric, select, radio,
  checkbox, and combobox-style fields by intent mappings.
- `form_fill_fields` reports unfilled and ambiguous mappings without inventing
  values.
- `page_click_primary_action` advances steps and returns progress before and
  after, surfaced errors, pending required fields, and clicked button metadata.
- `artifact_prepare_upload` plus `upload_files` completes a PDF upload through
  the controlled artifact directory.
- `upload_files(expect_filename_visible=true)` reports visible filename even
  when native input state is empty after the page records the upload.
- `submission_wait_for_confirmation` returns `confirmed`,
  `submitted_uncertain`, `blocked`, and `failed` in separate deterministic
  fixture states.
- `page_screenshot` and `element_screenshot` save artifact files by default,
  return path metadata, and return base64 only with explicit opt-in.

## MCP End-To-End Smoke

Add a real MCP browser smoke test that uses the public tool surface only.

Required flow:

1. Launch browser with a temporary profile.
2. Navigate to `multi-step-application.html`.
3. Observe the page and open the generic form modal.
4. Call `page_get_active_surface`.
5. Fill contact fields through `form_fill_fields`.
6. Advance with `page_click_primary_action`.
7. Prepare a local PDF through `artifact_prepare_upload`.
8. Upload it with `upload_files(expect_filename_visible=true)`.
9. Fill question fields through `form_fill_fields`.
10. Advance to review and inspect review text through active surface output.
11. Submit only through `page_click_primary_action`.
12. Wait for confirmation through `submission_wait_for_confirmation`.
13. Close the browser.

The smoke test must not call `js_evaluate` or `js_evaluate_readonly` for normal
workflow steps. JavaScript may be used only inside the fixture itself.

## Contract Tests

Update MCP contract tests to include the new public tool names:

- `page_get_active_surface`
- `element_find_by_text_candidates`
- `element_resolve_again`
- `form_fill_fields`
- `page_click_primary_action`
- `submission_wait_for_confirmation`
- `artifact_prepare_upload`

Update prohibited tool checks as needed to keep `execute_cdp_cmd`, OS commands,
and arbitrary filesystem methods absent from the public catalog.

## Documentation Tests And Manual Checks

Documentation must explain the generic recipes without local paths in public
docs. Required documentation checks:

- README tool list includes the new tools.
- `docs/agent-recipes.md` includes a multi-step form recipe with upload and
  confirmation.
- `docs/security.md` explains upload preparation, screenshot artifact defaults,
  and evidence redaction.
- `docs/pydoll-capabilities.md` records Pydoll capabilities used for this plan.
- `CHANGELOG.md` summarizes the new alpha capabilities.
- Progress notes record gates and any fixture or browser limitations.

## Required Gates

Run the exact gate set required by `AGENTS.md` before concluding:

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

If the default pytest base temp directory is locked on Windows, rerun with a
safe isolated `--basetemp` and record both the failure and the successful rerun
in progress.

