"""Test configuration and fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / 'fixtures' / 'pages'


@pytest.fixture
def simple_html(fixtures_dir: Path) -> str:
    return str(fixtures_dir / 'simple.html')


@pytest.fixture
def unicode_html(fixtures_dir: Path) -> str:
    return str(fixtures_dir / 'unicode.html')


@pytest.fixture
def form_html(fixtures_dir: Path) -> str:
    return str(fixtures_dir / 'form.html')


@pytest.fixture
def iframe_parent_html(fixtures_dir: Path) -> str:
    return str(fixtures_dir / 'iframe-parent.html')


@pytest.fixture
def shadow_dom_html(fixtures_dir: Path) -> str:
    return str(fixtures_dir / 'shadow-dom.html')


@pytest.fixture
def delay_html(fixtures_dir: Path) -> str:
    return str(fixtures_dir / 'delay.html')


@pytest.fixture
def many_nodes_html(fixtures_dir: Path) -> str:
    return str(fixtures_dir / 'many-nodes.html')


def pytest_configure(config) -> None:
    config.addinivalue_line('markers', 'unit: Unit tests')
    config.addinivalue_line('markers', 'integration: Integration tests requiring browser')
    config.addinivalue_line('markers', 'browser: Tests requiring full browser')
    config.addinivalue_line('markers', 'slow: Slow tests')
    config.addinivalue_line('markers', 'contract: MCP contract tests')
