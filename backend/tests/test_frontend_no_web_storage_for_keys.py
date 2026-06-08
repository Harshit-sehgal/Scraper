"""Static guards against storing sensitive data in browser Web Storage.

These tests are intentionally simple: they grep the frontend JS source
for `sessionStorage` / `localStorage` references touching the API key
identifier. The dashboard's UI state (theme) is permitted to use
localStorage, so we limit the check to the key namespace.

If a future change reintroduces ``sessionStorage.setItem('dataforge_api_key', …)``
or similar, this test fails and forces a security review.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIRS = [
    REPO_ROOT / "frontend" / "js",
    REPO_ROOT / "frontend" / "dashboard",
]

# Substrings we forbid in non-comment lines of frontend source.
FORBIDDEN_PATTERNS = [
    "sessionStorage.setItem('dataforge_api_key'",
    'sessionStorage.setItem("dataforge_api_key"',
    "sessionStorage.getItem('dataforge_api_key'",
    'sessionStorage.getItem("dataforge_api_key"',
    "localStorage.setItem('dataforge_api_key'",
    'localStorage.setItem("dataforge_api_key"',
    "localStorage.getItem('dataforge_api_key'",
    'localStorage.getItem("dataforge_api_key"',
]


def _is_comment_line(stripped: str) -> bool:
    s = stripped.lstrip()
    return s.startswith(("//", "/*", "*"))


def test_no_session_storage_for_api_key() -> None:
    """``sessionStorage`` MUST NOT be used to persist the API key."""
    offenders: list[str] = []
    for d in FRONTEND_DIRS:
        if not d.exists():
            continue
        for js_file in d.rglob("*.js"):
            for lineno, raw in enumerate(js_file.read_text().splitlines(), start=1):
                stripped = raw.strip()
                if not stripped or _is_comment_line(stripped):
                    continue
                for needle in FORBIDDEN_PATTERNS:
                    if needle in raw:
                        offenders.append(f"{js_file.relative_to(REPO_ROOT)}:{lineno}: {stripped}")
    assert not offenders, (
        "Frontend JS must not persist the API key in Web Storage. "
        "Use in-memory state or a backend-issued HTTP-only cookie. "
        "Offending lines:\n  " + "\n  ".join(offenders)
    )
