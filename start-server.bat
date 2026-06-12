@echo off
setlocal

set "PYDOLL_MCP_AUTH_TOKEN=pydoll-dev-token"

echo ============================================
echo   Pydoll MCP Server
echo   http://127.0.0.1:8765
echo   Auth token: %PYDOLL_MCP_AUTH_TOKEN%
echo ============================================
echo.

python -m pydoll_mcp_server.cli %*

endlocal
