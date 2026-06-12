# Changelog

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
