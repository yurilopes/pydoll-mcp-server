"""Unit tests for LinkedIn Jobs search tools."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pydoll_mcp_server.json_types import JsonObject

pytestmark = [pytest.mark.unit]


def _script_result(value: JsonObject) -> JsonObject:
    return {'result': {'result': {'value': value}}}


class TestLinkedInSearch:
    def test_search_url_includes_remote_easy_apply_and_location(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_search_url

        url = linkedin_jobs_search_url(
            keywords='Full Stack Developer',
            location='United States',
            remote=True,
            easy_apply=True,
            sort_by='recent',
        )

        assert url.startswith('https://www.linkedin.com/jobs/search/?')
        assert 'keywords=Full+Stack+Developer' in url
        assert 'location=United+States' in url
        assert 'f_WT=2' in url
        assert 'f_AL=true' in url
        assert 'sortBy=R' in url

    def test_search_url_includes_expanded_filters(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_search_url

        url = linkedin_jobs_search_url(
            keywords='AI Engineer',
            location='United States',
            date_posted='past_week',
            experience_levels=['mid_senior', 'director'],
            job_types=['full_time', 'contract'],
            geo_id='103644278',
            start=25,
        )

        assert 'f_TPR=r604800' in url
        assert 'f_E=4%2C5' in url
        assert 'f_JT=F%2CC' in url
        assert 'geoId=103644278' in url
        assert 'start=25' in url

    def test_search_navigates_then_returns_results(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_search

        with (
            patch(
                'pydoll_mcp_server.tools.linkedin_search.page_goto',
                new=AsyncMock(return_value={'success': True, 'url': 'https://www.linkedin.com/jobs/search/'}),
            ) as goto,
            patch(
                'pydoll_mcp_server.tools.linkedin_search.linkedin_jobs_search_results',
                new=AsyncMock(return_value={'success': True, 'results': [], 'count': 0, 'no_results': True}),
            ) as results,
        ):
            response = asyncio.run(
                linkedin_jobs_search(
                    'client',
                    'tab',
                    keywords='Python Developer',
                    location='Brazil',
                )
            )

        assert response['success'] is True
        assert response['count'] == 0
        assert 'search_url' in response
        goto.assert_awaited_once()
        results.assert_awaited_once_with('client', 'tab', max_results=25)

    def test_search_waits_for_hydrated_results(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_search

        responses: list[JsonObject] = [
            {'success': True, 'results': [], 'count': 0, 'no_results': False},
            {'success': True, 'results': [{'linkedin_job_id': '123'}], 'count': 1, 'no_results': False},
        ]
        with (
            patch(
                'pydoll_mcp_server.tools.linkedin_search.page_goto',
                new=AsyncMock(return_value={'success': True, 'url': 'https://www.linkedin.com/jobs/search/'}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_search.linkedin_jobs_search_results',
                new=AsyncMock(side_effect=responses),
            ) as results,
        ):
            response = asyncio.run(
                linkedin_jobs_search(
                    'client',
                    'tab',
                    keywords='Python Developer',
                    location='Brazil',
                    timeout_ms=1000,
                )
            )

        assert response['count'] == 1
        assert results.await_count == 2

    def test_search_results_extracts_compact_payload(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_search_results

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value=_script_result(
                {
                    'success': True,
                    'url': 'https://www.linkedin.com/jobs/search/?keywords=Python&location=Brazil&f_WT=2&f_AL=true',
                    'keywords': 'Python',
                    'location': 'Brazil',
                    'filters': {'remote': True, 'easy_apply': True, 'sort_by': 'relevance'},
                    'results': [
                        {
                            'linkedin_job_id': '123',
                            'title': 'Python Developer',
                            'company': 'Example Inc',
                            'location': 'Brazil Remote',
                            'url': 'https://www.linkedin.com/jobs/view/123/',
                            'easy_apply_hint': True,
                            'remote_hint': True,
                        }
                    ],
                    'count': 1,
                    'partial': False,
                    'no_results': False,
                }
            )
        )
        with patch('pydoll_mcp_server.tools.linkedin_search.get_registry') as registry:
            tab_info = MagicMock()
            tab_info.pydoll_tab = mock_tab
            registry.return_value.get_tab.return_value = tab_info

            result = asyncio.run(linkedin_jobs_search_results('client', 'tab', max_results=10))

        assert result['success'] is True
        assert result['count'] == 1
        results_value = result['results']
        assert isinstance(results_value, list)
        first = results_value[0]
        assert isinstance(first, dict)
        assert first['easy_apply_hint'] is True

    def test_open_result_requires_exactly_one_target(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_open_result

        missing = asyncio.run(linkedin_jobs_open_result('client', 'tab'))
        both = asyncio.run(linkedin_jobs_open_result('client', 'tab', linkedin_job_id='123', index=0))

        assert missing['error_code'] == 'INVALID_INPUT'
        assert both['error_code'] == 'INVALID_INPUT'

    def test_open_result_clicks_visible_card_and_returns_snapshot(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_open_result

        with (
            patch(
                'pydoll_mcp_server.tools.linkedin_search.linkedin_jobs_search_results',
                new=AsyncMock(
                    return_value={
                        'success': True,
                        'results': [{'linkedin_job_id': '123', 'title': 'Python Developer'}],
                    }
                ),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_search._execute_search_script',
                new=AsyncMock(return_value={'success': True, 'card': {'selector_hint': '#job-card'}}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_search.element_find',
                new=AsyncMock(return_value={'success': True, 'element_id': 'el_job'}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_search.element_click',
                new=AsyncMock(return_value={'success': True, 'clicked': True}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_search._wait_for_opened_job',
                new=AsyncMock(
                    return_value={
                        'success': True,
                        'linkedin_job_id': '123',
                        'detail_panel_present': True,
                    }
                ),
            ),
        ):
            result = asyncio.run(linkedin_jobs_open_result('client', 'tab', linkedin_job_id='123', timeout_ms=1000))

        assert result['success'] is True
        assert result['opened_from_result'] is True

    def test_open_result_falls_back_to_direct_navigation(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_open_result

        with (
            patch(
                'pydoll_mcp_server.tools.linkedin_search.linkedin_jobs_search_results',
                new=AsyncMock(
                    return_value={
                        'success': True,
                        'results': [{'linkedin_job_id': '123', 'title': 'Python Developer'}],
                    }
                ),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_search._execute_search_script',
                new=AsyncMock(return_value={'success': True}),
            ),
            patch(
                'pydoll_mcp_server.tools.linkedin_search.page_goto',
                new=AsyncMock(return_value={'success': True, 'url': 'https://www.linkedin.com/jobs/view/123/'}),
            ) as goto,
            patch(
                'pydoll_mcp_server.tools.linkedin_search.linkedin_job_snapshot',
                new=AsyncMock(return_value={'success': True, 'linkedin_job_id': '123'}),
            ),
        ):
            result = asyncio.run(linkedin_jobs_open_result('client', 'tab', index=0, timeout_ms=1000))

        assert result['fallback_navigation'] is True
        goto.assert_awaited_once()

    def test_page_snapshot_returns_list_and_detail(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_jobs_page_snapshot

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value=_script_result(
                {
                    'success': True,
                    'results': [{'linkedin_job_id': '123'}],
                    'count': 1,
                    'selected_job_id': '123',
                    'detail_job_snapshot': {'linkedin_job_id': '123', 'application_state': 'not_started'},
                    'detail_panel_present': True,
                    'easy_apply_button_state': 'easy_apply',
                    'detail_url': 'https://www.linkedin.com/jobs/view/123/',
                    'list_count': 1,
                    'has_next_page': True,
                }
            )
        )
        with patch('pydoll_mcp_server.tools.linkedin_search.get_registry') as registry:
            tab_info = MagicMock()
            tab_info.pydoll_tab = mock_tab
            registry.return_value.get_tab.return_value = tab_info

            result = asyncio.run(linkedin_jobs_page_snapshot('client', 'tab'))

        assert result['selected_job_id'] == '123'
        assert result['detail_panel_present'] is True
        assert result['has_next_page'] is True

    def test_application_evidence_returns_compact_payload(self) -> None:
        from pydoll_mcp_server.tools.linkedin_search import linkedin_application_evidence

        mock_tab = MagicMock()
        mock_tab.execute_script = AsyncMock(
            return_value=_script_result(
                {
                    'success': True,
                    'platform': 'linkedin',
                    'linkedin_job_id': '123',
                    'canonical_url': 'https://www.linkedin.com/jobs/view/123/',
                    'company': 'Example Inc',
                    'role': 'Python Developer',
                    'location': 'Brazil Remote',
                    'application_state': 'submitted',
                    'easy_apply_available': True,
                    'authorization_risk': False,
                    'risk_text': '',
                    'resume_filename': 'resume.pdf',
                    'answers': [{'question': 'Can work?', 'answer': 'Yes'}],
                    'confirmation_text': 'Candidatura enviada',
                    'captured_at_unix': 1783430000,
                }
            )
        )
        with patch('pydoll_mcp_server.tools.linkedin_search.get_registry') as registry:
            tab_info = MagicMock()
            tab_info.pydoll_tab = mock_tab
            registry.return_value.get_tab.return_value = tab_info

            result = asyncio.run(linkedin_application_evidence('client', 'tab'))

        assert result['platform'] == 'linkedin'
        assert result['application_state'] == 'submitted'
        assert result['resume_filename'] == 'resume.pdf'
