# Pydoll MCP Server

MCP server for browser automation built on the [Pydoll](https://github.com/autoscrape-labs/pydoll) library.

This project offers a local alternative to the Playwright MCP Server, with its own agent-oriented API built on Pydoll. It does not copy the Playwright API. It provides a predictable layer for agents: observe pages, choose elements, act by `element_id`, navigate, capture screenshots, execute JavaScript with limits, and handle iframes and shadow DOM.

## Status

Experimental alpha (v0.2.0a1). HTTP on `127.0.0.1` is the primary transport. `stdio` transport is available as an option (`--transport stdio`).

Endpoints:
- `/health` - Health check (no auth)
- `/mcp` - Streamable HTTP MCP (bearer token required)
- `/sse` - Server-Sent Events (bearer token required)

## Requirements

- Python `>=3.10`
- Chrome or Chromium installed
- Pydoll `>=2.23.0`

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
$env:PYDOLL_MCP_AUTH_TOKEN = "your-secret-token"
```

```bash
# Linux / macOS
export PYDOLL_MCP_AUTH_TOKEN="your-secret-token"
```

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

- `browser_launch`
- `browser_list`
- `browser_close`
- `browser_attach`
- `tab_list`
- `tab_activate`
- `tab_close`
- `tab_recover`
- `tab_new`, `tab_duplicate`, `tab_health_check`, `tab_recreate`
- `dialog_list`, `dialog_handle`, `popup_prepare`, `popup_wait`

Navigation:

- `page_goto`
- `page_reload`
- `page_back`
- `page_forward`
- `page_wait`
- `page_wait_for_url`, `page_wait_for_function`
- `page_scroll`, `page_scroll_to`

Observation:

- `page_get_text`
- `page_get_tree`
- `page_get_tree_deep`
- `page_screenshot`
- `page_snapshot`, `page_diff`
- `page_get_accessibility_tree`, `frame_list`, `frame_snapshot`
- `page_print_pdf`

Elements:

- `element_find`
- `element_find_deep`
- `element_click`
- `element_type`
- `element_fill`
- `element_get_text`
- `element_get_attribute`
- `element_screenshot`
- `element_get_state`, `element_wait_for_state`
- `element_select_option`, `element_check`, `element_uncheck`
- `element_hover`, `element_scroll_into_view`, `keyboard_press`
- semantic finders by role, text, label, placeholder, and test ID

JavaScript and advanced helpers:

- `js_evaluate_readonly`
- `js_evaluate`
- `user_agent_set`
- `viewport_set`
- `cookies_get`
- `cookies_set`
- `storage_get`
- `storage_set`
- `download_expect`
- `download_prepare`, `download_wait`, `download_list`, `download_get_info`
- `upload_files`
- `operation_cancel`

Network inspection:

- `network_enable`
- `network_disable`
- `network_list`
- `network_get_response`
- `network_summary`, `network_clear`
- `network_wait_for_request`, `network_wait_for_response`

Console inspection:

- `console_enable`, `console_disable`, `console_list`

## Agent-friendly model

`page_get_tree` returns a compact, limited tree by default. Interactive nodes receive `element_id`, `selector_hint`, `xpath_hint`, `actionable`, and `resolution_confidence`. An agent can observe the tree and call `element_click` or `element_fill` directly with the `element_id`, without calling `element_find` first.

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
- Screenshots, downloads, and uploads use controlled directories or an allowlist.
- Cookies and storage are redacted by default on read.
- Sensitive attributes such as tokens, passwords, and cookies are redacted.
- Logs must redact bearer tokens, cookies, authorization headers, and sensitive fields.

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

- `profiles/`
- `tmp/`
- `downloads/`
- `artifacts/`
- `logs/`

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
python -m mypy src
python -m pytest -m browser_smoke -q
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
- `operation_cancel` currently applies to waits that receive an explicit caller-provided `operation_id`.

## License

MIT
