# Release Checklist

## 0.1.0a1 - Experimental Alpha

### Pre-release checks
- [x] `pytest -q`: 184 passed
- [x] `ruff check .`: All checks passed
- [x] `mypy src`: Success (38 source files)
- [x] `pytest -m browser_smoke -q`: 9 passed
- [x] `sdist` and `wheel` built successfully
- [x] Wheel installed in temporary venv and import verified
- [x] `LICENSE` exists (MIT)
- [x] `CHANGELOG.md` exists
- [x] `docs/security.md` exists
- [x] README updated for P2 state

### Transport validation
- [x] HTTP local on 127.0.0.1 works
- [x] Bearer token required by default
- [x] `/health` responds without token
- [x] `/mcp` requires token
- [x] `/sse` endpoint exists
- [x] `stdio` transport available via `--transport stdio` (no token required)
- [x] `stdio` probe passes: `'' | python -m pydoll_mcp_server.cli --transport stdio`

### Version consistency
- [x] `pyproject.toml`: `0.1.0a1`
- [x] `health_check["version"]`: `0.1.0a1`
- [x] `server_status["version"]`: `0.1.0a1`
- [x] `/health` response: `version: 0.1.0a1`

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
- [x] Console: enable, disable, list (returns UNSUPPORTED)
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
- [x] console UNSUPPORTED tested
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
