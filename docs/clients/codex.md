# Configuring Codex with Pydoll MCP Server

## HTTP transport (recommended)

Start the server:

```powershell
$env:PYDOLL_MCP_AUTH_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:PYDOLL_MCP_AUTH_TOKEN
pydoll-mcp-server --host 127.0.0.1 --port 8765
```

Copy the generated value from `$env:PYDOLL_MCP_AUTH_TOKEN` into the client
configuration below. Token generation uses Python for compatibility with both
Windows PowerShell 5.1 and PowerShell 7.

In Codex config (`~/.codex/config.yaml` or project `.codex/config.yaml`):

```yaml
mcp_servers:
  pydoll-mcp:
    transport: http
    url: http://127.0.0.1:8765/mcp
    headers:
      Authorization: Bearer your-secret-token
```

## stdio transport (optional)

The default `full` profile preserves compatibility. For general browser
automation, prefer `--tool-profile agent`; use `--tool-profile linkedin` when
LinkedIn search or Easy Apply helpers are needed.

```yaml
mcp_servers:
  pydoll-mcp:
    transport: stdio
    command: pydoll-mcp-server
    args: ["--transport", "stdio", "--tool-profile", "agent"]
```

Restart Codex after config changes.
