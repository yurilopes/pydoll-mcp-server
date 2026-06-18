# Security

Pydoll MCP Server is designed to be secure by default for local browser automation.

## Threat Model

The server runs **locally** on `127.0.0.1` by default. It is not intended for network exposure. The primary threats are:

1. Unauthorized local clients connecting to the MCP endpoint
2. Sensitive data leaking through logs, cookies, storage, or screenshots
3. Malicious JavaScript execution through `js_evaluate`
4. Filesystem access through upload/download/screenshot paths
5. Browser profile corruption through concurrent access

## Bearer Token

- **Required by default** for HTTP transport.
- Set via `PYDOLL_MCP_AUTH_TOKEN` environment variable.
- Development bypass only with `PYDOLL_MCP_ALLOW_NO_AUTH=true`.
- Token is never logged, never stored in artifacts, never returned in diagnostics.

## Cookies and Storage

- `cookies_get` and `storage_get` **redact values by default** (`redact_values=true`).
- `cookies_set` and `storage_set` require explicit `tab_id` or `browser_id`.
- Cookie values are never logged in full.

## JavaScript Execution

- `js_evaluate_readonly` blocks known dangerous patterns:
  - `document.cookie` access
  - `localStorage` / `sessionStorage` access
  - Form submission (`.submit()`)
  - Location assignment (`location =`, `location.href =`)
  - Infinite loops (`while(true)`)
- `js_evaluate` allows side effects but logs audit summary (script hash, duration, result size).
- Both tools have time limits (default 5s, max 15s) and code size limits (max 20,000 chars).
- Script content and full results are not logged.

## Uploads and Downloads

- **Upload**: only paths inside `artifacts_dir`, `downloads_dir`, or `tmp_dir`.
- **Upload preparation**: `artifact_prepare_upload` copies allowed files into the
  controlled client artifact directory before upload. It rejects sources outside
  runtime directories and explicit allowlists, returns exact allowed directories
  on denial, and sanitizes filenames.
- **Download**: files stored in `downloads_dir/{client_id}/`.
- **Screenshots**: saved to artifact files by default (`return_base64=false`).
  Base64 is returned only with explicit opt-in. Path writing validated against
  allowed directories.
- Path traversal (`../escape.png`) is blocked via `Path.resolve()` + `relative_to()`.

## Profiles

- Profile metadata is stored in `profiles/index.json` without exposing cookies,
  tokens, localStorage, sessionStorage, passwords, proxy credentials, or
  absolute filesystem paths.
- Default persistent profile per `client_id`.
- Profiles are locked exclusively to prevent concurrent Chrome access.
- Temporary profiles are cleaned up on browser close.
- Profile data stored in OS-specific app data, outside the repository.
- `profile_list` returns only logical metadata: profile_id, mode, last_used_at,
  display_name, path_kind, and optional site_hints (domain only).
- `profile_promote` validates source is inside managed runtime directories,
  sanitizes destination paths via `ClientIdentity`, and refuses overwrite by
  default. Chrome lock files (`Singleton*`) are removed from promoted copies.
- `session_intent="user_authenticated"` with `site_hint` prefers a single
  matching persistent profile; when multiple match, returns `AMBIGUOUS_PROFILE`
  structured error with safe options; when only temp matches exist, returns
  structured recommendation to call `profile_promote`.

## Network and Console Inspection

- Network events are opt-in per tab via `network_enable`.
- `network_get_request` is deliberately raw and can return cookies, authorization
  headers, tokens, form values, and personal data. Its result is never copied into
  server logs or traces.
- Raw request captures remain in bounded per-tab memory only. `network_clear`,
  `network_disable`, tab close, browser close, and tab recreation remove them.
- `network_list` and network waits return compact sanitized summaries. Consumers must
  not log `network_get_request` results automatically.
- `http_request` and `network_replay_request` return raw headers and bodies. Their content
  is excluded from logs and traces, but callers must treat the tool result as sensitive.
- Direct HTTP is same-host by default. Cross-origin requests require an explicit opt-in,
  embedded URL credentials are blocked, and every redirect is validated before following.
- Replay of POST, PUT, PATCH, or DELETE requires `confirm_side_effects=true` because it may
  duplicate an external side effect.
- Network response bodies are size-limited and redacted by default.
- Console inspection uses bounded, redacted Chromium Runtime events and returns `UNSUPPORTED` when unavailable.
- Proxy URLs are validated before browser launch. Responses and browser metadata never expose proxy credentials.
- Loopback and unspecified proxy hosts are blocked, and proxy settings cannot be changed after launch.

## Diagnostics and Trace

- `diagnostics_snapshot` never includes:
  - Bearer token
  - Cookie values
  - Storage values
  - Full JS code
  - Full response bodies
- Trace events are stored in memory with per-client isolation and size limits.

## Prohibited Methods

The following are NOT exposed as MCP tools:

- `execute_cdp_cmd` - would allow arbitrary CDP commands
- OS command execution - not in scope
- Arbitrary filesystem read/write - blocked by path allowlist
- CAPTCHA bypass, fraud automation, or security evasion

## Runtime Cleanup

- Stale profile locks are released on browser close.
- Temporary directories cleaned up.
- Server startup does NOT kill Chrome processes (only cleans metadata).
