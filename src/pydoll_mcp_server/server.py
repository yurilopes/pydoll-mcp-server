"""MCP server entry point using FastMCP and Starlette."""

from __future__ import annotations

import time
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from pydoll_mcp_server.auth import BearerTokenBackend
from pydoll_mcp_server.errors import StructuredError

_start_time = time.time()


class ServerState:
    def __init__(self) -> None:
        self._tool_counts: dict[str, int] = {}
        self._failure_counts: dict[str, int] = {}
        self._timeouts: int = 0
        self._tab_unhealthy: int = 0
        self._recoveries: int = 0

    def record_tool(self, tool_name: str) -> None:
        self._tool_counts[tool_name] = self._tool_counts.get(tool_name, 0) + 1

    def record_failure(self, error_code: str) -> None:
        self._failure_counts[error_code] = self._failure_counts.get(error_code, 0) + 1

    def record_timeout(self) -> None:
        self._timeouts += 1

    def record_unhealthy_tab(self) -> None:
        self._tab_unhealthy += 1

    def record_recovery(self) -> None:
        self._recoveries += 1

    @property
    def uptime_seconds(self) -> float:
        return time.time() - _start_time

    def summary(self) -> dict[str, Any]:
        return {
            'uptime_seconds': round(self.uptime_seconds, 1),
            'tool_calls': dict(self._tool_counts),
            'failures': dict(self._failure_counts),
            'timeouts': self._timeouts,
            'unhealthy_tabs': self._tab_unhealthy,
            'recoveries': self._recoveries,
        }


_server_state = ServerState()

mcp = FastMCP(
    'pydoll-mcp-server',
    instructions='Browser automation MCP server using Pydoll.',
    streamable_http_path='/',
    sse_path='/',
)


def generate_request_id() -> str:
    return uuid.uuid4().hex[:12]


def error_response(error: StructuredError) -> dict[str, Any]:
    _server_state.record_failure(error.error_code.value)
    return {'success': False, **error.to_dict()}


@mcp.tool()
def health_check(include_runtime: bool = False) -> dict[str, Any]:
    from pydoll_mcp_server.config import get_config
    config = get_config()
    result: dict[str, Any] = {
        'status': 'ok',
        'version': '0.1.0',
        'uptime_seconds': round(_server_state.uptime_seconds, 1),
        'auth_mode': 'token' if config.auth_enabled else 'none',
    }
    if include_runtime:
        result['runtime'] = _server_state.summary()
    return result


@mcp.tool()
def server_status(
    client_id: str = 'anonymous',
    include_clients: bool = False,
) -> dict[str, Any]:
    from pydoll_mcp_server.browser.registry import get_registry
    from pydoll_mcp_server.config import get_config

    registry = get_registry()
    config = get_config()
    result: dict[str, Any] = {
        'status': 'ok',
        'version': '0.1.0',
        'uptime_seconds': round(_server_state.uptime_seconds, 1),
        'auth_mode': 'token' if config.auth_enabled else 'none',
    }
    try:
        browsers = registry.list_browsers(client_id)
        result['browsers'] = [b.summary() for b in browsers]
        tabs = registry.list_tabs(client_id)
        result['tabs'] = len(tabs)
    except Exception as e:
        result['browsers_error'] = str(e)
    if include_clients:
        result['clients'] = registry.list_clients()
    result['resources'] = _server_state.summary()
    return result


@mcp.tool()
async def browser_launch(
    client_id: str,
    headless: bool = False,
    profile_mode: str = 'persistent',
    profile_id: str = '',
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.browser import browser_launch as impl
    return await impl(client_id, headless, profile_mode, profile_id)


@mcp.tool()
async def browser_list(client_id: str) -> dict[str, Any]:
    from pydoll_mcp_server.tools.browser import browser_list as impl
    return await impl(client_id)


@mcp.tool()
async def browser_close(
    client_id: str,
    browser_id: str,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.browser import browser_close as impl
    return await impl(client_id, browser_id)


@mcp.tool()
async def tab_list(
    client_id: str,
    browser_id: str = '',
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.tabs import tab_list as impl
    return await impl(client_id, browser_id)


@mcp.tool()
async def tab_activate(
    client_id: str,
    tab_id: str,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.tabs import tab_activate as impl
    return await impl(client_id, tab_id)


@mcp.tool()
async def tab_close(
    client_id: str,
    tab_id: str,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.tabs import tab_close as impl
    return await impl(client_id, tab_id)


@mcp.tool()
async def tab_recover(
    client_id: str,
    tab_id: str,
    mode: str = 'reload',
    force: bool = False,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.tabs import tab_recover as impl
    return await impl(client_id, tab_id, mode, force)


@mcp.tool()
async def page_goto(
    client_id: str,
    tab_id: str,
    url: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.page import page_goto as impl
    return await impl(client_id, tab_id, url, timeout)


@mcp.tool()
async def page_reload(
    client_id: str,
    tab_id: str,
    ignore_cache: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.page import page_reload as impl
    return await impl(client_id, tab_id, ignore_cache, timeout)


@mcp.tool()
async def page_back(
    client_id: str,
    tab_id: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.page import page_back as impl
    return await impl(client_id, tab_id, timeout)


@mcp.tool()
async def page_forward(
    client_id: str,
    tab_id: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.page import page_forward as impl
    return await impl(client_id, tab_id, timeout)


@mcp.tool()
async def page_wait(
    client_id: str,
    tab_id: str,
    state: str = 'load',
    selector: str = '',
    text: str = '',
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.page import page_wait as impl
    return await impl(client_id, tab_id, state, selector, text, timeout)


@mcp.tool()
async def page_get_text(
    client_id: str,
    tab_id: str,
    max_chars: int = 20000,
) -> dict[str, Any]:
    from pydoll_mcp_server.dom.tree import page_get_text as impl
    return await impl(client_id, tab_id, max_chars)


@mcp.tool()
async def page_get_tree(
    client_id: str,
    tab_id: str,
    max_depth: int = 6,
    max_nodes: int = 300,
) -> dict[str, Any]:
    from pydoll_mcp_server.dom.tree import build_page_tree as impl
    return await impl(client_id, tab_id, max_depth, max_nodes)


@mcp.tool()
async def page_screenshot(
    client_id: str,
    tab_id: str,
    fmt: str = 'png',
    full_page: bool = False,
    as_base64: bool = True,
    path: str = '',
) -> dict[str, Any]:
    from pydoll_mcp_server.dom.tree import page_screenshot as impl
    return await impl(client_id, tab_id, fmt, full_page, as_base64, path)


@mcp.tool()
async def page_get_tree_deep(
    client_id: str,
    tab_id: str,
    max_depth: int = 10,
    max_nodes: int = 1000,
    timeout: float | None = None,
    include_shadow: bool = True,
    include_iframes: bool = True,
) -> dict[str, Any]:
    from pydoll_mcp_server.dom.deep_traversal import page_get_tree_deep as impl
    return await impl(
        client_id, tab_id, max_depth, max_nodes, timeout,
        include_shadow, include_iframes,
    )


@mcp.tool()
async def element_find(
    client_id: str,
    tab_id: str,
    selector: str,
    strategy: str = 'css',
    timeout: float | None = None,
    find_all: bool = False,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.elements import element_find as impl
    return await impl(client_id, tab_id, selector, strategy, timeout, find_all)


@mcp.tool()
async def element_find_deep(
    client_id: str,
    tab_id: str,
    selector: str,
    strategy: str = 'css',
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.dom.deep_traversal import element_find_deep as impl
    return await impl(client_id, tab_id, selector, strategy, timeout)


@mcp.tool()
async def element_click(
    client_id: str,
    tab_id: str,
    element_id: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.elements import element_click as impl
    return await impl(client_id, tab_id, element_id, timeout)


@mcp.tool()
async def element_type(
    client_id: str,
    tab_id: str,
    element_id: str,
    text: str,
    delay: float = 0.0,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.elements import element_type as impl
    return await impl(client_id, tab_id, element_id, text, delay)


@mcp.tool()
async def element_fill(
    client_id: str,
    tab_id: str,
    element_id: str,
    value: str,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.elements import element_fill as impl
    return await impl(client_id, tab_id, element_id, value)


@mcp.tool()
async def element_get_text(
    client_id: str,
    tab_id: str,
    element_id: str,
    max_chars: int = 5000,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.elements import element_get_text as impl
    return await impl(client_id, tab_id, element_id, max_chars)


@mcp.tool()
async def element_get_attribute(
    client_id: str,
    tab_id: str,
    element_id: str,
    name: str,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.elements import element_get_attribute as impl
    return await impl(client_id, tab_id, element_id, name)


@mcp.tool()
async def element_screenshot(
    client_id: str,
    tab_id: str,
    element_id: str,
    path: str = '',
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.elements import element_screenshot as impl
    return await impl(client_id, tab_id, element_id, path)


@mcp.tool()
async def js_evaluate_readonly(
    client_id: str,
    tab_id: str,
    script: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.javascript import js_evaluate_readonly as impl
    return await impl(client_id, tab_id, script, timeout)


@mcp.tool()
async def js_evaluate(
    client_id: str,
    tab_id: str,
    script: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.javascript import js_evaluate as impl
    return await impl(client_id, tab_id, script, timeout)


@mcp.tool()
async def user_agent_set(
    client_id: str,
    tab_id: str = '',
    browser_id: str = '',
    user_agent: str = '',
) -> dict[str, Any]:
    from pydoll_mcp_server.browser.cdp_helpers import set_user_agent as impl
    return await impl(client_id, tab_id, browser_id, user_agent)


@mcp.tool()
async def viewport_set(
    client_id: str,
    tab_id: str,
    width: int,
    height: int,
    scale: float = 1.0,
) -> dict[str, Any]:
    from pydoll_mcp_server.browser.cdp_helpers import set_viewport as impl
    return await impl(client_id, tab_id, width, height, scale)


@mcp.tool()
async def cookies_get(
    client_id: str,
    browser_id: str = '',
    tab_id: str = '',
    url_filter: str = '',
    redact_values: bool = True,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.storage import cookies_get as impl
    return await impl(client_id, browser_id, tab_id, url_filter, redact_values)


@mcp.tool()
async def cookies_set(
    client_id: str,
    browser_id: str = '',
    tab_id: str = '',
    cookies: list[dict] | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.storage import cookies_set as impl
    return await impl(client_id, browser_id, tab_id, cookies)


@mcp.tool()
async def storage_get(
    client_id: str,
    tab_id: str,
    origin: str = '',
    keys: list[str] | None = None,
    redact_values: bool = True,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.storage import storage_get as impl
    return await impl(client_id, tab_id, origin, keys, redact_values)


@mcp.tool()
async def storage_set(
    client_id: str,
    tab_id: str,
    origin: str = '',
    items: list[dict] | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.storage import storage_set as impl
    return await impl(client_id, tab_id, origin, items)


@mcp.tool()
async def download_expect(
    client_id: str,
    tab_id: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.files import download_expect as impl
    return await impl(client_id, tab_id, timeout)


@mcp.tool()
async def upload_files(
    client_id: str,
    tab_id: str,
    element_id: str,
    paths: list[str],
) -> dict[str, Any]:
    from pydoll_mcp_server.tools.files import upload_files as impl
    return await impl(client_id, tab_id, element_id, paths)


async def health_endpoint(request: Any) -> JSONResponse:
    return JSONResponse({
        'status': 'ok',
        'version': '0.1.0',
        'uptime_seconds': round(_server_state.uptime_seconds, 1),
    })


def create_app() -> Starlette:
    from pydoll_mcp_server.config import get_config

    config = get_config()
    config.ensure_directories()

    mcp_stream = mcp.streamable_http_app()
    mcp_sse = mcp.sse_app()

    def auth_error(request: Any, exc: Exception) -> JSONResponse:
        return JSONResponse(
            {'error': 'Authentication required. Provide Bearer token.'},
            status_code=401,
        )

    routes: list = [
        Route('/health', health_endpoint, methods=['GET']),
        Mount('/mcp', app=mcp_stream),
        Mount('/sse', app=mcp_sse),
    ]

    app = Starlette(
        debug=False,
        middleware=[
            Middleware(
                AuthenticationMiddleware,
                backend=BearerTokenBackend(),
                on_error=auth_error,
            ),
        ],
        routes=routes,
    )

    return app


def get_server_state() -> ServerState:
    return _server_state
