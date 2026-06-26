"""F-FRONTEND-001 — esbuild bundler artifact validation.

Verifies:
1. `npm run build` produces the expected dist/ artifacts
2. First-paint CSS bundle < 200 KB
3. Main app.js entry chunk exists
4. Dynamic import chunks are present (code splitting works)
5. manifest.json is valid
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"


def _check_dist_exists() -> None:
    assert DIST_DIR.is_dir(), f"F-FRONTEND-001: dist directory missing at {DIST_DIR}. Run 'npm run build' first."
    assert (DIST_DIR / "app.js").is_file(), "F-FRONTEND-001: dist/app.js missing. Run 'npm run build' first."
    assert (DIST_DIR / "styles.css").is_file(), "F-FRONTEND-001: dist/styles.css missing. Run 'npm run build' first."


class TestFrontendBuildArtifacts:
    """F-FRONTEND-001: esbuild produces expected dist/ output."""

    def test_dist_directory_exists(self) -> None:
        assert DIST_DIR.is_dir(), "F-FRONTEND-001: no dist/ directory. Run 'npm run build' before this test."

    def test_main_js_bundle_exists(self) -> None:
        _check_dist_exists()
        size_kb = (DIST_DIR / "app.js").stat().st_size / 1024
        assert size_kb > 1, f"F-FRONTEND-001: dist/app.js too small ({size_kb:.1f} KB)"

    def test_css_bundle_exists_and_under_threshold(self) -> None:
        _check_dist_exists()
        size_kb = (DIST_DIR / "styles.css").stat().st_size / 1024
        assert size_kb < 200, f"F-FRONTEND-001: first-paint CSS is {size_kb:.1f} KB >= 200 KB (acceptance criterion)"

    def test_code_splitting_chunks_exist(self) -> None:
        _check_dist_exists()
        chunks_dir = DIST_DIR / "chunks"
        assert chunks_dir.is_dir(), "F-FRONTEND-001: no chunks/ directory — code splitting not working"
        chunk_files = list(chunks_dir.glob("*.js"))
        assert len(chunk_files) >= 5, (
            f"F-FRONTEND-001: too few code-split chunks ({len(chunk_files)}). "
            "Dynamic import() calls should produce at least 5 chunks."
        )
        # Verify at least some named chunks from dynamic imports
        named_chunks = [c.name for c in chunk_files if "-" in c.stem and not c.stem.startswith("chunk-")]
        assert any("api-keys" in n for n in named_chunks), (
            f"F-FRONTEND-001: no api-keys-page chunk found. Named chunks: {named_chunks}"
        )

    def test_manifest_json_is_valid(self) -> None:
        _check_dist_exists()
        manifest_path = DIST_DIR / "manifest.json"
        assert manifest_path.is_file(), "F-FRONTEND-001: manifest.json missing"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(manifest, dict)
        assert len(manifest) > 0
        # All values should be relative paths that exist
        for rel_path in manifest.values():
            if rel_path.endswith(".map") or "woff" in rel_path:
                continue  # source maps and fonts are optional
            if rel_path.startswith("dist/"):
                assert (FRONTEND_DIR / rel_path).exists() or (FRONTEND_DIR / ".." / rel_path).exists()
            elif rel_path.startswith("frontend/"):
                assert (REPO_ROOT / rel_path).exists(), f"F-FRONTEND-001: manifest path {rel_path} does not exist"

    def test_styles_does_not_import_original_sources(self) -> None:
        """The bundled CSS should contain inlined rule content, not @import directives to the original files."""
        _check_dist_exists()
        bundled = (DIST_DIR / "styles.css").read_text(encoding="utf-8")
        # The bundle should not reference the original @import cascade paths
        assert "@import" not in bundled, "F-FRONTEND-001: bundled styles.css still contains @import — tree-shaking failed"
        # It should contain rule content from at least a few of the source files
        assert "font-family" in bundled, "F-FRONTEND-001: bundled CSS missing font-face rules"
        assert "skip-link" in bundled, "F-FRONTEND-001: bundled CSS missing base layout rules"
