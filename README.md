# Pydoll MCP Server

MCP server for browser automation built on the [Pydoll](https://github.com/autoscrape-labs/pydoll) library.

This project offers a local alternative to the Playwright MCP Server, with its own agent-oriented API built on Pydoll. It does not copy the Playwright API. It provides a predictable layer for agents: observe pages, choose elements, act by `element_id`, navigate, capture screenshots, execute JavaScript with limits, handle iframes and shadow DOM, inspect complete HTTP requests, and call authenticated HTTP endpoints directly from the browser session.

## Status

Beta preview (v0.4.0b1). HTTP on `127.0.0.1` is the primary transport. `stdio` transport is available as an option (`--transport stdio`).

Endpoints:
- `/health` - Health check (no auth)
- `/mcp` - Streamable HTTP MCP (bearer token required)
- `/sse` - Server-Sent Events (bearer token required)

## Requirements

- Python `>=3.10`
- Chrome or Chromium installed
- Pydoll `>=2.23.0`

Contributors must follow the quality gates and engineering conventions in
[`docs/development.md`](docs/development.md).

## Installation

```powershell
python -m pip install -e ".[dev]"
```

For release distribution:

```bash
pip install pydoll-mcp-server
```

## Running

Set a token before starting:

```powershell
# Windows (PowerShell)
$env:PYDOLL_MCP_AUTH_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```bash
# Linux / macOS
export PYDOLL_MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

These commands use Python instead of shell or .NET cryptography APIs, so token
generation behaves consistently across Windows PowerShell 5.1, PowerShell 7,
Linux, and macOS. Keep the generated value available when configuring MCP client
headers. Generate a new token whenever the server is restarted with a new client
configuration.

Start the server (HTTP, the default):

```powershell
python -m pydoll_mcp_server.cli --host 127.0.0.1 --port 8765
```

Or via stdio:

```powershell
python -m pydoll_mcp_server.cli --transport stdio
```

Endpoints:

- `GET http://127.0.0.1:8765/health` - public health check, no token
- `POST http://127.0.0.1:8765/mcp/` - Streamable HTTP MCP, with bearer token
- `GET http://127.0.0.1:8765/sse/` - SSE MCP, with bearer token

MCP clients must send:

```text
Authorization: Bearer <PYDOLL_MCP_AUTH_TOKEN>
```

`PYDOLL_MCP_ALLOW_NO_AUTH=true` should only be used in isolated development.

## MCP Tools

Health and diagnostics:

- `health_check`
- `server_status`
- `diagnostics_snapshot`
- `trace_start`, `trace_stop`, `trace_get`, `trace_cleanup`

Lifecycle:

- `browser_launch` (supports `session_intent="user_authenticated"` + `site_hint`)
- `browser_list`
- `browser_close`
- `browser_attach`
- `tab_list`
- `tab_activate`
- `tab_close`
- `tab_recover`
- `tab_new`, `tab_duplicate`, `tab_health_check`, `tab_recreate`
- `dialog_list`, `dialog_handle`, `popup_prepare`, `popup_wait`
- `proxy_validate`, `proxy_get`

`browser_launch` accepts an optional `proxy_server` using `http`, `https`,
`socks4`, or `socks5`, plus an optional `proxy_bypass_list`. Proxy credentials
may be embedded for Pydoll authentication, but MCP responses and browser
listings expose only sanitized metadata without usernames or passwords. Proxy
configuration is immutable after browser launch.

Navigation:

- `page_goto`
- `page_reload`
- `page_back`
- `page_forward`
- `page_wait`
- `page_wait_for_url`, `page_wait_for_function`
- `page_wait_for_text`, `page_wait_text_gone`, `page_wait_for_selector`, `page_wait_for_network_idle`
- `page_scroll`, `page_scroll_to`

Observation:

- `page_get_text`
- `page_get_tree`
- `page_get_tree_deep`
- `page_get_interactive_summary`
- `page_get_active_surface`
- `page_screenshot`
- `page_snapshot`, `page_diff`
- `page_get_accessibility_tree`, `frame_list`, `frame_snapshot`
- `page_print_pdf`

Elements:

- `element_find`
- `element_find_deep`
- `element_click`
- `element_click_by_text`, `element_click_center`, `mouse_click`
- `element_find_by_text_candidates`
- `element_resolve_again`
- `element_type`
- `element_fill`
- `element_fill_and_verify`, `element_wait_value`
- `element_get_text`
- `element_get_attribute`
- `element_screenshot`
- `element_get_state`, `element_wait_for_state`
- `element_select_option`, `element_check`, `element_uncheck`
- `element_hover`, `element_scroll_into_view`, `keyboard_press`
- semantic finders by role, text, label, placeholder, and test ID
- `form_snapshot`, `form_errors`
- `combobox_get_options`, `select_get_options`, `combobox_type_and_select`, `combobox_select_option`

JavaScript and advanced helpers:

- `js_evaluate_readonly`
- `js_evaluate`
- `user_agent_set`
- `user_agent_get`
- `viewport_set`
- `viewport_get`
- `cookies_get`
- `cookies_set`
- `storage_get`
- `storage_set`
- `download_expect`
- `download_prepare`, `download_wait`, `download_list`, `download_get_info`
- `upload_files`
- `file_upload_state`, `artifact_get_paths`, `artifact_import`, `artifact_prepare_upload`
- `profile_list`, `profile_promote`
- `operation_cancel`
- `http_request`

Network inspection:

- `network_enable`
- `network_disable`
- `network_list`
- `network_get_request`
- `network_replay_request`
- `network_get_response`
- `network_summary`, `network_clear`
- `network_wait_for_request`, `network_wait_for_response`
- `websocket_list`
- `websocket_get`
- `websocket_frames_list`

`network_list` is a compact, sanitized index. `network_get_request` returns the raw
request details captured by Chromium, including request headers and payload, without
redaction. `network_get_response` retrieves the response body separately.
`websocket_list`, `websocket_get`, and `websocket_frames_list` expose Chromium
`Network.webSocket*` events as first-class captures, including handshakes, sent frames,
received frames, frame errors, close events, payload truncation metadata, and optional
raw output. Raw request and WebSocket data can contain credentials and personal data.
Do not log it automatically, and call `network_clear` after analysis when retention is
unnecessary.

`http_request` performs a direct HTTP(S) request using the owning browser tab's current
cookies, user agent, and supported HTTP(S) proxy. It is not subject to page CORS.
Destinations are restricted to the tab hostname unless `allow_cross_origin=true`.
`network_replay_request` replays a captured request through the same service and requires
`confirm_side_effects=true` for POST, PUT, PATCH, and DELETE. Direct HTTP does not reproduce
Chromium TLS fingerprinting, cache, service workers, or client certificates.

### Authenticated direct HTTP

`http_request` is the equivalent of a browser-associated API request context. It sends
HTTP outside page JavaScript while sharing the owning tab's current cookies, user agent,
and supported HTTP(S) proxy. Cookies received through `Set-Cookie` are synchronized back
to the browser.

Example JSON request:

```json
{
  "client_id": "agent",
  "tab_id": "tab-123",
  "method": "POST",
  "url": "/api/profile",
  "headers": {
    "Accept": "application/json"
  },
  "json_value": {
    "name": "Example"
  },
  "timeout": 30,
  "max_response_bytes": 1048576
}
```

Supported payload modes are mutually exclusive:

- `json_value` for JSON;
- `form_fields` for ordered URL-encoded fields, including duplicate names;
- `body` for raw UTF-8 text;
- `body_base64` for raw binary data.

Relative URLs resolve against the current tab URL. Absolute URLs are restricted to the
same hostname unless `allow_cross_origin=true`. Every redirect is validated before it is
followed. Response bodies are returned as text when the content type is textual and as
base64 otherwise. Truncation, original size when known, and returned size are explicit.

### Capture and replay workflow

A deterministic agent workflow is:

1. Call `network_enable` and `network_clear`.
2. Start `network_wait_for_request` with URL and method filters.
3. Trigger the browser action that submits the request.
4. Call `network_get_request` with the captured request ID.
5. Call `network_get_response` to retrieve the browser response body.
6. Optionally call `network_replay_request` to resend the captured request.
7. Call `network_clear` when raw data is no longer needed.

Replay uses the current browser cookies and preserves the captured method, URL, headers,
and available payload. Headers controlled by the HTTP client, including `Host`, `Cookie`,
and `Content-Length`, are recalculated and listed in `omitted_headers`. Mutating methods
require explicit confirmation:

```json
{
  "client_id": "agent",
  "tab_id": "tab-123",
  "request_id": "request-456",
  "confirm_side_effects": true
}
```

Replay rejects incomplete multipart captures and ambiguous multiple binary entries instead
of reconstructing data that Chromium did not provide.

Console inspection:

- `console_enable`, `console_disable`, `console_list`

Agent-friendly model

`page_get_tree` returns a compact, limited tree by default. It prioritizes visible body content and hides `head`, `script`, `meta`, `style`, `link`, and invisible nodes unless `include_head=true` or `include_invisible=true` is set. Interactive nodes receive `element_id`, `selector_hint`, `xpath_hint`, `actionable`, and `resolution_confidence`. An agent can observe the tree and call `element_click` or `element_fill` directly with the `element_id`, without calling `element_find` first.

`page_get_interactive_summary` is the recommended first observation for modern frontend apps. It returns visible controls with roles, names, labels, nearby section context, bounding boxes, selector hints, enabled/editable state, and cached `element_id` values.

`page_get_active_surface` detects the current modal, dialog, form, or main content surface. It returns fields, compact actionable controls, structural containers, primary and secondary actions, progress indicators, visible validation errors, pending required fields, and structured evidence. Scope `auto` prefers visible modals and dialogs over page content. Large select option lists are summarized with counts; use `select_get_options` or `combobox_get_options` when an agent needs the option list.

Radio and checkbox questions are represented as `radio_group` or `checkbox_group` fields. Each option includes its own `element_id`, label, checked state, and disabled state. A required group appears once in `pending_required` while no option is selected. Dismissal actions such as Close and Cancel are never selected as `primary_action`.

Use `form_select_choice(field_label, option_label)` for radio and checkbox questions. It restricts matching to the identified question, uses associated labels when needed, and returns success only after verifying the selected state.

For multi-step form flows, use `form_fill_fields` to fill fields by intent (label, placeholder, selector matching) and `page_click_primary_action` to advance steps. `element_find_by_text_candidates` resolves duplicate visible text before clicking. `element_resolve_again` recovers stale element handles after page re-renders. `submission_wait_for_confirmation` polls for post-submit outcomes.

For React-like forms and custom controls, prefer `element_fill`, `element_fill_and_verify`, `combobox_type_and_select`, `element_click_by_text`, and condition waits before using custom JavaScript. `js_evaluate` and `js_evaluate_readonly` return structured JSON values directly in `value`; clients should not parse `value` as a JSON string.

`page_get_tree_deep` is the recommended option when the page uses iframes or shadow DOM. It is more expensive, has its own timeout, and returns:

- `frame_path`
- `shadow_path`
- `partial`
- `errors`
- visibility and interaction metadata when available

The alpha covers simple iframes, same-origin nested iframes, and open shadow DOM. Closed shadow roots and complex cross-origin cases still require additional validation.

## Security

- Bearer token is required by default.
- The default bind must remain `127.0.0.1`.
- Free `execute_cdp_cmd` is not exposed.
- Operating system commands are not exposed.
- Arbitrary filesystem read or write is not exposed.
- Navigation to `file://` is blocked completely. Serve local fixtures through loopback HTTP.
- Screenshots, downloads, and uploads use controlled directories or an allowlist.
- Cookies and storage are redacted by default on read.
- Sensitive attributes such as tokens, passwords, and cookies are redacted.
- Logs must redact bearer tokens, cookies, authorization headers, and sensitive fields.
- Proxy credentials are never returned, logged, traced, or persisted. The effective proxy
  URL is held only in internal in-memory browser state when needed for authenticated direct HTTP.
- Raw network inspection, direct HTTP, and replay responses can contain credentials and
  personal data. Consumers must not log these tool results automatically.
- Direct HTTP is same-host by default, blocks credentials embedded in URLs, validates every
  redirect, and requires explicit cross-origin opt-in.
- Replaying POST, PUT, PATCH, or DELETE requires `confirm_side_effects=true`.

`js_evaluate` is a sensitive tool:

- Requires explicit `tab_id`.
- Uses a short timeout by default.
- Limits code and result size.
- Logs a summarized audit with hash, duration, and size.
- Must not log full code or full results.
- Warns or blocks dangerous patterns, depending on mode.
- May be disabled in the future via a safe-mode configuration.

`js_evaluate_readonly` is preferred for inspection, but should also be treated as sensitive.

## Runtime directories

Runtime data is stored outside the repository by default:

- Windows: `%LOCALAPPDATA%\pydoll-mcp-server`
- macOS: `~/Library/Application Support/pydoll-mcp-server`
- Linux: `~/.local/share/pydoll-mcp-server`

Expected subdirectories:

- `profiles/` (contains `index.json` with safe profile metadata)
- `tmp/`
- `downloads/`
- `artifacts/`
- `logs/`

## Session continuity

Persistent browser profiles preserve cookies, localStorage, and login state
across launches. Use `session_intent="user_authenticated"` with `site_hint` in
`browser_launch` to pick up an existing profile matching a domain.
`profile_list` discovers available profiles and `profile_promote` promotes a
preserved temporary profile to persistent. Profiles are indexed safely in
`profiles/index.json` without exposing cookies, tokens, storage values, or
absolute paths.

## Vendored Pydoll documentation

Vendored Pydoll documentation is available at:

```text
references/pydoll-docs/
```

Do not mix vendored documentation with MCP server code.

## Testing

Core gates:

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy --strict src tests
python -m pyright
python -m pytest -m mcp_e2e -q
python -m pytest -m browser_smoke -q
python -m build
```

Useful test suites by area:

```powershell
python -m pytest tests/contract -q
python -m pytest tests/unit/test_concurrency.py -q
python -m pytest tests/unit/test_security.py tests/unit/test_files_security.py -q
python -m pytest tests/p2/ -q
```

`browser_smoke` opens Chrome/Chromium headless and validates real flows with local fixtures.

## Known limitations

- Console inspection depends on Chromium Runtime events and may return `UNSUPPORTED` when unavailable.
- `browser_attach` does not support reconnection across server sessions (returns `UNSUPPORTED`).
- JavaScript dialogs can block the originating browser command; handle them from an independent MCP request.
- Closed shadow roots and complex OOPIFs still require dedicated validation.
- Deep traversal is more expensive than `page_get_tree` and should be used explicitly.
- Downloads depend on Pydoll's `expect_download` flow and must remain in the controlled runtime dir.
- Uploads must only use paths allowed by the allowlist.
- `operation_cancel` applies to waits and direct HTTP operations that receive an explicit caller-provided `operation_id`.
- Direct HTTP supports HTTP and HTTPS proxies. SOCKS proxy sessions return `UNSUPPORTED`
  rather than bypassing the configured browser proxy.
- Direct HTTP shares cookies, user agent, and supported proxy settings, but not Chromium's
  TLS fingerprint, HTTP cache, service workers, CORS behavior, or client certificates.

## License

MIT
