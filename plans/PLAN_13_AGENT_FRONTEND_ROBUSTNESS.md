# PLAN_13: Agent frontend robustness

## Objective

Improve the MCP server for real modern frontend workflows so agents can observe,
select, act, wait, validate, and upload with fewer custom `js_evaluate` calls.
The implementation must preserve the current security model, typed boundaries,
async behavior, and client isolation.

## Confirmed baseline

- `page_get_tree` currently walks from `document.documentElement` and can include
  head metadata unless filtered by implementation.
- `element_click` uses Pydoll element click with a DOM click fallback.
- `element_fill` inserts text and falls back to a direct JS value set, but does
  not expose validation options.
- Semantic finders exist, but broad XPath text matching can select ambiguous
  ancestors.
- Pydoll exposes `WebElement.click(...)` and `tab.mouse.click(x, y)` for real
  browser input events.
- `js_evaluate` currently serializes every returned value into a JSON string.
- Uploads are already restricted to runtime directories plus explicit allowlists.

## Implementation plan

1. Observation
   - Update `page_get_tree` to default to body-first visible content.
   - Add `include_invisible=false` and `include_head=false`.
   - Add `page_get_interactive_summary` with visible controls, role, name, text,
     labels, nearest heading, section label, bounds, enabled, editable, checked,
     selected, `selector_hint`, `xpath_hint`, score, and `element_id`.
   - Reuse the same DOM summary logic in `page_get_accessibility_tree` where
     practical.

2. Semantic interaction
   - Add `element_click_by_text`.
   - Rank candidates by exact text, visible state, actionable tag or role,
     enabled state, smallest bounding area, and absence of conflicting option
     text.
   - Return the chosen candidate and rejected candidates with reasons.
   - Add `element_click_center` and `mouse_click` using Pydoll mouse input.
   - Do not expose arbitrary CDP commands or OS input APIs.

3. Framework-safe forms
   - Improve `element_fill` to use native property setters for input, textarea,
     select, and contenteditable, then dispatch `input`, `change`, and `blur`.
   - Keep values out of logs and responses except lengths and safe verification
     metadata.
   - Add `element_fill_and_verify`, `element_wait_value`, `form_snapshot`, and
     `form_errors`.
   - Add combobox helpers: `combobox_get_options`, `combobox_type_and_select`,
     and `combobox_select_option`.

4. Waits and artifacts
   - Add text, selector, and network-idle waits.
   - Extend URL wait with `match="contains"`.
   - Add `artifact_get_paths` and `artifact_import`.
   - `artifact_import` may read only from existing allowed runtime directories,
     `PYDOLL_MCP_UPLOAD_ALLOWLIST`, or `PYDOLL_MCP_IMPORT_ALLOWLIST`.
   - Add `file_upload_state` and return post-upload details from `upload_files`.

5. JavaScript return contract
   - Return JSON values directly from `js_evaluate_readonly` and `js_evaluate`.
   - Add `value_type`, `result_size_bytes`, `truncated`, `script_hash`, and
     diagnostic data for null, undefined, execution error, timeout, and
     truncation.
   - Update e2e and docs that currently parse `value` with `json.loads`.

## Acceptance tests

- `page_get_tree` excludes head and invisible nodes by default, and includes
  them only with flags.
- `page_get_interactive_summary` returns controls with context and element IDs.
- `element_click_by_text` selects the smallest visible candidate for `Freelance`
  in an ambiguous card fixture.
- `element_click_center` and `mouse_click` trigger browser input events.
- `element_fill` updates a controlled input and reports verification.
- `combobox_type_and_select` selects a portaled option.
- `form_snapshot` and `form_errors` associate errors with likely fields.
- `artifact_import` rejects paths outside allowlists and copies allowed files
  into the artifacts directory.
- `upload_files` returns accepted file metadata and `file_upload_state` reports
  the input and nearby UI state.
- `js_evaluate*` returns dicts, arrays, strings, numbers, booleans, and null as
  JSON values, not serialized JSON strings.

## Required documentation updates

- README tool list and agent-friendly model.
- `docs/agent-recipes.md` with practical examples.
- `CHANGELOG.md`.
- `docs/release-checklist.md` if final tool counts or gate results change.

## Required gates

Run the full gate set from `AGENTS.md` before concluding:

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

