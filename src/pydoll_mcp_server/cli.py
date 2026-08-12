"""CLI entry point for the MCP server."""

from __future__ import annotations

import argparse
import os

import uvicorn

from pydoll_mcp_server.tool_metadata import ToolProfile


def main() -> None:
    parser = argparse.ArgumentParser(description='Pydoll MCP Server - Browser automation via MCP')
    parser.add_argument(
        '--transport',
        default=os.environ.get('PYDOLL_MCP_TRANSPORT', 'http'),
        choices=['http', 'stdio'],
        help='Transport mode: http (default) or stdio',
    )
    parser.add_argument(
        '--host',
        default=os.environ.get('PYDOLL_MCP_HOST', '127.0.0.1'),
        help='Host to bind to (http transport only)',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.environ.get('PYDOLL_MCP_PORT', '8765')),
        help='Port to listen on (http transport only)',
    )
    parser.add_argument(
        '--log-level',
        default=os.environ.get('PYDOLL_MCP_LOG_LEVEL', 'info'),
        choices=['debug', 'info', 'warning', 'error'],
        help='Logging level',
    )
    parser.add_argument(
        '--tool-profile',
        default=os.environ.get('PYDOLL_MCP_TOOL_PROFILE', ToolProfile.FULL.value),
        choices=[profile.value for profile in ToolProfile],
        help='Tool exposure profile: full, agent, or linkedin',
    )
    args = parser.parse_args()

    os.environ['PYDOLL_MCP_TOOL_PROFILE'] = args.tool_profile
    previous_transport = os.environ.get('PYDOLL_MCP_TRANSPORT')
    os.environ['PYDOLL_MCP_TRANSPORT'] = args.transport
    os.environ['PYDOLL_MCP_HOST'] = args.host

    from pydoll_mcp_server.logging import get_logger

    logger = get_logger()
    logger.set_level(args.log_level)

    if args.transport == 'stdio':
        logger.info(f'Starting Pydoll MCP Server via stdio with tool profile {args.tool_profile}')
        try:
            run_stdio()
        finally:
            if previous_transport is None:
                os.environ.pop('PYDOLL_MCP_TRANSPORT', None)
            else:
                os.environ['PYDOLL_MCP_TRANSPORT'] = previous_transport
        return

    from pydoll_mcp_server.config import get_config

    config = get_config()
    if config.auth_enabled:
        logger.info('Authentication enabled (bearer token required)')
    else:
        logger.warning('Authentication disabled - development mode only')

    config.ensure_directories()
    logger.info(f'Runtime directory: {config.runtime_dir}')

    app_path = 'pydoll_mcp_server.server:create_app'

    logger.info(f'Starting Pydoll MCP Server on {args.host}:{args.port} with tool profile {args.tool_profile}')
    uvicorn.run(
        f'{app_path}',
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        factory=True,
    )


def run_stdio() -> None:
    import asyncio

    from pydoll_mcp_server.server import mcp
    from pydoll_mcp_server.tools.browser import shutdown_browsers

    try:
        mcp.run(transport='stdio')
    finally:
        asyncio.run(shutdown_browsers())


_run_stdio = run_stdio


if __name__ == '__main__':
    main()
