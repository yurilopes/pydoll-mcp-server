# Changelog

## 0.4.0b1 (Unreleased)

### Added
- Added `page_get_active_surface` for modal/dialog/form/viewport observation with fields, controls, progress, errors, and evidence
- Added `element_find_by_text_candidates` for ranked text matching with ambiguity detection and filterable candidates
- Added `element_resolve_again` for safe re-resolution of stale cached element handles
- Added `form_fill_fields` for intent-driven form filling by label, placeholder, selector, role, and name
- Added `page_click_primary_action` for primary button detection with step progression tracking
- Added `artifact_prepare_upload` for agent-friendly upload file preparation with allowlist security
- Added `submission_wait_for_confirmation` for polling-based confirmation with structured status
- Added `AMBIGUOUS_ELEMENT` error code for cases where multiple candidates are too close to act safely

### Changed
- Changed `page_screenshot` and `element_screenshot` to save artifact files by default (`return_base64=false`)
- Changed `element_click_by_text` to accept filter parameters and ambiguity threshold
- Changed `element_click` to accept effect observation parameters
- Changed `server_status.capabilities` to include active surfaces, form flow, upload preparation, effect-aware clicks, and confirmation waits

## 0.3.0a1 (Unreleased)

### Added
- Added `page_get_interactive_summary` for visible controls with labels, section context, bounds, selector hints, and cached element IDs
- Added semantic click and mouse tools: `element_click_by_text`, `element_click_center`, and `mouse_click`
- Added framework-safe form tools: `element_fill_and_verify`, `element_wait_value`, `form_snapshot`, and `form_errors`
- Added combobox helpers for autocomplete controls: `combobox_get_options`, `combobox_type_and_select`, and `combobox_select_option`
- Added condition waits for text, text disappearance, selectors, and network idle
- Added artifact helpers and upload inspection: `artifact_get_paths`, `artifact_import`, and `file_upload_state`
- Added `docs/agent-recipes.md` with practical agent workflows for modern frontend pages

### Changed
- Established strict agent engineering rules and portable development guidance
- Made mypy strict, Pyright strict, Ruff formatting, and a 450-line hard limit required gates
- Removed silent Pydoll compatibility fallbacks and made malformed script responses fail explicitly
- Changed `page_get_tree` to hide head metadata and invisible nodes by default, with explicit opt-in flags
- Changed `element_fill` to use native property setters and framework-compatible events with verification by default
- Changed `js_evaluate_readonly` and `js_evaluate` to return structured JSON values directly instead of JSON serialized inside strings
- Renamed internal Pydoll runtime handles to make their boundary role explicit
- Added validated recursive JSON boundaries and explicit MCP input schemas
- Made mypy strict and Pyright strict pass across both production code and tests
- Added the `py.typed` marker and validated it in the built wheel
- Isolated pytest runtime artifacts inside `.tmp/` for portable sandboxed execution
- Normalized the repository with the enforced Ruff format
- Changed browser smoke fixtures to use loopback HTTP instead of local file navigation
- Centralized package version metadata so source, health endpoints, MCP tools, and wheels agree
- Restricted broad exception catches to registered MCP tool boundaries with an AST architecture gate
- Added a real MCP stdio end-to-end browser workflow covering element IDs, UTF-8, deep traversal, network, and cleanup
- Made delayed Windows temporary-profile cleanup explicit without retaining browser ownership

### Migration
- Internal integrations using `_pydoll_browser`, `_pydoll_tab`, or `_pydoll_element`
  must use `pydoll_browser`, `pydoll_tab`, or `pydoll_element`.

## 0.2.0a1 (2026-06-14)

### Added
- Agent-friendly semantic finders and advanced element interactions
- Compact snapshots, diffs, accessibility-like trees, and frame snapshots
- Cancelable waits for URL, functions, element state, and network activity
- Runtime console inspection, network summaries, and buffer cleanup
- Two-phase popup and download workflows, safe PDF generation, and explicit tab recreation
- Secure HTTP, HTTPS, SOCKS4, and SOCKS5 proxy configuration during browser launch
- `proxy_validate` and `proxy_get` tools with credential-safe metadata

### Changed
- Refactored Python modules to a flexible 400-line target with a 420-line hard gate
- Made public documentation and project configuration portable across machines
- Updated the declarative MCP tool catalog and capabilities for the v0.2 alpha
- Blocked `file://` navigation completely to prevent indirect local filesystem reads

## 0.1.0a1 (2026-06-12)

### Added
- MCP server over HTTP local with bearer token auth
- Streamable HTTP at `/mcp` and SSE at `/sse`
- Optional `stdio` transport via `--transport stdio`
- 32+ tools: browser lifecycle, navigation, page observation, element interaction, deep traversal, JS execution, cookies/storage, upload/download
- `page_get_tree` for compact DOM observation with actionable `element_id`
- `page_get_tree_deep` for iframe and shadow DOM traversal
- `element_find_deep` for cross-frame/cross-shadow element search
- Network inspection: `network_enable`, `network_disable`, `network_list`, `network_get_response`
- Console inspection: `console_enable`, `console_disable`, `console_list` (returns UNSUPPORTED pending Pydoll runtime validation)
- `diagnostics_snapshot` for server/browser/tab health diagnostics
- Trace tools: `trace_start`, `trace_stop`, `trace_get`, `trace_cleanup`
- `browser_attach` with strict ownership validation (returns UNSUPPORTED for cross-session attach)
- `schema_version` and `capabilities` in `server_status`
- Multi-client isolation by `client_id`
- Resource-level concurrency locks for tab and browser mutations
- Path allowlist for upload/download/screenshot artifacts
- Sensitive data redaction in cookies, storage, logs, and network inspection
- Browser smoke tests with headless Chrome
- HTML fixtures for unit and integration testing

### Changed
- N/A (first release)

### Security
- Bearer token required by default for HTTP transport
- `js_evaluate` tools scan for dangerous patterns (document.cookie, localStorage, form submission)
- Cookies and storage values are redacted by default
- Screenshot and upload paths validated against allowed directories
- Path traversal blocked in artifact paths
- `execute_cdp_cmd` not exposed
- No OS command tools
- No arbitrary filesystem access

### Known Limitations
- Console inspection returns `UNSUPPORTED` (requires additional Pydoll runtime event validation)
- `browser_attach` only works within the same server session
- Back/forward navigation uses JS `history.back()` / `history.forward()` (no native CDP support)
- Viewport set uses JS `window.resizeTo()` (no `Emulation.setDeviceMetricsOverride`)
- OOPIF support depends on Pydoll session routing
- Closed shadow root traversal may vary by Chromium version
