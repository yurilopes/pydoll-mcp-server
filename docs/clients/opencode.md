# Configuring OpenCode with Pydoll MCP Server

## HTTP transport (recommended)

Start the server:

```powershell
$env:PYDOLL_MCP_AUTH_TOKEN = "your-secret-token"
pydoll-mcp-server --host 127.0.0.1 --port 8765
```

In your OpenCode project config (`.opencode/opencode.jsonc`):

```jsonc
{
  "mcp": {
    "pydoll-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Authorization": "Bearer your-secret-token"
      }
    }
  }
}
```

## stdio transport (optional)

For Windows native mode, keep stdio UTF-8 explicit:

```powershell
$env:PYDOLL_MCP_ALLOW_NO_AUTH = "true"
$env:PYTHONIOENCODING = "utf-8"
python -m pydoll_mcp_server.cli --transport stdio
```

```jsonc
{
  "mcp": {
    "pydoll-mcp": {
      "type": "local",
      "command": [
        "python",
        "-m",
        "pydoll_mcp_server.cli",
        "--transport",
        "stdio"
      ],
      "environment": {
        "PYDOLL_MCP_ALLOW_NO_AUTH": "true",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

For sandboxed manual validation, set `PYDOLL_MCP_RUNTIME_DIR`, `TEMP`, and `TMP`
to controlled temporary directories. `page_goto` accepts only `http://` and
`https://`. Local fixtures must be served through a loopback HTTP server such as
`http://127.0.0.1:<port>/...`. Navigation to `file://` is blocked completely.

Suggested validation prompt:

```text
Use the pydoll MCP server.

1. Show server status.
2. Launch a headless browser with a temporary profile.
3. Open a local page served through http://127.0.0.1.
4. Get the page tree.
5. Click a button by the returned element_id.
6. Fill an input with: Olá mundo, 日本語, 한국어, 中文.
7. Read the input value and confirm UTF-8 was preserved.
8. Save a screenshot to an allowed artifact path.
9. Show server status again.
10. Close the browser.
```

Restart OpenCode after config changes.
