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

The default `jobs` profile is focused on job search and application workflows.
Use `--tool-profile full` only when advanced browser compatibility tools are
explicitly required. The `agent` and `linkedin` profiles remain legacy options.

```yaml
mcp_servers:
  pydoll-mcp:
    transport: stdio
    command: pydoll-mcp-server
    args: ["--transport", "stdio", "--tool-profile", "jobs"]
```

Restart Codex after config changes.

Keep the configured MCP server running for the whole browser task. Use one stable
client identity and reuse the browser returned by `browser_launch`. Starting a
second server against the same persistent profile returns `RESOURCE_LOCKED`.
The server closes managed browsers during graceful shutdown while the persistent
profile keeps its login state for the next session.

Use `tab_list` as the authoritative tab count. The server reconciles the live Chrome targets
and permits at most five tabs per browser. Keep the search tab open when working in an
application tab. Do not assume a close succeeded until `tab_close` returns
`confirmed_closed=true`. If a browser-dialog-specific tool is required, start an
explicit `full` compatibility profile; it is not part of the default `jobs` surface.

For application forms, use `form_preflight`, `form_prepare`, `form_review`, and
`form_submit_after_review` in that order. The final tool requires an explicit
authorization mode and a single-use review token bound to the client, tab,
document generation, and form fingerprint. It does not retry an unknown final
click. Use `artifact_export` only with a server-owned artifact ID and a
destination under the configured allowlist.
