@echo off
setlocal

set "PYDOLL_MCP_AUTH_TOKEN=pydoll-dev-token"

echo ============================================
echo   Pydoll MCP Server
echo   http://%PYDOLL_MCP_HOST:='127.0.0.1'%:%PYDOLL_MCP_PORT:='8765'%
echo   Auth token: %PYDOLL_MCP_AUTH_TOKEN%
echo ============================================
echo.

C:\Users\Yuri\anaconda3\python.exe -m pydoll_mcp_server.cli %*

endlocal
