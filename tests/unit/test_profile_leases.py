"""Tests for cross-process profile leases."""

from pathlib import Path

from pytest import MonkeyPatch

from pydoll_mcp_server.browser.profile_leases import ProfileLeaseManager


def test_profile_lease_prevents_second_owner(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv('PYDOLL_MCP_AUTH_TOKEN', 'test-token')
    monkeypatch.setenv('PYDOLL_MCP_RUNTIME_DIR', str(tmp_path))
    from pydoll_mcp_server.config import get_config

    get_config.cache_clear()
    first = ProfileLeaseManager()
    second = ProfileLeaseManager()
    profile = tmp_path / 'profiles' / 'client' / 'default'
    profile.mkdir(parents=True)

    lease = first.acquire(str(profile), 'client-a', 'profile-a')
    assert lease is not None
    assert second.acquire(str(profile), 'client-b', 'profile-b') is None

    first.release(lease)
    released = second.acquire(str(profile), 'client-b', 'profile-b')
    assert released is not None
    second.release(released)
