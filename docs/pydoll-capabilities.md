# Pydoll Capabilities Matrix

Date: 2026-06-12. Source: Pydoll v2.23.0, commit `59330abf`.

## Legend

| Status | Meaning |
|--------|---------|
| VERIFIED | Confirmed in source code and/or docs |
| HYPOTHESIS | Docs suggest support, needs runtime validation |
| UNSUPPORTED | Not available in Pydoll |
| PARTIAL | Works with limitations |

## Browser Management

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Launch Chrome | `Chrome().start()` -> `Tab` | `pydoll/browser/chromium/chrome.py` | VERIFIED | `browser_launch` | PLAN_03 |
| Launch Edge | `Edge().start()` | `pydoll/browser/chromium/edge.py` | VERIFIED | P2 | PLAN_03 |
| Headless mode | `ChromiumOptions.headless` | `pydoll/browser/options.py` | VERIFIED | `browser_launch` | PLAN_03 |
| Connect to running browser | `Browser.connect(ws_address)` | `pydoll/browser/chromium/base.py` | VERIFIED | `browser_attach` | PLAN_03 |
| User data dir | `ChromiumOptions.user_data_dir` | `pydoll/browser/options.py` | VERIFIED | Perfis | PLAN_03 |
| Close browser | `Browser.stop()` | `pydoll/browser/chromium/base.py` | VERIFIED | `browser_close` | PLAN_03 |
| Browser version | `Browser.get_version()` | `pydoll/browser/chromium/base.py` | VERIFIED | Health | PLAN_09 |
| Process alive check | Via process manager | `pydoll/browser/managers/browser_process_manager.py` | VERIFIED | Health | PLAN_09 |

## Tab Management

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| New tab | `Browser.new_tab()` | `base.py` | VERIFIED | `browser_launch` | PLAN_03 |
| List tabs | `Browser.get_opened_tabs()` | `base.py` | VERIFIED | `tab_list` | PLAN_03 |
| Close tab | `Tab.close()` | `tab.py` | VERIFIED | `tab_close` | PLAN_03 |
| Bring to front | `Tab.bring_to_front()` | `tab.py` | VERIFIED | `tab_activate` | PLAN_03 |
| Window ID for tab | `Browser.get_window_id_for_tab()` | `base.py` | VERIFIED | `window_list` | PLAN_03 |
| Window bounds | `Browser.set_window_bounds()` | `base.py` | VERIFIED | `window_set_bounds` | PLAN_03 |
| Maximize/minimize | `Browser.set_window_maximized/minimized()` | `base.py` | VERIFIED | `window_set_bounds` | PLAN_03 |
| Tab title | `Tab.title` | `tab.py` | VERIFIED | Health, observation | PLAN_05 |
| Current URL | `Tab.current_url` | `tab.py` | VERIFIED | Health, observation | PLAN_05 |
| Page source | `Tab.page_source` | `tab.py` | VERIFIED | `page_get_text` | PLAN_05 |

## Navigation

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Go to URL | `Tab.go_to(url, timeout=300)` | `tab.py` | VERIFIED | `page_goto` | PLAN_04 |
| Refresh | `Tab.refresh(ignore_cache)` | `tab.py` | VERIFIED | `page_reload` | PLAN_04 |
| Back/Forward | Not directly exposed | `tab.py` | HYPOTHESIS | `page_back`, `page_forward` | PLAN_04 |
| Page load state | `PageLoadState` enum | `constants.py` | VERIFIED | Wait policy | PLAN_04 |
| Page events | `Tab.enable_page_events()` | `tab.py` | VERIFIED | Load detection | PLAN_04 |

## Element Finding

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| CSS selector | `Tab.query(css)` | `mixins/find_elements_mixin.py` | VERIFIED | `element_find` | PLAN_06 |
| XPath | `Tab.query(xpath)` | `mixins/find_elements_mixin.py` | VERIFIED | `element_find` | PLAN_06 |
| By attribute | `Tab.find(id=, class_name=, ...)` | `mixins/find_elements_mixin.py` | VERIFIED | `element_find` | PLAN_06 |
| Wait for element | `Tab.find_or_wait_element(by, value, timeout)` | `mixins/find_elements_mixin.py` | VERIFIED | `element_find` | PLAN_06 |
| Find all | `find_all=True` | `mixins/find_elements_mixin.py` | VERIFIED | `element_find` | PLAN_06 |
| Relative find | `WebElement.find()` / `WebElement.query()` | `elements/web_element.py` | VERIFIED | Scoped search | PLAN_06 |

## Element Interaction

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Click | `WebElement.click()` | `elements/web_element.py` | VERIFIED | `element_click` | PLAN_06 |
| JS click | `WebElement.click_using_js()` | `elements/web_element.py` | VERIFIED | Fallback | PLAN_06 |
| Type text | `WebElement.type_text(text)` | `elements/web_element.py` | VERIFIED | `element_type` | PLAN_06 |
| Insert text | `WebElement.insert_text(text)` | `elements/web_element.py` | VERIFIED | `element_fill` | PLAN_06 |
| Clear input | `WebElement.clear()` | `elements/web_element.py` | VERIFIED | `element_fill` | PLAN_06 |
| Focus | `WebElement.focus()` | `elements/web_element.py` | VERIFIED | Pre-click | PLAN_06 |
| Scroll into view | `WebElement.scroll_into_view()` | `elements/web_element.py` | VERIFIED | Pre-click | PLAN_06 |
| Get attribute | `WebElement.get_attribute(name)` | `elements/web_element.py` | VERIFIED | `element_get_attribute` | PLAN_06 |
| Element text | `WebElement.text` | `elements/web_element.py` | VERIFIED | `element_get_text` | PLAN_06 |
| Element tag name | `WebElement.tag_name` | `elements/web_element.py` | VERIFIED | Observation | PLAN_05 |
| Is visible | `WebElement.is_visible()` | `elements/web_element.py` | VERIFIED | Validation | PLAN_06 |
| Is interactable | `WebElement.is_interactable()` | `elements/web_element.py` | VERIFIED | Validation | PLAN_06 |
| Is enabled | `WebElement.is_enabled` | `elements/web_element.py` | VERIFIED | Validation | PLAN_06 |
| Is editable | `WebElement.is_editable()` | `elements/web_element.py` | VERIFIED | Validation | PLAN_06 |
| Is on top | `WebElement.is_on_top()` | `elements/web_element.py` | VERIFIED | Click validation | PLAN_06 |
| Wait until | `WebElement.wait_until()` | `elements/web_element.py` | VERIFIED | Wait policy | PLAN_06 |
| Bounding box | `WebElement.bounds` | `elements/web_element.py` | VERIFIED | Hints | PLAN_05 |
| Inner HTML | `WebElement.inner_html` | `elements/web_element.py` | VERIFIED | Tree | PLAN_05 |

## Iframes

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Detect iframe | `WebElement.is_iframe` | `elements/web_element.py` | VERIFIED | Deep traversal | PLAN_07 |
| Iframe context | `WebElement.iframe_context` -> IFrameContext | `elements/web_element.py` | VERIFIED | Frame path | PLAN_07 |
| Cross-frame selectors | `selector >> inner-selector` (CSS) | `mixins/find_elements_mixin.py` | VERIFIED | `element_find_deep` | PLAN_07 |
| OOPIF support | `IFrameContextResolver` | `mixins/find_elements_mixin.py` | VERIFIED | Partial result | PLAN_07 |
| Interact in iframe | Via `WebElement` as search scope | `elements/web_element.py` | VERIFIED | Deep traversal | PLAN_07 |

## Shadow DOM

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Get shadow root | `WebElement.get_shadow_root()` -> `ShadowRoot` | `elements/web_element.py` | VERIFIED | `page_get_tree_deep` | PLAN_07 |
| Find all shadow roots | `Tab.find_shadow_roots(deep=False)` | `tab.py` | VERIFIED | `page_get_tree_deep` | PLAN_07 |
| Shadow root mode | `ShadowRoot.mode` (open/closed/user-agent) | `elements/shadow_root.py` | VERIFIED | Closed support | PLAN_07 |
| CSS in shadow | `ShadowRoot.query(css)` | `elements/shadow_root.py` | VERIFIED | Deep search | PLAN_07 |
| XPath in shadow | Raises `NotImplementedError` | `elements/shadow_root.py` | VERIFIED | Limitation | PLAN_07 |
| OOPIF shadow roots | `_collect_oopif_shadow_roots()` | `tab.py` | VERIFIED | Deep traversal | PLAN_07 |

## Screenshots

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Page screenshot | `Tab.take_screenshot()` | `tab.py` | VERIFIED | `page_screenshot` | PLAN_05 |
| Element screenshot | `WebElement.take_screenshot()` | `elements/web_element.py` | VERIFIED | `element_screenshot` | PLAN_06 |
| Full page | `beyond_viewport=True` | `tab.py` | VERIFIED | `page_screenshot` | PLAN_05 |
| Base64 output | `as_base64=True` | `tab.py` | VERIFIED | `page_screenshot` | PLAN_05 |
| JPEG/PNG | `quality` param | `tab.py` | VERIFIED | Format | PLAN_05 |

## JavaScript Execution

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Execute script | `Tab.execute_script(script)` | `tab.py` | VERIFIED | `js_evaluate` | PLAN_08 |
| Execute on element | `WebElement.execute_script(script)` | `elements/web_element.py` | VERIFIED | `js_evaluate` | PLAN_08 |
| JSON serialize | Returns typed response | `tab.py` | VERIFIED | Output | PLAN_08 |
| Page events | `Tab.enable_page_events()` | `tab.py` | VERIFIED | Console/Network | PLAN_08 |

## Cookies

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Get cookies (tab) | `Tab.get_cookies()` | `tab.py` | VERIFIED | `cookies_get` | PLAN_08 |
| Set cookies (tab) | `Tab.set_cookies(cookies)` | `tab.py` | VERIFIED | `cookies_set` | PLAN_08 |
| Delete cookies (tab) | `Tab.delete_all_cookies()` | `tab.py` | VERIFIED | `cookies_set` | PLAN_08 |
| Get cookies (browser) | `Browser.get_cookies()` | `base.py` | VERIFIED | `cookies_get` | PLAN_08 |
| Set cookies (browser) | `Browser.set_cookies()` | `base.py` | VERIFIED | `cookies_set` | PLAN_08 |
| Cookie model | `Cookie`, `CookieParam` types | Pydoll protocol | VERIFIED | Schemas | PLAN_08 |

## Storage

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Browser contexts | `Browser.create_browser_context()` | `base.py` | VERIFIED | Isolated storage | PLAN_08 |
| Context deletion | `Browser.delete_browser_context()` | `base.py` | VERIFIED | Cleanup | PLAN_08 |
| Local/session storage | Via CDP commands (Storage domain) | `commands/storage.py` | HYPOTHESIS | `storage_get/set` | PLAN_08 |

## Downloads

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Set download path | `Browser.set_download_path(path)` | `base.py` | VERIFIED | `download_expect` | PLAN_08 |
| Download behavior | `Browser.set_download_behavior()` | `base.py` | VERIFIED | Control | PLAN_08 |
| Expect download | `Tab.expect_download()` context manager | `tab.py` | VERIFIED | `download_expect` | PLAN_08 |
| Download handle | `_DownloadHandle.file_path, .read_bytes()` | `tab.py` | VERIFIED | Artifact | PLAN_08 |

## File Upload

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Set input files | `WebElement.set_input_files(files)` | `elements/web_element.py` | VERIFIED | `upload_files` | PLAN_08 |
| Expect file chooser | `Tab.expect_file_chooser(files)` | `tab.py` | VERIFIED | `upload_files` | PLAN_08 |

## Network

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Network events | `Tab.enable_network_events()` | `tab.py` | VERIFIED | `network_list` | PLAN_08 |
| Network logs | `Tab.get_network_logs()` | `tab.py` | VERIFIED | `network_list` | PLAN_08 |
| Response body | `Tab.get_network_response_body()` | `tab.py` | VERIFIED | Network detail | PLAN_08 |
| Fetch interception | `Tab.enable_fetch_events()` | `tab.py` | VERIFIED | Network control | PLAN_08 |

## Console

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Runtime events | `Tab.enable_runtime_events()` | `tab.py` | HYPOTHESIS | `console_list` | PLAN_08 |
| DOM events | `Tab.enable_dom_events()` | `tab.py` | VERIFIED | Observation | PLAN_05 |
| Dialogs | `Tab.has_dialog()`, `.handle_dialog()` | `tab.py` | VERIFIED | Dialog handling | PLAN_04 |

## User Agent / Viewport

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| User agent override | `Browser` auto-propagates to workers | `base.py` | VERIFIED | `user_agent_set` | PLAN_08 |
| Viewport set | Via CDP commands | `commands/page.py` | HYPOTHESIS | `viewport_set` | PLAN_08 |

## Browser Contexts

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Isolated contexts | `Browser.create_browser_context()` | `base.py` | VERIFIED | Multi-client | PLAN_03 |
| Context list | `Browser.get_browser_contexts()` | `base.py` | VERIFIED | Registry | PLAN_03 |
| Permissions | `Browser.grant_permissions()` | `base.py` | VERIFIED | Advanced | PLAN_08 |
| Proxy per context | `create_browser_context(proxy_server=)` | `base.py` | VERIFIED | P2 | - |

## Event System

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Browser events | `Browser.on(event, callback)` | `base.py` | VERIFIED | Health monitoring | PLAN_09 |
| Tab events | `Tab.on(event, callback)` | `tab.py` | VERIFIED | Wait/health | PLAN_04 |
| Remove callback | `.remove_callback()` | `base.py` | VERIFIED | Cleanup | PLAN_09 |
| Async callbacks | Supported | `base.py` | VERIFIED | Integration | PLAN_09 |

## Input APIs (Advanced)

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Keyboard API | `Tab.keyboard.press/down/up/hotkey` | `tab.py` | VERIFIED | Future | P2 |
| Mouse API | `Tab.mouse.click/move/drag` | `tab.py` | VERIFIED | Future | P2 |
| Scroll API | `Tab.scroll.to/into_view` | `tab.py` | VERIFIED | Future | P2 |
| Human-like typing | `WebElement.type_text(humanize=True)` | `elements/web_element.py` | VERIFIED | Advanced | P2 |

## Data Extraction

| Capability | Pydoll API | Source | Status | MCP Impact | Plan |
|------------|-----------|--------|--------|------------|------|
| Structured extraction | `Tab.extract(model)` | `tab.py` | VERIFIED | P2 | - |
| Pydantic models | `Tab.extract_all(model)` | `tab.py` | VERIFIED | P2 | - |

## Unsupported

| Capability | Notes |
|------------|-------|
| Native `page_back`/`page_forward` | Not directly exposed; may use CDP Page.navigateToHistoryEntry or JS `history.back()` |
| Viewport set API | Not directly exposed as method; may use CDP `Emulation.setDeviceMetricsOverride` |
| Console log collection | Tab supports `enable_runtime_events()` but no explicit console log API; may work via Runtime.consoleAPICalled event |
| Video recording | Not supported in Pydoll |

## Validation Notes

- Back/forward: Marked HYPOTHESIS. If Pydoll does not expose history navigation, implement via JS `history.go(-1)` or CDP `Page.navigateToHistoryEntry` with security audit.
- Viewport: Marked HYPOTHESIS. If Pydoll does not expose viewport method, implement via CDP `Emulation.setDeviceMetricsOverride` as a delimited helper.
- Storage get/set: Marked HYPOTHESIS. Pydoll has `StorageCommands` but no high-level API. Use CDP `Storage` domain through delimited helpers.
- Console list: Marked HYPOTHESIS. Pydoll has `enable_runtime_events()` which may capture `Runtime.consoleAPICalled`. Validate before exposing.
- Network list: Verified via `get_network_logs()`. Expose with redaction of sensitive headers.

## PLAN_14 Capabilities Used (Agent Form Flow V2)

Date: 2026-06-17. All capabilities verified in Pydoll v2.23.0.

| Capability | Pydoll API | MCP Impact |
|------------|-----------|------------|
| Execute script (tab) | `Tab.execute_script(script, return_by_value=True)` | All JS-based surface/ranking/fill tools |
| Click | `WebElement.click()` | `element_click`, `page_click_primary_action` |
| Mouse click | `Tab.mouse.click(x, y, button)` | `click_strategy=center_mouse` |
| Set input files | `WebElement.set_input_files(files)` | `upload_files`, `artifact_prepare_upload` |
| Page screenshot | `Tab.take_screenshot(beyond_viewport, as_base64, path)` | `page_screenshot` (artifact-first) |
| Element screenshot | `WebElement.take_screenshot(as_base64, path)` | `element_screenshot` (artifact-first) |
| Get tab URL | `Tab.current_url` or CDP | `get_tab_url()` for URL change detection |
| Find elements | `Tab.query(css, find_all, raise_exc)` | `element_resolve_again` |
