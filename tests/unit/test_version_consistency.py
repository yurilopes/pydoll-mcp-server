"""Version consistency across source and public health responses."""

from pytest import MonkeyPatch

from pydoll_mcp_server import __version__ as public_version
from pydoll_mcp_server.config import get_config
from pydoll_mcp_server.tools.diagnostics import health_check, server_status
from pydoll_mcp_server.tools.health import get_health_response
from pydoll_mcp_server.version import __version__, get_version


def test_source_and_health_responses_share_one_version(monkeypatch: MonkeyPatch) -> None:
    expected = '0.3.0a1'
    monkeypatch.setenv('PYDOLL_MCP_ALLOW_NO_AUTH', 'true')
    get_config.cache_clear()

    assert __version__ == expected
    assert public_version == expected
    assert get_version() == expected
    assert get_health_response()['version'] == expected
    assert health_check()['version'] == expected
    assert server_status()['version'] == expected
    get_config.cache_clear()
