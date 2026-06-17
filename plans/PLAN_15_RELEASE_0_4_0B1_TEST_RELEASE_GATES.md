# PLAN_15 Test And Release Gates For 0.4.0b1

## Goal

Verify that `0.4.0b1` is installable, documented, secure, and usable as a beta
MCP server after the PLAN_14 workflow additions.

Tests should be added before release metadata is considered complete whenever a
gap is found. Do not add production-only branches for tests.

## Required Test Coverage

Add or update focused tests if current coverage does not already prove these
contracts:

- source version is `0.4.0b1`;
- package metadata derives from the source version;
- release classifier is beta;
- health check and server status report the source version;
- contract test includes all public tools, including the PLAN_14 tools;
- prohibited tools are absent, especially `execute_cdp_cmd`, OS command tools,
  and arbitrary filesystem tools;
- `artifact_prepare_upload` remains complementary to `artifact_import`;
- screenshot tools default to artifact paths unless base64 is explicitly
  requested;
- structured error codes include `AMBIGUOUS_ELEMENT`, `STALE_ELEMENT`,
  `PERMISSION_DENIED`, `TIMEOUT`, `INVALID_INPUT`, and `EXECUTION_ERROR`;
- docs or release checklist do not rely on the old `0.3.0a1` tool count.

The existing PLAN_14 browser smoke flow remains part of the release acceptance
criteria. It must complete the multi-step fixture with upload, review, submit,
and confirmation using high-level tools and without manual `js_evaluate`.

## Package Install Smoke

The release pass must validate the built wheel in a temporary clean environment.

The smoke must prove:

- wheel builds successfully;
- wheel installs without editable mode;
- importing `pydoll_mcp_server` succeeds;
- installed version is `0.4.0b1`;
- `py.typed` is present in the installed package;
- CLI help, server health, or an equivalent non-browser startup check works;
- no local repository path is required at runtime.

Record the exact command and result in `docs/release-checklist.md` or progress.
Use a temporary environment and clean it up when safe.

## Required Gates

Run every gate required by `AGENTS.md` before concluding:

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

If Windows blocks the default pytest cache or temporary directory with
`WinError 5`, rerun pytest with an isolated `--basetemp` directory and record
both the environmental failure and the successful isolated result.

## MCP Runtime Validation

The release pass must include runtime-level checks:

- MCP stdio handshake succeeds;
- real tool listing succeeds;
- current tool count is recorded from the actual server;
- no prohibited tool names appear in the MCP listing;
- at least one real MCP browser workflow passes;
- HTTP health behavior remains correct if HTTP transport is validated.

Do not rely only on unit tests for release readiness.

## Documentation Validation

Check public docs after edits:

- no local machine paths in `README.md`, `CHANGELOG.md`, `docs/*.md`, or client
  docs;
- `0.4.0b1` appears where release status is discussed;
- `0.3.0a1` remains only as historical context or previous release data;
- PLAN_14 beta tools are described as generic browser automation capabilities,
  not as job-site-specific workflows;
- release checklist clearly separates completed checks from pending human
  release actions.

## Final Acceptance

The release implementation is complete only when:

- all required gates pass;
- package install smoke passes;
- MCP runtime validation passes;
- docs and changelog are updated;
- version metadata is consistent;
- no release publication action was performed;
- progress records exact gate results and pending human actions.
