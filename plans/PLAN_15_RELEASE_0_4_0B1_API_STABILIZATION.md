# PLAN_15 API Stabilization For 0.4.0b1

## Goal

Define the API stabilization pass required before calling `0.4.0b1` a beta.
The goal is not to freeze every alpha detail forever. The goal is to make the
agent-facing contract honest, documented, tested, and safe enough for beta use.

## Public Tool Inventory

The implementation agent must generate the public MCP tool inventory from the
current code and contract tests, then compare it with the documentation.

The inventory must record:

- tool name;
- capability group;
- beta status;
- mutating or observation-only behavior;
- sensitive value exposure behavior;
- filesystem or artifact boundary, when applicable;
- whether structured errors are expected;
- whether operational evidence is returned.

The tool count must be measured during the release pass. Do not copy the old
`0.3.0a1` count from `docs/release-checklist.md`.

## Beta Status Categories

Classify public tools into these categories.

### beta-supported

Use `beta-supported` for tools whose contracts are intended for normal agent
use in `0.4.0b1`:

- browser lifecycle;
- tab lifecycle and recovery;
- navigation and page waits;
- page text and tree observation;
- active surface observation;
- element find, click, type, fill, screenshot, and attributes;
- semantic actions and ranked text candidates;
- click effect validation;
- stale element recovery;
- form snapshots and intent-driven form filling;
- primary action progression;
- downloads, artifacts, upload preparation, and uploads;
- screenshot tools with artifact-first defaults;
- diagnostics, network, console, and trace tools with redaction;
- stdio and HTTP transports;
- health and server status.

### experimental

Use `experimental` for capabilities that are useful but still need explicit
caveats:

- manual JavaScript tools, including readonly variants;
- deep DOM traversal across frames, shadow roots, OOPIFs, or partial failures;
- features that depend on browser or site behavior not fully normalized by the
  server;
- `browser_attach` if it remains intentionally unsupported or limited;
- fallback click strategies that dispatch pointer or mouse event sequences.

Experimental tools may remain public, but documentation must state the caveat
and preferred beta-supported alternative.

## PLAN_14 Contract Surface

The beta docs and tests must explicitly cover the PLAN_14 additions:

- `page_get_active_surface`;
- `element_find_by_text_candidates`;
- enhanced `element_click_by_text` filters and ambiguity refusal;
- enhanced `element_click` effect validation;
- `element_resolve_again`;
- `form_fill_fields`;
- `page_click_primary_action`;
- `submission_wait_for_confirmation`;
- `artifact_prepare_upload`;
- enhanced `upload_files` upload visibility diagnostics;
- `page_screenshot` and `element_screenshot` artifact-first behavior.

For each capability, document the intended beta usage pattern, not only the raw
parameter list.

## Error Contract

Structured failures must keep using explicit MCP error codes at the tool
boundary.

Required codes to verify:

- `AMBIGUOUS_ELEMENT`;
- `STALE_ELEMENT`;
- `PERMISSION_DENIED`;
- `TIMEOUT`;
- `INVALID_INPUT`;
- `EXECUTION_ERROR`.

The release pass must confirm that ambiguity, stale element recovery failure,
permission denial for paths, timeout, invalid input, and unexpected execution
failure all produce structured responses that an agent can act on.

## Evidence And Redaction Contract

Sensitive, mutating, diagnostic, upload, submission, and screenshot operations
must keep evidence short and structured.

Evidence may include:

- timestamp;
- target element summary;
- strategy used;
- before and after state where safe;
- validation text;
- warnings;
- redaction status.

Evidence must not include:

- tokens;
- cookies;
- storage values;
- passwords;
- bearer tokens;
- file contents;
- full JavaScript;
- large page text;
- unbounded form values.

Snapshot and form tools must keep `include_values=false` as the default. When
values are explicitly requested, return only bounded non-sensitive previews and
mark sensitive values as redacted.

## Compatibility Policy

For `0.4.0b1`, compatibility should be honest instead of artificial:

- Preserve useful existing tools and response fields when they are not wrong.
- Fix incorrect alpha contracts when necessary for safety or predictability.
- Do not preserve broken alpha behavior only to avoid a documented change.
- Document any intentional contract adjustment in `CHANGELOG.md`.
- Do not remove a public tool without an explicit rationale in progress notes
  and release checklist.
- Prefer additive docs and focused tests over broad rewrites.

## Security Contract

The beta API must continue to reject capabilities outside the MCP server's
security model:

- no free CDP command execution;
- no operating system command tool;
- no arbitrary filesystem browsing or copying;
- no secret logging;
- no unbounded browser state extraction;
- no upload from paths outside controlled runtime directories or explicit
  allowlists.

If a release validation finds a gap, the implementer must fix the root cause
before marking `0.4.0b1` ready.
