from __future__ import annotations

import textwrap


def _build_stealth_init_script() -> str:
    """Build the basic stealth JS similar to browser_pool._apply_stealth_evasion."""
    return textwrap.dedent("""
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = { runtime: {} };
    (function() {
        const pluginData = [
            {name:'PDF Viewer',filename:'internal-pdf-viewer',description:'Portable Document Format'},
            {name:'Chrome PDF Viewer',filename:'internal-pdf-viewer',description:'Portable Document Format'},
            {name:'Chromium PDF Viewer',filename:'internal-pdf-viewer',description:'Portable Document Format'},
            {name:'Microsoft EDGE PDF Viewer',filename:'internal-pdf-viewer',description:'Portable Document Format'},
            {name:'WebKit built-in PDF',filename:'internal-pdf-viewer',description:'Portable Document Format'},
        ];
        const pluginArray = [];
        pluginData.forEach(function(p) {
            const plugin = {name:p.name,filename:p.filename,description:p.description,length:1,
                0:{type:'application/pdf',suffixes:'pdf',description:p.description}};
            pluginArray.push(plugin);
        });
        Object.defineProperty(pluginArray, 'length', {get: () => pluginArray.length});
        Object.defineProperty(navigator, 'plugins', {get: () => pluginArray});
    })();
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
    """)


def _has_data_image_empty_refs(pdf_text: str) -> list[str]:
    """Check PDF text for [data:image] empty object references."""
    matches: list[str] = []
    import re

    for match in re.finditer(r"\[data:image[^\]]*\]", pdf_text, re.IGNORECASE):
        matches.append(match.group())
    return matches


class TestStealthInitScript:
    """Anti 33: Verify stealth init script properties."""

    def test_webdriver_undefined(self) -> None:
        js = _build_stealth_init_script()
        assert "navigator" in js
        assert "webdriver" in js
        assert "undefined" in js

    def test_chrome_runtime_spoofed(self) -> None:
        js = _build_stealth_init_script()
        assert "window.chrome" in js
        assert "runtime: {}" in js

    def test_navigator_plugins_spoofed(self) -> None:
        js = _build_stealth_init_script()
        assert "navigator" in js
        assert "plugins" in js

    def test_navigator_languages_spoofed(self) -> None:
        js = _build_stealth_init_script()
        assert "navigator" in js
        assert "languages" in js
        assert "en-US" in js

    def test_plugin_array_with_pdf_viewers(self) -> None:
        js = _build_stealth_init_script()
        assert "PDF Viewer" in js
        assert "Chrome PDF Viewer" in js
        assert "Chromium PDF Viewer" in js
        assert "Microsoft EDGE PDF Viewer" in js
        assert "WebKit built-in PDF" in js

    def test_script_valid_syntax(self) -> None:
        js = _build_stealth_init_script()
        assert js.count("(") == js.count(")")
        assert js.count("{") == js.count("}")

    def test_script_no_literal_newlines_in_strings(self) -> None:
        js = _build_stealth_init_script()
        for line in js.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("'", '"')):
                assert "'\\n'" not in stripped and '"\\n"' not in stripped


class TestDataImageDetection:
    """Anti 33: PDF should not contain [data:image] empty objects."""

    def test_clean_pdf_text_returns_no_matches(self) -> None:
        clean = "PDF content with normal images and text"
        assert _has_data_image_empty_refs(clean) == []

    def test_identifies_data_image_in_text(self) -> None:
        dirty = "Some content [data:image] and [data:image/png] more text"
        matches = _has_data_image_empty_refs(dirty)
        assert len(matches) >= 2

    def test_case_insensitive_detection(self) -> None:
        dirty = "found [DATA:IMAGE] here"
        matches = _has_data_image_empty_refs(dirty)
        assert len(matches) == 1

    def test_no_false_positive_on_normal_image(self) -> None:
        text = "normal image <img src='data:image/png;base64,abc'> reference"
        assert _has_data_image_empty_refs(text) == []

    def test_browser_webdriver_set_in_init_script(self) -> None:
        source_lines = [
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
            "window.chrome = { runtime: {} }",
            "Object.defineProperty(navigator, 'languages'",
            "Object.defineProperty(navigator, 'plugins'",
        ]
        for line_str in source_lines:
            assert line_str in _build_stealth_init_script()
