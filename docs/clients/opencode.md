# Configuring OpenCode with Pydoll MCP Server

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
python -m pip install "pydoll-mcp-server[windows]"
$env:PYDOLL_MCP_ALLOW_NO_AUTH = "true"
$env:PYTHONIOENCODING = "utf-8"
python -m pydoll_mcp_server.cli --transport stdio --tool-profile jobs
```

The `windows` extra is needed only when an upload portal opens a native file
picker through the File System Access API. The fallback requires a visible
browser. Headless sessions receive a structured unsupported result.

For stdio without the optional Windows picker:

```powershell
$env:PYDOLL_MCP_ALLOW_NO_AUTH = "true"
$env:PYTHONIOENCODING = "utf-8"
python -m pydoll_mcp_server.cli --transport stdio
```

Use the `jobs` profile for the OpenCode job-search and application workflow.
It exposes semantic navigation, the form workflow, uploads, evidence, and
LinkedIn search and Easy Apply helpers while keeping advanced network,
JavaScript, storage, cookies, and diagnostic tools out of the default model
context. Use `full` only when advanced compatibility is required. The
`agent` and `linkedin` profiles remain legacy options.

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
        "stdio",
        "--tool-profile",
        "jobs"
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
4. Get a semantic page snapshot and active surface.
5. Find and click a button through the semantic element tools.
6. Fill an input with: Olá mundo, 日本語, 한국어, 中文.
7. Read the input value and confirm UTF-8 was preserved.
8. Save a screenshot to an allowed artifact path.
9. Show server status again.
10. Close the browser.
```

Restart OpenCode after config changes.
