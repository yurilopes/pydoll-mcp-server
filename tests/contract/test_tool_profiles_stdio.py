"""MCP stdio handshake contracts for curated tool profiles."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

from pydoll_mcp_server.json_types import get_array, require_json_object

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_stdio_handshake_exposes_selected_profiles(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    expected_counts = {'full': 144, 'agent': 63, 'linkedin': 78}

    for profile, expected_count in expected_counts.items():
        environment = dict(os.environ)
        environment.update(
            {
                'PYTHONIOENCODING': 'utf-8',
                'PYDOLL_MCP_TRANSPORT': 'stdio',
                'PYDOLL_MCP_ALLOW_NO_AUTH': 'true',
                'PYDOLL_MCP_RUNTIME_DIR': str(tmp_path / profile),
                'PYTHONPATH': str(root / 'src'),
            }
        )
        parameters = StdioServerParameters(
            command=sys.executable,
            args=['-m', 'pydoll_mcp_server.cli', '--transport', 'stdio', '--tool-profile', profile],
            env=environment,
            cwd=root,
            encoding='utf-8',
            encoding_error_handler='strict',
        )

        async with (
            stdio_client(parameters) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            catalog = await session.list_tools()
            names = {tool.name for tool in catalog.tools}
            assert len(names) == expected_count
            assert all(tool.title for tool in catalog.tools)
            assert all(tool.description for tool in catalog.tools)

            status_result = await session.call_tool(
                'server_status',
                {'client_id': f'profile-{profile}', 'include_tool_names': True},
            )
            assert status_result.isError is not True
            assert len(status_result.content) == 1
            content = status_result.content[0]
            assert isinstance(content, TextContent)
            status = require_json_object(json.loads(content.text), 'server status')
            assert status['tool_profile'] == profile
            assert status['exposed_tool_count'] == expected_count
            status_names = {str(name) for name in get_array(status, 'tool_names', [])}
            assert status_names == names
