"""MCP server composition and transport entry points."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from pydoll_mcp_server.auth import BearerTokenBackend
from pydoll_mcp_server.server_state import (
    SCHEMA_VERSION,
    ServerState,
    error_response,
    generate_request_id,
    get_server_state,
)
from pydoll_mcp_server.tool_catalog import register_tools
from pydoll_mcp_server.tools.diagnostics import (
    browser_attach,
    diagnostics_snapshot,
    health_check,
    server_status,
    trace_cleanup,
    trace_get,
    trace_start,
    trace_stop,
)
from pydoll_mcp_server.version import get_version

mcp = FastMCP(
    'pydoll-mcp-server',
    instructions='Browser automation MCP server using Pydoll.',
    streamable_http_path='/',
    sse_path='/',
)
register_tools(mcp)
_server_state = get_server_state()


async def health_endpoint(request: Any) -> JSONResponse:
    return JSONResponse({
        'status': 'ok',
        'version': get_version(),
        'schema_version': SCHEMA_VERSION,
        'uptime_seconds': round(_server_state.uptime_seconds, 1),
    })


def create_app() -> Starlette:
    from pydoll_mcp_server.config import get_config

    config = get_config()
    config.ensure_directories()
    mcp_stream = mcp.streamable_http_app()
    session_manager = mcp.session_manager
    mcp_sse = mcp.sse_app()

    def auth_error(request: Any, exc: Exception) -> JSONResponse:
        return JSONResponse({'error': 'Authentication required. Provide Bearer token.'}, status_code=401)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    return Starlette(
        debug=False,
        middleware=[Middleware(AuthenticationMiddleware, backend=BearerTokenBackend(), on_error=auth_error)],
        routes=[
            Route('/health', health_endpoint, methods=['GET']),
            Mount('/mcp', app=mcp_stream),
            Mount('/sse', app=mcp_sse),
        ],
        lifespan=lifespan,
    )


__all__ = [
    'ServerState', 'browser_attach', 'create_app', 'diagnostics_snapshot', 'error_response',
    'generate_request_id', 'get_server_state', 'health_check', 'mcp', 'server_status',
    'trace_cleanup', 'trace_get', 'trace_start', 'trace_stop',
]
