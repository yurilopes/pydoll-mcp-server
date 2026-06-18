# PLAN_16: User Authenticated Browser Profiles

## Objective

Plan the implementation of predictable session continuity for authenticated
websites. This planning artifact does not implement production code. A later
Developer LLM must implement the code, tests, and documentation changes
described here, and this agent will validate that implementation afterward.

The improvement should make the intent "open this site as the already logged-in
user" a supported MCP workflow, without requiring agents to understand runtime
directory internals, Chrome profile layouts, or the interaction between
`client_id`, `profile_mode`, and profile paths.

## Current Baseline

- `browser_launch` currently defaults to `profile_mode="persistent"` in
  `src/pydoll_mcp_server/tools/browser.py`.
- `docs/agent-recipes.md` still recommends the universal first step
  `browser_launch(client_id, headless=false, profile_mode="temporary")`.
- Persistent profile reuse is coupled to the exact `client_id` and the managed
  profile layout under `profiles/<client_id>/<profile_name>`.
- Temporary profiles are created under the managed runtime `tmp` area and may
  remain on disk after manual or failed cleanup, but they are not discoverable
  or reusable through a supported public MCP workflow.
- There is no public tool to list managed profiles, identify safe site hints, or
  promote a preserved temporary profile to a persistent named profile.

The root cause is not lack of isolation. The server has useful isolation, but it
does not yet provide a user-oriented continuity layer for authenticated
sessions. As a result, agents can make a technically safe choice that looks to
the user like the MCP forgot their login.

## Implementation Changes

### Profile Metadata And Index

Add a profile metadata layer backed by `runtime_dir/profiles/index.json`.

The index must store only safe metadata:

- logical `profile_id`;
- `owner_client_id`;
- `mode`;
- `created_at`;
- `last_used_at`;
- redacted `last_urls_redacted`;
- domain-only `site_hints`;
- optional `display_name`;
- `path_kind`.

Do not store cookies, tokens, localStorage values, sessionStorage values, proxy
credentials, raw Chrome database rows, JavaScript content, or arbitrary absolute
paths in public responses.

Normal discovery must use this index. The implementation may inspect managed
profile directories only for safe recovery of preserved temporary profiles, and
must not depend on Chrome SQLite internals for ordinary profile listing.

Update metadata on:

- persistent profile creation or launch;
- successful `page_goto`, using a redacted URL and a normalized domain hint;
- profile promotion.

### Public API

Extend `browser_launch` with optional arguments:

- `session_intent: str = ""`;
- `site_hint: str = ""`.

Keep existing `profile_mode`, `profile_id`, `client_id`, proxy arguments, and
response compatibility for existing callers.

Add tools:

- `profile_list(include_site_hints: bool = false)`;
- `profile_promote(source_profile_id, target_profile_id, client_id, overwrite=false)`.

Register both tools in `tool_catalog.py`.

Add `AMBIGUOUS_PROFILE` to `ErrorCode` for cases where the server finds multiple
safe candidates and must not choose silently.

Successful `browser_launch` responses may include a `warnings` array. Each
warning should be structured with at least `code` and `message`, and may include
safe metadata such as candidate logical profile ids.

### Discovery Behavior

`profile_list` must return managed persistent profiles and safely discoverable
preserved temporary profiles under managed runtime roots.

Response entries should use logical ids, for example:

- `codex/default`;
- `codex/linkedin`;
- `recovered/profile_vduwyale`.

Each entry may include:

- `profile_id`;
- `owner_client_id`;
- `mode`;
- `last_used_at`;
- `site_hints` when `include_site_hints=true`;
- `display_name`;
- `path_kind`;
- `is_locked`.

Do not return absolute local paths by default. If a diagnostic mode is ever added
later, it must be explicit and still limited to managed runtime paths.

`site_hints` must be domains only. Full URLs are allowed only in redacted fields
whose shape is intentionally safe, such as `https://www.linkedin.com/feed/`.
Never include query strings likely to contain tokens, auth codes, search terms,
or personal data.

### Promotion Behavior

`profile_promote` must copy a preserved temporary profile into a managed
persistent profile location.

Required rules:

- validate that the source is inside the MCP managed runtime roots;
- reject sources outside managed roots with a structured error;
- reject overwrite of an existing persistent target unless `overwrite=true`;
- preserve the source profile;
- remove Chrome lock files such as `Singleton*` from the copied target;
- write or update safe index metadata for the target;
- audit the promotion without secrets and without absolute local paths in public
  responses.

The operation should return logical metadata, not local filesystem paths, by
default.

### Semantic Launch Intent

When `browser_launch` receives:

```json
{
  "session_intent": "user_authenticated",
  "site_hint": "linkedin.com"
}
```

the server must:

1. Normalize `site_hint` to a safe domain.
2. Search recent persistent profiles with that domain hint.
3. Launch with the single matching persistent profile when exactly one exists.
4. Return `AMBIGUOUS_PROFILE` with safe candidate options when multiple
   persistent matches exist.
5. If only preserved temporary matches exist, return a structured recommendation
   to call `profile_promote`. Do not silently copy profile directories.
6. If no match exists, create or use a stable persistent profile and include a
   warning that login may be required.

If `profile_mode="temporary"` is used with a known authenticated-site hint, the
tool should still launch successfully but include a non-blocking warning such as
`TEMPORARY_PROFILE_FOR_AUTH_SITE`.

The default authenticated profile id for a stable human workflow should be
documented and deterministic. Prefer simple names such as `default-user`,
`main`, `work`, or a site-specific name such as `linkedin`, rather than generated
per-attempt ids.

### Documentation

Update public documentation after implementation:

- `README.md`: list the new profile tools, describe the runtime profile model,
  and explain authenticated session continuity.
- `docs/agent-recipes.md`: stop recommending temporary profiles as the
  universal first step.
- `docs/agent-recipes.md`: recommend temporary profiles only for disposable
  browsing, tests, scraping isolation, and clean-session workflows.
- `docs/agent-recipes.md`: recommend `session_intent="user_authenticated"` plus
  `site_hint`, or persistent named `profile_id`, when a user asks to open a
  personal or authenticated website.
- `docs/agent-recipes.md`: document that agents must use a stable `client_id`
  when the user expects browser state continuity.
- `docs/security.md`: document that profile metadata is safe, redacted, and does
  not expose cookies, storage values, tokens, or arbitrary paths.

Public docs must not include local machine paths.

## Tests And Acceptance Criteria

Add focused tests before or with the implementation.

Required unit tests:

- profile id normalization;
- index persistence and reload;
- safe URL redaction;
- site hint extraction;
- managed path validation;
- overwrite refusal in `profile_promote`;
- Chrome lock file removal from promoted copies;
- ambiguous profile selection.

Required contract tests:

- `profile_list` and `profile_promote` are registered MCP tools;
- prohibited capabilities remain absent;
- new structured responses remain JSON objects with no secret-bearing fields.

Required launch behavior tests with fakes:

- authenticated intent chooses the single matching persistent profile;
- no match creates or uses a stable persistent profile and returns a warning;
- multiple matches return `AMBIGUOUS_PROFILE`;
- temporary-only match returns a promotion recommendation;
- temporary profile with authenticated-site hint returns
  `TEMPORARY_PROFILE_FOR_AUTH_SITE` warning.

Required navigation and security tests:

- successful `page_goto` updates safe profile metadata;
- responses do not contain cookies, tokens, storage values, proxy credentials,
  absolute local paths, or raw Chrome profile internals.

Run all gates required by `AGENTS.md` after implementation:

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

Record exact pass or fail results in
`progress/2026-06-17_AGENT_PLAN_16_USER_AUTHENTICATED_PROFILES.md`.

## Constraints

- Do not expose `execute_cdp_cmd`.
- Do not add OS command tools or arbitrary filesystem access.
- Do not weaken Ruff, mypy, Pyright, tests, or security policy.
- Do not use `Any`, `cast`, or `type: ignore` to hide typing problems.
- Do not add production branches only for tests.
- Keep potentially long operations timed out.
- Use locks for profile mutations that can interfere with active browsers.
- Keep internal errors specific and convert them to structured MCP errors at the
  tool boundary.
- Preserve existing callers unless a contract is demonstrably unsafe.

## Validation Plan

After the Developer LLM implements PLAN_16, validation must confirm:

- existing `browser_launch` calls with `profile_mode` and optional `profile_id`
  still work;
- `session_intent="user_authenticated"` uses stable profile selection and does
  not silently choose among ambiguous candidates;
- `profile_list` and `profile_promote` expose only safe logical metadata;
- preserved temporary profile promotion copies only from managed runtime
  directories and refuses overwrite by default;
- `README.md` and `docs/agent-recipes.md` no longer teach temporary profiles as
  the universal first step;
- all `AGENTS.md` gates pass, or failures are recorded with exact commands and
  actionable causes.
