# Release Checklist

## 0.4.0b1 - Beta

### Pre-release checks
- [x] `pytest -q --basetemp=.tmp/pytest-release`: 238 passed (unit + contract + p2 + import + smoke integration)
- [x] `pytest -m browser_smoke -q --basetemp=.tmp/pytest-smoke`: 13 passed (inclui PLAN_14 multi-step flow smoke)
- [x] `pytest -m mcp_e2e -q --basetemp=.tmp/pytest-e2e`: real stdio browser workflow passed
- [x] `ruff check .`: All checks passed
- [x] `ruff format --check .`: 109 files formatted
- [x] `mypy --strict src tests`: Success
- [x] `pyright --pythonpath python`: 0 errors
- [x] `python -m build`: sdist and wheel built successfully
- [x] No Python file exceeds the 450-line maximum (semantic_actions.py at ~370 lines, justified in progress)
- [x] `LICENSE` exists (MIT)
- [x] `CHANGELOG.md` updated for 0.4.0b1
- [x] `docs/security.md` updated with PLAN_14 security model
- [x] `docs/agent-recipes.md` updated with multi-step form flow recipe
- [x] `docs/pydoll-capabilities.md` updated with PLAN_14 capabilities

Note: the default configured basetemp `.tmp/pytest` is currently blocked by
Windows `WinError 5` in this workspace. The same suites pass with isolated
basetemp directories. The PLAN_14 smoke test on Windows may also hit profile
cleanup permission errors; the test logic itself passes when cleanup does not
race with Chrome.

### Transport validation
- [x] HTTP local on `127.0.0.1` works
- [x] Bearer token required by default
- [x] `/health` responds without token
- [x] `/mcp` requires token
- [x] `/sse` endpoint exists
- [x] `stdio` transport available via `--transport stdio` (no token required)
- [x] MCP SDK stdio handshake and real tool listing passed (118 tools registered)

### Version consistency
- [x] Hatchling derives package metadata from `src/pydoll_mcp_server/version.py`
- [x] `health_check["version"]`: `0.4.0b1`
- [x] `server_status["version"]`: `0.4.0b1`
- [x] `/health` response: `version: 0.4.0b1`
- [x] Installed wheel metadata: `0.4.0b1`, matching the source version
- [x] `py.typed` present in installed package

### Tool coverage (beta)
- [x] Lifecycle: launch, list, close, attach (returns UNSUPPORTED)
- [x] Tabs: list, activate, close, recover, new, duplicate, health_check, recreate
- [x] Navigation: goto, reload, back, forward, wait
- [x] Observation: get_text, get_tree, get_tree_deep, get_interactive_summary, get_active_surface, screenshot (artifact-first), snapshot, diff
- [x] Active surfaces: page_get_active_surface (modal, dialog, form, main, viewport, active_element_context scopes)
- [x] Elements: find, find_deep, click (with effect observation), click_by_text (with ambiguity filtering), click_center, mouse_click, type, fill, fill_and_verify, get_text, get_attribute, screenshot (artifact-first), resolve_again, find_by_role/text/label/placeholder/test_id
- [x] Text ranking: element_find_by_text_candidates with filters and ambiguity detection
- [x] Forms: form_fill_fields (intent-driven), form_snapshot, form_errors, combobox_get_options, combobox_type_and_select, combobox_select_option
- [x] Primary action: page_click_primary_action with step progression
- [x] Upload: upload_files (with filename visibility), artifact_prepare_upload, artifact_import, artifact_get_paths, file_upload_state
- [x] Submission: submission_wait_for_confirmation (confirmed/submitted_uncertain/blocked/failed)
- [x] JS: evaluate_readonly, evaluate (experimental)
- [x] Config: user_agent_set/get, viewport_set/get
- [x] Storage: cookies_get/set, storage_get/set
- [x] Files: download_expect/prepare/wait/list/get_info
- [x] Network: enable, disable, list, get_response (with redaction), summary, clear
- [x] Console: enable, disable, list
- [x] Diagnostics: health_check, server_status, diagnostics_snapshot
- [x] Trace: start, stop, get, cleanup

### Security validation
- [x] No `execute_cdp_cmd` tool exposed
- [x] No OS command tool exposed
- [x] Path allowlist blocks traversal
- [x] Sensitive data redaction in cookies/storage/network
- [x] JS scanner blocks dangerous patterns
- [x] Bearer token never logged
- [x] Screenshots default to artifact files (base64 opt-in only)
- [x] `artifact_prepare_upload` rejects sources outside allowlist
- [x] Upload paths validated against runtime directories and explicit allowlists

### Structured errors (verified)
- [x] `AMBIGUOUS_ELEMENT`
- [x] `STALE_ELEMENT`
- [x] `PERMISSION_DENIED`
- [x] `TIMEOUT`
- [x] `INVALID_INPUT`
- [x] `EXECUTION_ERROR`

### Package install smoke
- [x] Wheel installs without editable mode in clean temp environment
- [x] `import pydoll_mcp_server` succeeds
- [x] Installed version is `0.4.0b1`
- [x] `py.typed` is present in the installed package
- [x] CLI help or non-browser startup check works

### Pending for release
- [ ] Human review
- [ ] GitHub tag
- [ ] GitHub release
- [ ] PyPI publication (manual only)

## 0.3.0a1 - Experimental Alpha

### Pre-release checks
- [x] `pytest -q --basetemp=.tmp\pytest-plan13-full`: 221 passed
- [x] `ruff check .`: All checks passed
- [x] `ruff format --check .`: All files formatted
- [x] `mypy --strict src tests`: Success
- [x] `pyright` strict on `src` and `tests`: 0 errors
- [x] `pytest -m browser_smoke -q`: 12 passed
- [x] `pytest -m mcp_e2e -q --basetemp=.tmp\pytest-plan13-e2e`: real stdio browser workflow passed
- [x] `sdist` and `wheel` built successfully
- [x] Wheel installed in temporary venv, version verified, and `py.typed` confirmed
- [x] No Python file exceeds the 400-line target
- [x] `LICENSE` exists (MIT)
- [x] `CHANGELOG.md` exists
- [x] `docs/security.md` exists
- [x] README updated for P2 state

Note: the default configured basetemp `.tmp/pytest` is currently blocked by
Windows `WinError 5` in this workspace. The same suites pass with isolated
basetemp directories.

### Transport validation
- [x] HTTP local on 127.0.0.1 works
- [x] Bearer token required by default
- [x] `/health` responds without token
- [x] `/mcp` requires token
- [x] `/sse` endpoint exists
- [x] `stdio` transport available via `--transport stdio` (no token required)
- [x] MCP SDK stdio handshake and real tool listing pass with 111 tools
- [x] MCP SDK stdio real browser workflow passes

### Version consistency
- [x] Hatchling derives package metadata from `src/pydoll_mcp_server/version.py`
- [x] `health_check["version"]`: `0.3.0a1`
- [x] `server_status["version"]`: `0.3.0a1`
- [x] `/health` response: `version: 0.3.0a1`
- [x] Installed wheel metadata: `0.3.0a1`, matching the source version

### Tool coverage
- [x] Lifecycle: launch, list, close
- [x] Tabs: list, activate, close, recover
- [x] Navigation: goto, reload, back, forward, wait
- [x] Observation: get_tree, get_text, screenshot
- [x] Deep: get_tree_deep, element_find_deep
- [x] Elements: find, click, type, fill, get_text, get_attribute, screenshot
- [x] JS: evaluate_readonly, evaluate
- [x] Config: user_agent_set, viewport_set
- [x] Storage: cookies_get/set, storage_get/set
- [x] Files: download_expect, upload_files
- [x] Network: enable, disable, list, get_response (with redaction)
- [x] Console: enable, disable, list using bounded Runtime events
- [x] Diagnostics: snapshot (with trace integration)
- [x] Trace: start, stop, get, cleanup (real events, not stubs)
- [x] Attach: browser_attach (returns UNSUPPORTED, ownership validated)

### P2-specific tests
- [x] 34 tests in `tests/p2/`
- [x] stdio dispatch tested behaviorally
- [x] network list filter and redaction tested
- [x] trace start/stop/get/cleanup tested
- [x] trace integration with diagnostics_snapshot and network_* tested
- [x] capabilities and schema_version tested
- [x] console behavior and unavailable-runtime fallback tested
- [x] browser_attach ownership and no-arbitrary-input tested

### Security validation
- [x] No `execute_cdp_cmd` tool exposed
- [x] No OS command tool exposed
- [x] Path allowlist blocks traversal
- [x] Sensitive data redaction in cookies/storage/network
- [x] JS scanner blocks dangerous patterns
- [x] Bearer token never logged

### Client docs
- [x] `docs/clients/opencode.md`
- [x] `docs/clients/codex.md`
- [x] `docs/clients/claude-code.md`

### Pending for release
- [ ] Human review
- [ ] GitHub tag
- [ ] PyPI publication (manual only)
