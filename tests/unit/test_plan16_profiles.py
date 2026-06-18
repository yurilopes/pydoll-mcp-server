"""Unit tests for PLAN_16 User Authenticated Browser Profiles."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


class TestProfileIndex:
    def test_index_persists_and_reloads(self) -> None:
        from pydoll_mcp_server.browser.profile_index import (
            ProfileIndex,
            ProfileIndexEntry,
        )

        tmp_dir = Path(tempfile.mkdtemp())
        config = MagicMock()
        config.profiles_dir = tmp_dir

        with patch('pydoll_mcp_server.browser.profile_index.get_config', return_value=config):
            idx = ProfileIndex()
            entry = ProfileIndexEntry(
                profile_id='prof_test_default',
                owner_client_id='test',
                mode='persistent',
                created_at=1000.0,
                display_name='test',
                site_hints=['example.com'],
            )
            idx.upsert('prof_test_default', entry)

        config2 = MagicMock()
        config2.profiles_dir = tmp_dir
        with patch('pydoll_mcp_server.browser.profile_index.get_config', return_value=config2):
            idx2 = ProfileIndex()
            saved = idx2.get('prof_test_default')
            assert saved is not None
            assert saved.site_hints == ['example.com']

    def test_find_matching_by_site_hint(self) -> None:
        from pydoll_mcp_server.browser.profile_index import (
            ProfileIndex,
            ProfileIndexEntry,
        )

        config = MagicMock()
        config.profiles_dir = Path(tempfile.mkdtemp())

        with patch('pydoll_mcp_server.browser.profile_index.get_config', return_value=config):
            idx = ProfileIndex()
            idx.upsert(
                'prof_a',
                ProfileIndexEntry(
                    profile_id='prof_a',
                    owner_client_id='client1',
                    mode='persistent',
                    created_at=1000,
                    site_hints=['linkedin.com'],
                ),
            )
            idx.upsert(
                'prof_b',
                ProfileIndexEntry(
                    profile_id='prof_b',
                    owner_client_id='client1',
                    mode='persistent',
                    created_at=2000,
                    site_hints=['github.com'],
                ),
            )

            matches = idx.find_matching('client1', 'linkedin.com')
            assert len(matches) == 1
            assert matches[0].profile_id == 'prof_a'

            matches2 = idx.find_matching('client1', 'nonexistent.com')
            assert len(matches2) == 0

    def test_preserved_temp_with_mismatched_hints_excluded(self) -> None:
        from pydoll_mcp_server.browser.profile_index import (
            ProfileIndex,
            ProfileIndexEntry,
        )

        tmp_dir = Path(tempfile.mkdtemp())
        config = MagicMock()
        config.profiles_dir = tmp_dir
        config.tmp_dir = tmp_dir / 'tmp'

        with patch('pydoll_mcp_server.browser.profile_index.get_config', return_value=config):
            idx = ProfileIndex()
            idx.upsert(
                'preserved_client1_profile_abc',
                ProfileIndexEntry(
                    profile_id='preserved_client1_profile_abc',
                    owner_client_id='client1',
                    mode='temporary',
                    created_at=1000,
                    site_hints=['github.com'],
                    path_kind='preserved_temporary',
                ),
            )

            matches = idx.find_matching('client1', 'linkedin.com', mode_filter='temporary')
            assert len(matches) == 0, f'Should not match: {matches}'

    def test_url_redaction_removes_query(self) -> None:
        from pydoll_mcp_server.browser.profile_index import redact_url

        result = redact_url('https://example.com/path?token=secret&user=123')
        assert 'token' not in result
        assert 'secret' not in result
        assert result == 'https://example.com/path'

    def test_site_hint_extraction(self) -> None:
        from pydoll_mcp_server.browser.profile_index import extract_domain, normalize_site_hint

        assert extract_domain('https://www.linkedin.com/feed/') == 'www.linkedin.com'
        assert normalize_site_hint('linkedin.com') == 'linkedin.com'
        assert normalize_site_hint('LinkedIn.com:443') == 'linkedin.com'

    def test_managed_path_validation(self) -> None:
        from pydoll_mcp_server.tools.profile_tools import is_under

        root = Path('/managed/root')
        assert is_under(Path('/managed/root/sub/file'), root) is True
        assert is_under(Path('/outside/file'), root) is False


class TestProfileTools:
    def test_profile_list_returns_entries(self) -> None:
        import asyncio

        from pydoll_mcp_server.browser.profile_index import ProfileIndexEntry
        from pydoll_mcp_server.tools.profile_tools import profile_list

        with patch('pydoll_mcp_server.tools.profile_tools.get_profile_index') as mock_idx:
            mock_idx.return_value.list_all.return_value = [
                ProfileIndexEntry(
                    profile_id='prof_x',
                    owner_client_id='test',
                    mode='persistent',
                    created_at=1000,
                )
            ]
            result = asyncio.run(profile_list(client_id='test'))
            assert result.get('success') is True
            assert result.get('count') == 1

    def test_profile_promote_requires_temporary_source(self) -> None:
        import asyncio

        from pydoll_mcp_server.tools.profile_tools import profile_promote

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            result = asyncio.run(
                profile_promote(
                    source_profile_id='nonexistent',
                    target_profile_id='new_persistent',
                    client_id='test',
                )
            )
            assert result.get('success') is not True

    def test_profile_promote_refuses_overwrite(self) -> None:
        import asyncio
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp())
        target_dir = tmp_dir / 'existing'
        target_dir.mkdir()

        with patch.dict(os.environ, {'PYDOLL_MCP_AUTH_TOKEN': 'test-token'}):
            from pydoll_mcp_server.tools.profile_tools import profile_promote

            result = asyncio.run(
                profile_promote(
                    source_profile_id='src',
                    target_profile_id='target',
                    client_id='test',
                    overwrite=False,
                )
            )
            assert isinstance(result, dict)

    def test_profile_list_without_client_shows_all(self) -> None:
        import asyncio

        from pydoll_mcp_server.browser.profile_index import ProfileIndexEntry
        from pydoll_mcp_server.tools.profile_tools import profile_list

        with patch('pydoll_mcp_server.tools.profile_tools.get_profile_index') as mock_idx:
            mock_idx.return_value.list_all.return_value = [
                ProfileIndexEntry(
                    profile_id='prof_1',
                    owner_client_id='a',
                    mode='persistent',
                    created_at=1000,
                ),
                ProfileIndexEntry(
                    profile_id='prof_2',
                    owner_client_id='b',
                    mode='persistent',
                    created_at=2000,
                ),
            ]
            result = asyncio.run(profile_list(client_id=''))
            assert result.get('count') == 2


class TestBrowserLaunchIntent:
    def test_browser_launch_accepts_session_intent_params(self) -> None:
        import inspect

        from pydoll_mcp_server.tools.browser import browser_launch

        sig = inspect.signature(browser_launch)
        params = list(sig.parameters.keys())
        assert 'session_intent' in params
        assert 'site_hint' in params

    def test_ambiguous_profile_error_code_exists(self) -> None:
        from pydoll_mcp_server.errors import ErrorCode

        assert hasattr(ErrorCode, 'AMBIGUOUS_PROFILE')
        assert ErrorCode.AMBIGUOUS_PROFILE.value == 'AMBIGUOUS_PROFILE'

    def test_multi_persistent_candidates_are_json_array(self) -> None:
        import asyncio

        from pydoll_mcp_server.browser.profile_index import ProfileIndexEntry
        from pydoll_mcp_server.tools.browser import browser_launch

        entries = [
            ProfileIndexEntry(
                profile_id='prof_codex_linkedin_a',
                owner_client_id='codex',
                mode='persistent',
                created_at=1000,
                site_hints=['linkedin.com'],
            ),
            ProfileIndexEntry(
                profile_id='prof_codex_linkedin_b',
                owner_client_id='codex',
                mode='persistent',
                created_at=2000,
                site_hints=['linkedin.com'],
            ),
        ]
        with patch('pydoll_mcp_server.tools.browser.get_profile_index') as mock_index:
            mock_index.return_value.find_matching.return_value = entries
            result = asyncio.run(
                browser_launch(
                    client_id='codex',
                    headless=True,
                    session_intent='user_authenticated',
                    site_hint='linkedin.com',
                )
            )

        details = result.get('details', {})
        assert isinstance(details, dict)
        candidate_ids = details.get('candidate_profile_ids')
        assert candidate_ids == ['prof_codex_linkedin_a', 'prof_codex_linkedin_b']

    def test_temp_only_candidates_are_json_array(self) -> None:
        import asyncio

        from pydoll_mcp_server.browser.profile_index import ProfileIndexEntry
        from pydoll_mcp_server.tools.browser import browser_launch

        temp_entry = ProfileIndexEntry(
            profile_id='preserved_codex_profile_abc',
            owner_client_id='codex',
            mode='temporary',
            created_at=1000,
            site_hints=['linkedin.com'],
            path_kind='preserved_temporary',
        )
        with patch('pydoll_mcp_server.tools.browser.get_profile_index') as mock_index:
            mock_index.return_value.find_matching.side_effect = [[], [temp_entry]]
            result = asyncio.run(
                browser_launch(
                    client_id='codex',
                    headless=True,
                    session_intent='user_authenticated',
                    site_hint='linkedin.com',
                )
            )

        details = result.get('details', {})
        assert isinstance(details, dict)
        assert details.get('recommended_action') == 'profile_promote'
        candidate_ids = details.get('candidate_profile_ids')
        assert candidate_ids == ['preserved_codex_profile_abc']


class TestProfileMetadataSecurity:
    def test_profile_index_entry_no_secret_fields(self) -> None:
        from pydoll_mcp_server.browser.profile_index import ProfileIndexEntry

        entry = ProfileIndexEntry(
            profile_id='test',
            owner_client_id='c',
            mode='persistent',
            created_at=1000,
        )
        d = entry.to_dict()
        forbidden = {'cookies', 'tokens', 'storage', 'passwords', 'credentials', 'proxy'}
        for key in forbidden:
            assert key not in d, f'Sensitive key {key!r} found in profile index entry'

    def test_profile_list_response_has_no_secrets(self) -> None:
        import asyncio

        from pydoll_mcp_server.browser.profile_index import ProfileIndexEntry
        from pydoll_mcp_server.tools.profile_tools import profile_list

        with patch('pydoll_mcp_server.tools.profile_tools.get_profile_index') as mock_idx:
            mock_idx.return_value.list_all.return_value = [
                ProfileIndexEntry(
                    profile_id='prof_s',
                    owner_client_id='c',
                    mode='persistent',
                    created_at=1000,
                )
            ]
            result = asyncio.run(profile_list(client_id='c', include_site_hints=True))
            profiles = result.get('profiles', [])
            if isinstance(profiles, list) and profiles:
                entry = profiles[0]
                if isinstance(entry, dict):
                    forbidden = {'cookies', 'tokens', 'storage', 'passwords', 'path'}
                    for key in forbidden:
                        assert key not in entry, f'Sensitive key {key!r} found in profile_list'
