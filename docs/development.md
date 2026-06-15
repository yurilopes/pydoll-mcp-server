# Development Guide

## Quality rule

Hold the line on code quality from the first change. Do not defer cleanup, hide typing
problems, or add temporary compatibility behavior with the expectation that it will be
removed later.

Human readability, correctness, and security take priority over terse code and premature
abstraction.

## Engineering conventions

- Keep control flow direct and validate inputs and ownership early.
- Use names that express browser automation concepts and operational intent.
- Respect layering, separation of concerns, and explicit dependencies.
- Add an abstraction only when it removes real duplication or isolates a meaningful rule.
- Fix the root cause reported by Ruff, mypy, Pyright, the LSP, or tests.
- Keep dynamic third-party values inside a small typed boundary and normalize them before
  they enter core logic.
- Avoid `Any`, `cast`, `type: ignore`, silent exceptions, and defensive fallbacks.
- Convert domain errors to structured MCP errors at the tool boundary.
- Catch `Exception` only inside registered MCP tool functions, after expected exceptions.
- Internal services must catch `PydollException` or specific expected exceptions. Partial
  traversal failures must be returned explicitly instead of silently ignored.
- Never change correct production behavior only to simplify a test.

## Comments

Source comments are written in English. Add a comment only when it explains a functional
rule, security boundary, ownership rule, concurrency decision, destructive action, or safe
best-effort behavior.

Do not narrate obvious operations.

## File size

Python files should remain at or below 400 physical lines. The hard limit is 450 lines.
A file between 401 and 450 lines requires a short review justification. Refactor files
above the hard limit while preserving logical cohesion.

## Required checks

```shell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy --strict src tests
python -m pyright
python -m pytest -m mcp_e2e -q
python -m pytest -m browser_smoke -q
python -m build
```

Tests must validate observable contracts. Prefer small typed fakes over generic mocks and
source inspection.
