"""Shared pytest setup for local, sandbox-friendly test artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    # Keep pytest artifacts inside the repository so tests do not depend on user profile temp permissions.
    Path('.tmp/pytest').mkdir(parents=True, exist_ok=True)
    Path('.tmp/pytest-cache').mkdir(parents=True, exist_ok=True)
