"""Tests for JavaScript security scanning."""

from __future__ import annotations

from pydoll_mcp_server.tools.javascript import scan_script


class TestJSScanner:
    def test_clean_script(self) -> None:
        warnings = scan_script('return document.title;')
        assert warnings == []

    def test_detect_document_cookie(self) -> None:
        warnings = scan_script('document.cookie = "x=y";')
        assert any('document.cookie' in w for w in warnings)

    def test_detect_localstorage(self) -> None:
        warnings = scan_script('localStorage.getItem("x");')
        assert any('localStorage' in w for w in warnings)

    def test_detect_sessionstorage(self) -> None:
        warnings = scan_script('sessionStorage.setItem("k", "v");')
        assert any('sessionStorage' in w for w in warnings)

    def test_detect_form_submit(self) -> None:
        warnings = scan_script('document.forms[0].submit();')
        assert any('form submission' in w.lower() for w in warnings)

    def test_detect_location_assignment(self) -> None:
        warnings = scan_script('location = "https://evil.com";')
        assert any('location' in w for w in warnings)

    def test_detect_location_href(self) -> None:
        warnings = scan_script('location.href = "https://evil.com";')
        assert any('location' in w for w in warnings)

    def test_detect_infinite_loop(self) -> None:
        warnings = scan_script('while (true) { doSomething(); }')
        assert any('infinite' in w for w in warnings)

    def test_detect_while_1(self) -> None:
        warnings = scan_script('while (1) { break; }')
        assert any('infinite' in w for w in warnings)

    def test_detect_fetch(self) -> None:
        warnings = scan_script('fetch("https://example.com");')
        assert any('fetch' in w for w in warnings)
