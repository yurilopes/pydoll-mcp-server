# PLAN_15: Release 0.4.0b1

## Objective

Prepare `pydoll-mcp-server` for version `0.4.0b1` as the first beta-quality
release after the validated PLAN_14 browser form flow work.

This plan is about release readiness. It must not publish to PyPI, create tags,
push branches, open pull requests, or change repository history. Those actions
require explicit human authorization after the release candidate is reviewed.

The release should communicate that the main MCP contracts are usable by agents
in real browser workflows, while keeping honest experimental labels for areas
that still need broader hardening.

## Confirmed Baseline

- The repository currently reports `0.3.0a1` in
  `src/pydoll_mcp_server/version.py`.
- `docs/release-checklist.md` currently documents `0.3.0a1 - Experimental
  Alpha`.
- `CHANGELOG.md` currently starts with `0.3.0a1 (Unreleased)`.
- PLAN_14 added the active surface, ranked text candidate, click effect,
  re-resolution, form fill, primary action, upload preparation, submission
  confirmation, and artifact-first screenshot work.
- The PLAN_14 implementation was validated in prior review with full unit,
  contract, browser smoke, MCP E2E, typing, linting, formatting, and build
  gates.
- The working tree contains existing modified and untracked files from PLAN_14.
  The release implementer must preserve those changes and must not revert,
  rename, delete, or overwrite unrelated work.

## Release Metadata Work

The implementation agent must update version metadata consistently:

- Set `src/pydoll_mcp_server/version.py` to `0.4.0b1`.
- Update `pyproject.toml` release maturity classifier to
  `Development Status :: 4 - Beta`.
- Confirm Hatchling still derives package metadata from the source version.
- Verify that `health_check`, `server_status`, `/health`, built wheel metadata,
  and installed package metadata all report `0.4.0b1`.
- Keep Python version requirements, package name, license, entry points, and
  package data unchanged unless a failing release check proves they are wrong.

Do not add artificial compatibility code for old alpha-only behavior. If a
contract is incorrect, fix or document it honestly instead of preserving a
broken shape.

## Public Documentation Work

Update public documentation for the beta release:

- Add or replace the top `CHANGELOG.md` entry with `0.4.0b1 (Unreleased)`.
- Consolidate PLAN_14 user-visible changes under `0.4.0b1` when they are part
  of the beta release.
- Keep older release entries intact. Do not invent a release date.
- Update `README.md` to describe the current beta capability set and the
  agent-friendly form workflow surface.
- Update `docs/agent-recipes.md` with the recommended high-level flow:
  observe active surface, fill by intent, prepare upload, upload, advance,
  review, submit, wait for confirmation.
- Update `docs/security.md` with the beta security model for artifacts,
  upload preparation, screenshots, JavaScript tools, redaction, filesystem
  boundaries, and unsupported dangerous capabilities.
- Update `docs/pydoll-capabilities.md` to reflect capabilities actually used by
  the current implementation. Consult the local Pydoll repository and
  `references/pydoll-docs/` before claiming support.
- Update `docs/release-checklist.md` with a new `0.4.0b1 - Beta` section.

Public docs must not include local machine paths such as user home directories,
Anaconda paths, or local clone locations. Local paths are allowed only in
internal progress and developer prompt artifacts.

## Release Checklist Work

`docs/release-checklist.md` must become the source of truth for beta readiness.
The new `0.4.0b1 - Beta` section must include:

- exact gate commands required by `AGENTS.md`;
- actual pass or fail results after implementation;
- note about Windows temporary directory permission behavior if reproduced;
- MCP stdio handshake and real tool listing result;
- current public tool count measured from the implementation, not copied from
  the old `0.3.0a1` checklist;
- package build result;
- wheel install smoke result in a temporary clean environment;
- installed package version verification;
- `py.typed` verification;
- security validation summary;
- pending human review, GitHub tag, GitHub release, and PyPI publication.

The checklist must distinguish release preparation from release publication.
Publishing remains manual and out of scope unless the user later authorizes it.

## Security And Quality Constraints

The release work must preserve the repository's security-first posture:

- Do not expose `execute_cdp_cmd`.
- Do not add OS command execution tools.
- Do not allow arbitrary filesystem access.
- Do not weaken artifact, upload, screenshot, download, or path allowlists.
- Keep `artifact_prepare_upload` complementary to `artifact_import`.
- Keep screenshots artifact-first by default, with base64 only by explicit opt-in.
- Keep operational evidence bounded, short, redacted, and free of tokens,
  cookies, storage values, file contents, full JavaScript, or large page text.
- Keep mutating browser actions behind tab, browser, or profile locks where
  interference is possible.
- Keep async behavior real and use explicit timeouts for potentially long
  operations.

The implementation must also preserve quality gates:

- Do not weaken Ruff, mypy, Pyright, LSP, or tests.
- Do not use `Any`, `cast`, or `type: ignore` to hide typing problems.
- Do not add production branches only for tests.
- Keep Python files under the 400 line target where practical and under the
  450 line maximum. Any 401 to 450 line file requires a short progress note.

## Implementation Order

1. Read required context and verify `git status --short`.
2. Update version metadata and release classifier.
3. Add or update focused tests for version, metadata, contract inventory, and
   prohibited tool absence if current coverage is insufficient.
4. Update changelog, release checklist, and public docs.
5. Build the package and run an install smoke in a temporary environment.
6. Run every gate from `AGENTS.md`.
7. Record concise progress with exact results and remaining human-only release
   actions.

## Acceptance Criteria

- Source version, package metadata, wheel metadata, installed metadata, server
  status, health check, and `/health` all report `0.4.0b1`.
- `pyproject.toml` advertises beta maturity.
- `CHANGELOG.md` and `docs/release-checklist.md` describe `0.4.0b1`.
- Public docs describe PLAN_14 capabilities as part of the beta release without
  local paths.
- Public tools are inventoried and prohibited capabilities remain absent.
- Wheel builds and installs in a clean temporary environment.
- `py.typed` is present in the installed package.
- All required gates from `AGENTS.md` pass or any environmental rerun is clearly
  recorded with isolated `--basetemp`.
- No tag, push, GitHub release, or PyPI publication is performed.
