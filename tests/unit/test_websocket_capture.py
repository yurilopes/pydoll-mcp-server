"""WebSocket capture contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pydoll_mcp_server.browser.inspection import InspectionManager
from pydoll_mcp_server.json_types import get_array, get_bool, get_int, get_string
from pydoll_mcp_server.tools.websocket import (
    capture_websocket_event,
    websocket_frames_list,
    websocket_get,
    websocket_list,
)

pytestmark = pytest.mark.unit


class FakeTabInfo:
    pass


class FakeRegistry:
    def get_tab(self, client_id: str, tab_id: str) -> FakeTabInfo:
        if client_id != 'owner' or tab_id != 'tab-1':
            raise AssertionError('unexpected ownership lookup')
        return FakeTabInfo()


@pytest.mark.asyncio
async def test_websocket_connection_and_frames_are_captured() -> None:
    manager = InspectionManager()
    with (
        patch('pydoll_mcp_server.tools.websocket.get_inspection_manager', return_value=manager),
        patch('pydoll_mcp_server.tools.websocket.get_registry', return_value=FakeRegistry()),
    ):
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketCreated',
                'params': {
                    'requestId': 'ws-1',
                    'url': 'wss://example.test/socket?token=raw-secret',
                    'initiator': {'type': 'script'},
                    'timestamp': 1.0,
                },
            },
        )
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketWillSendHandshakeRequest',
                'params': {
                    'requestId': 'ws-1',
                    'timestamp': 2.0,
                    'wallTime': 3.0,
                    'request': {
                        'headers': {
                            'Host': 'example.test',
                            'Authorization': 'Bearer raw-secret',
                        }
                    },
                },
            },
        )
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketHandshakeResponseReceived',
                'params': {
                    'requestId': 'ws-1',
                    'timestamp': 4.0,
                    'response': {'status': 101, 'headers': {'Set-Cookie': 'session=raw-secret'}},
                },
            },
        )
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketFrameSent',
                'params': {
                    'requestId': 'ws-1',
                    'timestamp': 5.0,
                    'response': {'opcode': 1, 'mask': True, 'payloadData': '{"access_token":"raw-secret"}'},
                },
            },
        )
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketFrameReceived',
                'params': {
                    'requestId': 'ws-1',
                    'timestamp': 6.0,
                    'response': {'opcode': 1, 'mask': False, 'payloadData': '{"ok":true}'},
                },
            },
        )

        listed = await websocket_list('owner', 'tab-1')
        detail = await websocket_get('owner', 'tab-1', 'ws-1')
        frames = await websocket_frames_list('owner', 'tab-1', request_id='ws-1')

    connections = get_array(listed, 'connections')
    assert len(connections) == 1
    connection = connections[0]
    assert isinstance(connection, dict)
    assert get_string(connection, 'url') == 'wss://example.test/socket?token=REDACTED'
    assert get_int(connection, 'status') == 101
    assert get_int(connection, 'frame_count') == 2

    handshake_request = detail['handshake_request']
    assert isinstance(handshake_request, dict)
    headers = handshake_request['headers']
    assert isinstance(headers, dict)
    assert headers['Authorization'] == '[REDACTED]'

    detail_frames = get_array(detail, 'frames')
    assert len(detail_frames) == 2
    first_frame = detail_frames[0]
    assert isinstance(first_frame, dict)
    assert get_string(first_frame, 'payload_data') == '{"access_token":"[REDACTED]"}'
    assert get_bool(first_frame, 'base64_encoded') is False

    listed_frames = get_array(frames, 'frames')
    assert len(listed_frames) == 2


@pytest.mark.asyncio
async def test_websocket_frame_listing_filters_and_truncates_return_payload() -> None:
    manager = InspectionManager()
    with (
        patch('pydoll_mcp_server.tools.websocket.get_inspection_manager', return_value=manager),
        patch('pydoll_mcp_server.tools.websocket.get_registry', return_value=FakeRegistry()),
    ):
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketCreated',
                'params': {'requestId': 'ws-1', 'url': 'wss://example.test/socket', 'timestamp': 1.0},
            },
        )
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketFrameReceived',
                'params': {
                    'requestId': 'ws-1',
                    'timestamp': 2.0,
                    'response': {'opcode': 1, 'mask': False, 'payloadData': 'olá mundo'},
                },
            },
        )
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketFrameSent',
                'params': {
                    'requestId': 'ws-1',
                    'timestamp': 3.0,
                    'response': {'opcode': 2, 'mask': True, 'payloadData': 'YWJj'},
                },
            },
        )

        frames = await websocket_frames_list(
            'owner',
            'tab-1',
            direction='received',
            filter_payload='mundo',
            max_payload_bytes=4,
        )

    selected = get_array(frames, 'frames')
    assert len(selected) == 1
    frame = selected[0]
    assert isinstance(frame, dict)
    assert get_string(frame, 'direction') == 'received'
    assert get_string(frame, 'payload_data') == 'olá'
    assert get_bool(frame, 'return_truncated') is True
    assert get_int(frame, 'return_original_size_bytes') == len('olá mundo'.encode())


@pytest.mark.asyncio
async def test_websocket_get_can_return_unredacted_handshake_and_payload() -> None:
    manager = InspectionManager()
    with (
        patch('pydoll_mcp_server.tools.websocket.get_inspection_manager', return_value=manager),
        patch('pydoll_mcp_server.tools.websocket.get_registry', return_value=FakeRegistry()),
    ):
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketCreated',
                'params': {'requestId': 'ws-1', 'url': 'wss://example.test/socket?token=raw-secret'},
            },
        )
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketWillSendHandshakeRequest',
                'params': {
                    'requestId': 'ws-1',
                    'request': {'headers': {'Cookie': 'session=raw-secret'}},
                },
            },
        )
        await capture_websocket_event(
            'tab-1',
            {
                'method': 'Network.webSocketFrameSent',
                'params': {
                    'requestId': 'ws-1',
                    'response': {'opcode': 1, 'mask': True, 'payloadData': '{"token":"raw-secret"}'},
                },
            },
        )

        detail = await websocket_get('owner', 'tab-1', 'ws-1', redact=False)

    assert get_string(detail, 'url') == 'wss://example.test/socket?token=raw-secret'
    handshake_request = detail['handshake_request']
    assert isinstance(handshake_request, dict)
    headers = handshake_request['headers']
    assert isinstance(headers, dict)
    assert headers['Cookie'] == 'session=raw-secret'
    frames = get_array(detail, 'frames')
    frame = frames[0]
    assert isinstance(frame, dict)
    assert get_string(frame, 'payload_data') == '{"token":"raw-secret"}'
