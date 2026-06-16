# Agent Recipes

These recipes show preferred tool sequences for modern frontend pages. They are
designed to reduce custom JavaScript and keep actions inside the MCP safety
model.

## Open and inspect a page

1. `browser_launch(client_id, headless=false, profile_mode="temporary")`
2. `page_goto(client_id, tab_id, url)`
3. `page_get_text(client_id, tab_id)`
4. `page_get_interactive_summary(client_id, tab_id)`

Use `page_get_tree` when you need DOM shape. It hides head metadata and
invisible nodes by default. Use `include_head=true` or `include_invisible=true`
only for diagnostics.

## Click a visible option by text

Use `element_click_by_text` for cards, buttons, tabs, and custom controls:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "text": "Freelance",
  "exact": true
}
```

The response includes the chosen candidate and rejected candidates so the agent
can detect ambiguity before continuing.

## Fill a controlled input

Use `element_fill` or `element_fill_and_verify` with `value`:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_abc",
  "value": "Senior Python developer"
}
```

The fill path uses native property setters and dispatches `input`, `change`, and
`blur` so React-like controlled inputs see the update.

## Select an autocomplete combobox option

1. Find the input with `page_get_interactive_summary`, `element_find_by_label`,
   or `element_find_by_placeholder`.
2. Call `combobox_type_and_select`.

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_skill",
  "query": "Artificial",
  "option_text": "Artificial Intelligence"
}
```

The tool handles `aria-controls`, `role=listbox`, `role=option`, and portaled
option containers.

## Wait for state instead of sleeping

Prefer condition waits over fixed sleeps:

- `page_wait_for_text`
- `page_wait_text_gone`
- `page_wait_for_selector`
- `page_wait_for_url`
- `page_wait_for_network_idle`
- `element_wait_value`

## Upload a file safely

Use `artifact_get_paths` to discover runtime directories. If a source file is
outside allowed upload directories, use `artifact_import` only when the source is
inside an explicit import allowlist.

Then call:

```json
{
  "client_id": "agent",
  "tab_id": "tab",
  "element_id": "el_file",
  "paths": ["C:\\Users\\Yuri\\AppData\\Local\\pydoll-mcp-server\\artifacts\\agent\\resume.pdf"]
}
```

Check `file_upload_state` or nearby page text after upload if the page moves the
file state out of the native input.

## Evaluate JavaScript only when needed

`js_evaluate_readonly` returns real JSON values:

```json
{
  "success": true,
  "value": {"answer": 42},
  "value_type": "object"
}
```

Do not parse `value` as a JSON string. Use manual JavaScript only for diagnostics
that the first-class tools cannot provide.

