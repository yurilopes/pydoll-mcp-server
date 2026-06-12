# Configuring Claude Code with Pydoll MCP Server

## HTTP transport (recommended)

Start the server:

```powershell
$env:PYDOLL_MCP_AUTH_TOKEN = "your-secret-token"
pydoll-mcp-server --host 127.0.0.1 --port 8765
```

In Claude Code config (`~/.claude/claude_desktop_config.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "pydoll-mcp": {
      "transport": "http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Authorization": "Bearer your-secret-token"
      }
    }
  }
}
```

## stdio transport (optional)

```json
{
  "mcpServers": {
    "pydoll-mcp": {
      "transport": "stdio",
      "command": "pydoll-mcp-server",
      "args": ["--transport", "stdio"]
    }
  }
}
```

Restart Claude Code after config changes.
