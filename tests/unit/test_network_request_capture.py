"""Request capture contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pydoll_mcp_server.browser.inspection import InspectionManager
from pydoll_mcp_server.json_types import JsonObject, get_array, get_bool, get_int, get_string
from pydoll_mcp_server.tools.network import capture_network_event, network_get_request

pytestmark = pytest.mark.unit


class FakeTab:
    async def get_network_response_body(self, request_id: str) -> str:
        return request_id


class FakeTabInfo:
    def __init__(self) -> None:
        self.pydoll_tab = FakeTab()


class FakeRegistry:
    def get_tab(self, client_id: str, tab_id: str) -> FakeTabInfo:
        if client_id != 'owner' or tab_id != 'tab-1':
            raise AssertionError('unexpected ownership lookup')
        return FakeTabInfo()


def request_event(post_data: str | None, content_type: str) -> JsonObject:
    request: JsonObject = {
        'url': 'https://example.test/submit?raw=a%2Bb',
        'method': 'POST',
        'headers': {'Content-Type': content_type, 'Authorization': 'Bearer raw-secret'},
        'hasPostData': post_data is not None,
    }
    if post_data is not None:
        request['postData'] = post_data
    return {
        'method': 'Network.requestWillBeSent',
        'params': {
            'requestId': 'req-1',
            'request': request,
            'documentURL': 'https://example.test/form',
            'type': 'Document',
            'timestamp': 1.0,
            'wallTime': 2.0,
            'initiator': {'type': 'script'},
        },
    }


@pytest.mark.asyncio
async def test_form_payload_and_sensitive_headers_are_preserved() -> None:
    manager = InspectionManager()
    with (
        patch('pydoll_mcp_server.tools.network.get_inspection_manager', return_value=manager),
        patch('pydoll_mcp_server.tools.network.get_registry', return_value=FakeRegistry()),
    ):
        await capture_network_event(
            'tab-1',
            request_event('instalacao=4002229168&tag=a&tag=b&encoded=a%2Bb', 'application/x-www-form-urlencoded'),
        )
        result = await network_get_request('owner', 'tab-1', 'req-1')

    assert get_string(result, 'post_data') == 'instalacao=4002229168&tag=a&tag=b&encoded=a%2Bb'
    assert get_string(result, 'url').endswith('raw=a%2Bb')
    assert result['headers'] == {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': 'Bearer raw-secret',
    }
    fields = get_array(result, 'form_fields')
    assert [field for field in fields if isinstance(field, dict) and field.get('name') == 'tag'] == [
        {'name': 'tag', 'value': 'a'},
        {'name': 'tag', 'value': 'b'},
    ]


@pytest.mark.asyncio
async def test_json_raw_is_preserved_and_parsed() -> None:
    manager = InspectionManager()
    raw = '{"message":"olá","value":1}'
    with (
        patch('pydoll_mcp_server.tools.network.get_inspection_manager', return_value=manager),
        patch('pydoll_mcp_server.tools.network.get_registry', return_value=FakeRegistry()),
    ):
        await capture_network_event('tab-1', request_event(raw, 'application/json'))
        result = await network_get_request('owner', 'tab-1', 'req-1')
    assert get_string(result, 'post_data') == raw
    assert result['json_value'] == {'message': 'olá', 'value': 1}


@pytest.mark.asyncio
async def test_missing_payload_is_explicit() -> None:
    manager = InspectionManager()
    with (
        patch('pydoll_mcp_server.tools.network.get_inspection_manager', return_value=manager),
        patch('pydoll_mcp_server.tools.network.get_registry', return_value=FakeRegistry()),
    ):
        await capture_network_event('tab-1', request_event(None, 'text/plain'))
        result = await network_get_request('owner', 'tab-1', 'req-1')
    assert get_bool(result, 'has_post_data') is False
    assert result['post_data'] is None
    assert get_int(result, 'payload_size_bytes') == 0


@pytest.mark.asyncio
async def test_utf8_truncation_reports_both_sizes() -> None:
    manager = InspectionManager()
    with (
        patch('pydoll_mcp_server.tools.network.get_inspection_manager', return_value=manager),
        patch('pydoll_mcp_server.tools.network.get_registry', return_value=FakeRegistry()),
    ):
        await capture_network_event('tab-1', request_event('áéí', 'text/plain'))
        result = await network_get_request('owner', 'tab-1', 'req-1', max_bytes=5)
    assert get_string(result, 'post_data') == 'áé'
    assert get_bool(result, 'truncated') is True
    assert get_int(result, 'payload_size_bytes') == 6
    assert get_int(result, 'returned_size_bytes') == 4
