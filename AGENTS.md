# Agent Instructions

## Project context

This repository implements a Python MCP server for browser automation with Pydoll. The
server exposes a predictable and safe API for agents while preserving Pydoll's async model
and client isolation.

The project language is English. Code, comments, documentation, commit messages, tests,
fixtures, and progress notes must be written in English. Conversation with Yuri may happen
in Portuguese, but repository artifacts should remain in English.

## Golden rule

Keep quality high from the first change. Do not accept shortcuts, defer cleanup, or assume
that temporary debt will be fixed later. Fix the root cause while the context is available.

Human readability, correctness, and safety take priority over terseness, implementation
speed, and clever abstractions.

## Local paths

- Project repository: `C:\Users\Yuri\Documents\Git\pydoll-mcp-server`.
- Local Pydoll repository, read-only: `C:\Users\Yuri\Documents\Git\pydoll`.
- Python via Anaconda: `C:\Users\Yuri\anaconda3\python.exe`.
- Vendored Pydoll documentation: `references/pydoll-docs/`.

These paths are local to this environment. Do not copy them into public documentation.

## Non-negotiable rules

- Treat this machine with care. This machine is our home.
- Do not run destructive actions unless strictly necessary, and never revert changes made by others.
- Preserve UTF-8 and do not use em dash characters.
- Do not modify the `websocket_lambda` repository. It is a style reference only.
- Do not copy secrets, credentials, or insecure patterns found in other projects.
- Do not expose `execute_cdp_cmd`, operating-system commands, or arbitrary filesystem access.
- Do not weaken Ruff, mypy, Pyright, the LSP, or tests to hide a problem.
- Do not bend production code to make mocks easier or to make tests pass.
- Do not add artificial backward compatibility to preserve incorrect alpha contracts.

## File size and module boundaries

- Target size: at most 400 physical lines per Python file.
- Hard limit: 450 physical lines per Python file.
- Files over 450 lines must be refactored before the work is considered complete.
- Files between 401 and 450 lines require a short review or progress note explaining why the
  code should remain together.
- Prefer cohesive extraction by domain behavior. Do not split a module only to satisfy a line
  count if the split makes the code harder to read.
- When a module nears the target, move stable helper logic, typed models, scripts, or adapters
  into focused sibling modules.

## Typing and data modeling

- Do not use `Any`, `cast`, or `type: ignore` to silence typing.
- Avoid loose dictionaries whose expected attributes are known only through scattered call-site
  knowledge.
- Model structured data with dataclasses, TypedDict, Protocol, enums, or small domain classes
  when the shape is known.
- Use `JsonObject` and `JsonArray` only at JSON boundaries, MCP responses, CDP event ingress,
  and places where the payload is genuinely dynamic.
- Normalize external dynamic values as soon as they enter the codebase. After normalization,
  pass typed objects through internal helpers.
- When an external library requires a dynamic boundary, isolate that boundary, validate the
  value, and convert it into a typed local representation immediately.

## Engineering and architecture

- Prefer direct operational flow, early validation, and domain-oriented names.
- Respect separation of responsibilities, low coupling, and explicit dependencies.
- Do not create abstractions without concrete benefit. Readable code comes before over-engineering.
- Internal errors should be specific. Convert them to structured MCP errors only at the proper
  top-level boundary.
- `except Exception` is acceptable only inside functions registered as MCP tools, after expected
  exceptions, to prevent server crashes and convert unexpected failures.
- Internal helpers and services should catch `PydollException` or more specific exceptions.
- Deep traversal must report partial failures in `errors` with `partial=true`; never hide them.
- Best-effort fallbacks must be explicit in name, safe, and documented.

## Comments and logs

Code comments must be in English, short, and used only to explain:

- functional or business rules;
- security or ownership boundaries;
- lock or concurrency decisions;
- destructive-operation risk;
- safe recovery or best-effort fallback rationale;
- non-obvious external-library behavior.

Do not narrate obvious code. Logs should capture relevant operations and transitions without
exposing tokens, cookies, storage, full JavaScript code, or sensitive content.

## Async, concurrency, and Pydoll

- Do not block the global event loop.
- Every potentially long operation must have an explicit timeout.
- A tool returns only when the action completes, fails, or times out.
- Use tab, browser, or profile locks for mutations that can interfere with each other.
- Independent resources should remain concurrent.
- Respect real Pydoll async APIs. Do not change async properties into methods only to satisfy tests.
- Treat frames, iframes, OOPIFs, and shadow roots as central architectural concerns.

## Tests

- Tests represent real contracts. Fakes should adapt to production code, not the opposite.
- Prefer small typed fakes over generic mocks and source inspection.
- Cover ownership, isolation, UTF-8, frames, shadow roots, timeout, cancellation, recovery,
  redaction, and path security.
- Never add production branches that exist only for tests.

Before concluding, run the relevant focused tests first, then the full gates when feasible:

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

## How to work and resume

1. Read this file, `README.md`, relevant code, and the latest applicable progress note.
2. Check `git status --short` and do not revert existing changes.
3. Consult local Pydoll code or vendored docs before assuming a capability.
4. Make cohesive changes and keep quality gates green.
5. Record concise progress in `progress/YYYY-MM-DD_AGENT_<TASK>.md` when needed.

When in doubt, investigate the code and documentation first. If uncertainty remains, choose the
safer option and record the limitation.
